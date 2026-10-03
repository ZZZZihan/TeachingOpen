"""Bounded, byte-preserving Scratch hashes for owned local synthetic Redis only."""
import base64
import binascii
import json
from pathlib import Path
import re
import socket

from local_runtime import assert_app_config, load_ports


PREFIX = b'scratch:cloud:'
DATABASE = 1
CLOUD_FILE = 'cloud-values.json'
MAX_KEYS = 10000
MAX_FIELDS = 64
MAX_KEY_BYTES = 1024
MAX_FIELD_BYTES = 4096
MAX_VALUE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024

# One Redis command observes the complete allowlisted namespace atomically.
# SCAN is bounded by accepted keys; unrelated authentication values are not read.
CAPTURE = b'''
local keys, seen, cursor = {}, {}, '0'
repeat
  local batch = redis.call('SCAN', cursor, 'MATCH', 'scratch:cloud:*', 'COUNT', 256)
  cursor = batch[1]
  for _, key in ipairs(batch[2]) do
    if #key > 1024 then return redis.error_reply('CLOUD_KEY_LIMIT') end
    if not seen[key] then
      seen[key] = true; keys[#keys + 1] = key
      if #keys > 10000 then return redis.error_reply('CLOUD_KEY_LIMIT') end
    end
  end
until cursor == '0'
table.sort(keys)
local result, total = {}, 0
for _, key in ipairs(keys) do
  if redis.call('TYPE', key).ok ~= 'hash' then return redis.error_reply('CLOUD_WRONG_TYPE') end
  if redis.call('PTTL', key) ~= -1 then return redis.error_reply('CLOUD_EXPIRING') end
  local size = redis.call('HLEN', key)
  if size < 1 or size > 64 then return redis.error_reply('CLOUD_FIELD_LIMIT') end
  local names, fields = redis.call('HKEYS', key), {}
  table.sort(names); total = total + #key
  for _, name in ipairs(names) do
    local length = redis.call('HSTRLEN', key, name)
    if #name > 4096 or length > 1048576 then return redis.error_reply('CLOUD_BYTE_LIMIT') end
    total = total + #name + length
    if total > 16777216 then return redis.error_reply('CLOUD_BYTE_LIMIT') end
    fields[#fields + 1] = name; fields[#fields + 1] = redis.call('HGET', key, name)
  end
  result[#result + 1] = {key, -1, fields}
end
return result
'''

# Validate every key/count before writes. Redis errors can still leave a partial
# NEW target; the caller must not publish a successful restore result in that case.
RESTORE = b'''
if redis.call('DBSIZE') ~= 0 then return redis.error_reply('CLOUD_TARGET_NOT_EMPTY') end
local offset = 1
for _, key in ipairs(KEYS) do
  if string.sub(key, 1, 14) ~= 'scratch:cloud:' then return redis.error_reply('CLOUD_PREFIX') end
  local count = tonumber(ARGV[offset])
  if not count or count < 1 or count > 64 then return redis.error_reply('CLOUD_FIELD_LIMIT') end
  offset = offset + 1 + count * 2
end
if offset ~= #ARGV + 1 then return redis.error_reply('CLOUD_FORMAT') end
offset = 1
for _, key in ipairs(KEYS) do
  local count, fields = tonumber(ARGV[offset]), {}; offset = offset + 1
  for _ = 1, count * 2 do fields[#fields + 1] = ARGV[offset]; offset = offset + 1 end
  redis.call('HSET', key, unpack(fields))
end
return #KEYS
'''


class RedisCommandError(RuntimeError):
    pass


class OwnedRedis:
    """Minimal RESP2 transport: no CLI text conversion or credential arguments."""
    def __init__(self, runtime):
        self.runtime = Path(runtime).absolute()
        self.sock = self.reader = None
        self.reply_bytes = self.reply_nodes = 0

    def __enter__(self):
        runtime = self.runtime
        if (runtime.is_symlink() or runtime.parent.name != '.devspace'
                or runtime.parent.resolve() != runtime.parent or not runtime.is_dir()
                or runtime.stat().st_mode & 0o077):
            raise ValueError('Redis requires a private local runtime')
        assert_app_config(runtime)
        credentials = json.loads(read_private(runtime / 'config/credentials.json'))
        config = dict(line.split('=', 1) for line in read_private(runtime / 'config/application-localtest.properties').decode().splitlines()
                      if line and not line.startswith('#') and '=' in line)
        password = credentials.get('redis_password')
        if (not isinstance(password, str) or not password or config.get('spring.redis.database') != str(DATABASE)
                or config.get('spring.redis.password') != password):
            raise RuntimeError('Redis configuration differs from the owned local DB 1 profile')
        try:
            self.sock = socket.create_connection(('127.0.0.1', load_ports(runtime)['redis']), timeout=15)
            self.reader = self.sock.makefile('rb')
            if self.execute('AUTH', password) != b'OK': raise RuntimeError('Local Redis authentication failed')
            expected = {'dir': str(runtime / 'redis-data').encode(), 'bind': b'127.0.0.1',
                        'port': str(load_ports(runtime)['redis']).encode()}
            for name, value in expected.items():
                if self.execute('CONFIG', 'GET', name) != [name.encode(), value]:
                    raise RuntimeError('Actual Redis instance is not owned by this runtime')
            if self.execute('SELECT', DATABASE) != b'OK': raise RuntimeError('Cannot select local Redis DB 1')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.reader is not None: self.reader.close()
        if self.sock is not None: self.sock.close()
        self.reader = self.sock = None

    def execute(self, *args):
        if self.sock is None: raise RuntimeError('Owned Redis connection is not open')
        parts = [arg if isinstance(arg, bytes) else str(arg).encode() for arg in args]
        data = b'*' + str(len(parts)).encode() + b'\r\n' + b''.join(
            b'$' + str(len(part)).encode() + b'\r\n' + part + b'\r\n' for part in parts)
        self.sock.sendall(data)
        self.reply_bytes = self.reply_nodes = 0
        return self._read()

    def _read(self, depth=0):
        if depth > 4: raise RuntimeError('Unexpected nested Redis reply')
        line = self.reader.readline(1024)
        self.reply_bytes += len(line); self.reply_nodes += 1
        if self.reply_bytes > MAX_DOCUMENT_BYTES or self.reply_nodes > MAX_KEYS * (MAX_FIELDS * 2 + 5) + 64:
            raise RuntimeError('Redis reply exceeded total recovery limits')
        if not line.endswith(b'\r\n'): raise RuntimeError('Incomplete or oversized Redis reply')
        kind, body = line[:1], line[1:-2]
        if kind == b'+': return body
        if kind == b'-':
            code = re.search(rb'CLOUD_[A-Z_]+', body)
            raise RedisCommandError(code.group().decode() if code else 'Redis command failed')
        if kind not in (b':', b'$', b'*'): raise RuntimeError('Unsupported Redis reply')
        try: size = int(body)
        except ValueError as error: raise RuntimeError('Invalid Redis length') from error
        if kind == b':': return size
        if size == -1: return None
        if size < 0 or size > (MAX_TOTAL_BYTES if kind == b'$' else MAX_KEYS):
            raise RuntimeError('Redis reply exceeded recovery limits')
        if kind == b'*': return [self._read(depth + 1) for _ in range(size)]
        self.reply_bytes += size + 2
        if self.reply_bytes > MAX_DOCUMENT_BYTES: raise RuntimeError('Redis reply exceeded total recovery limits')
        value = self.reader.read(size + 2)
        if len(value) != size + 2 or not value.endswith(b'\r\n'): raise RuntimeError('Incomplete Redis bulk reply')
        return value[:-2]


def read_private(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Cloud recovery metadata must be an ordinary private file')
    if path.stat().st_size > MAX_DOCUMENT_BYTES: raise ValueError('Cloud recovery document exceeded size limit')
    return path.read_bytes()


def _decode(value):
    if not isinstance(value, str): raise ValueError('Cloud bytes require canonical base64 strings')
    try: raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error: raise ValueError('Invalid cloud base64') from error
    if base64.b64encode(raw).decode() != value: raise ValueError('Noncanonical cloud base64')
    return raw


def validate_cloud(document, project_ids=None):
    if (not isinstance(document, dict) or set(document) != {'format', 'database', 'prefix', 'ttl_policy', 'entries'}
            or type(document['format']) is not int or document['format'] != 1
            or type(document['database']) is not int or document['database'] != DATABASE
            or document['prefix'] != PREFIX.decode() or document['ttl_policy'] != 'persistent-only'
            or not isinstance(document['entries'], list) or len(document['entries']) > MAX_KEYS):
        raise ValueError('Unsupported cloud snapshot format or scope')
    total, previous = 0, None
    for entry in document['entries']:
        if (not isinstance(entry, dict) or set(entry) != {'key_b64', 'ttl_ms', 'fields'}
                or type(entry['ttl_ms']) is not int or entry['ttl_ms'] != -1
                or not isinstance(entry['fields'], list) or not 1 <= len(entry['fields']) <= MAX_FIELDS):
            raise ValueError('Invalid cloud hash entry or persistent-only TTL')
        key = _decode(entry['key_b64'])
        if (not key.startswith(PREFIX) or len(key) <= len(PREFIX) or len(key) > MAX_KEY_BYTES
                or (previous is not None and key <= previous)):
            raise ValueError('Invalid, duplicate or unsorted cloud key')
        project = key[len(PREFIX):]
        try: project.decode('utf-8')
        except UnicodeDecodeError as error: raise ValueError('Cloud project ID is not UTF-8') from error
        if any(byte < 32 or byte == 127 for byte in project): raise ValueError('Invalid cloud project ID')
        if project_ids is not None and project not in project_ids: raise ValueError('Dangling Scratch cloud project ID')
        total += len(key); previous = key; previous_field = None
        for pair in entry['fields']:
            if not isinstance(pair, list) or len(pair) != 2: raise ValueError('Invalid cloud field/value pair')
            field, value = (_decode(item) for item in pair)
            if (len(field) > MAX_FIELD_BYTES or len(value) > MAX_VALUE_BYTES
                    or (previous_field is not None and field <= previous_field)):
                raise ValueError('Cloud field bytes exceeded limits or duplicated/unsorted')
            total += len(field) + len(value); previous_field = field
            if total > MAX_TOTAL_BYTES: raise ValueError('Cloud snapshot exceeded total byte limit')
    return document


def capture_cloud(client, project_ids):
    try: rows = client.execute('EVAL', CAPTURE, 0)
    except RedisCommandError as error: raise ValueError('Scratch cloud snapshot refused: ' + str(error)) from error
    if not isinstance(rows, list): raise ValueError('Invalid cloud capture reply')
    entries = []
    for row in rows:
        if (not isinstance(row, list) or len(row) != 3 or not isinstance(row[0], bytes)
                or type(row[1]) is not int or not isinstance(row[2], list) or len(row[2]) % 2
                or any(not isinstance(item, bytes) for item in row[2])):
            raise ValueError('Invalid cloud capture row')
        encode = lambda raw: base64.b64encode(raw).decode()
        entries.append({'key_b64': encode(row[0]), 'ttl_ms': row[1],
                        'fields': [[encode(row[2][i]), encode(row[2][i + 1])] for i in range(0, len(row[2]), 2)]})
    return validate_cloud({'format': 1, 'database': DATABASE, 'prefix': PREFIX.decode(),
                           'ttl_policy': 'persistent-only', 'entries': entries}, project_ids)


def cloud_summary(document):
    validate_cloud(document)
    return {'included': 'scratch-cloud-hashes', 'database': DATABASE, 'prefix': PREFIX.decode(), 'file': CLOUD_FILE,
            'ttl_policy': 'persistent-only', 'keys': len(document['entries']),
            'fields': sum(len(entry['fields']) for entry in document['entries']),
            'authentication': 'excluded; fresh login required'}


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result: raise ValueError('Duplicate cloud document property')
        result[name] = value
    return result


def load_cloud(snapshot):
    return validate_cloud(json.loads(read_private(Path(snapshot) / CLOUD_FILE), object_pairs_hook=_unique_object))


def encode_cloud(document):
    validate_cloud(document)
    data = (json.dumps(document, indent=2) + '\n').encode()
    if len(data) > MAX_DOCUMENT_BYTES: raise ValueError('Cloud recovery document exceeded size limit')
    return data


def restore_cloud(client, document, project_ids):
    validate_cloud(document, project_ids)
    if client.execute('DBSIZE') != 0: raise RuntimeError('Fresh target Redis DB 1 is not empty; do not overwrite it')
    keys, args = [], []
    for entry in document['entries']:
        keys.append(_decode(entry['key_b64'])); args.append(len(entry['fields']))
        for field, value in entry['fields']: args.extend((_decode(field), _decode(value)))
    if client.execute('EVAL', RESTORE, len(keys), *keys, *args) != len(keys):
        raise RuntimeError('Cloud restore did not acknowledge all hashes')
    if capture_cloud(client, project_ids) != document:
        raise RuntimeError('Restored Scratch cloud bytes differ from snapshot')
