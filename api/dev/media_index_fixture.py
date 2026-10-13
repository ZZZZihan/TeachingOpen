"""Keep explicit raw-SQL fixture imports consistent with the media index.

This is fixture preparation and cleanup, not a production fallback. Call only
after a successful direct fixture SQL write; never wrap API business writes or
rebuild before an API assertion, which would hide transaction-sync failures.
The caller's FixtureApi and SQL callback retain the existing runtime guards and
CI adapter. This helper neither opens another database connection nor repairs
the original snapshot before recording it.
"""
import hashlib
import re


MEDIA_SOURCES = frozenset({
    'teaching_course', 'teaching_course_unit', 'teaching_additional_work',
    'sys_config', 'teaching_news', 'sys_data_log',
})
_WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_DIRECTIVE = re.compile(r'[ \t]*DELIMITER[ \t]+(\S+)[ \t]*(?:\r?\n|$)', re.I)
_COMMENT = re.compile(r'--(?=\s|$)[^\n]*|#[^\n]*|/\*.*?\*/', re.S)
_QUOTED = re.compile(r"'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"|`(?:``|[^`])*`", re.S)


def _statements(text):
    """Recognize fixture command heads without treating literals as SQL.

    Respect mysql-client DELIMITER blocks so stored routine/trigger definitions
    containing source-table writes do not look like executed fixture mutations.
    This is a small fixture recognizer, not a general SQL parser.
    """
    tokens, delimiter, position = [], ';', 0
    while position < len(text):
        if position == 0 or text[position - 1] == '\n':
            directive = _DIRECTIVE.match(text, position)
            if directive:
                delimiter = directive.group(1)
                position = directive.end()
                continue
        if text[position].isspace():
            position += 1
            continue
        comment = _COMMENT.match(text, position)
        if comment:
            position = comment.end()
            continue
        quoted = _QUOTED.match(text, position)
        if quoted:
            value = quoted.group()
            tokens.append(value[1:-1].replace('``', '`').lower() if value.startswith('`') else None)
            position = quoted.end()
            continue
        if text.startswith(delimiter, position):
            if tokens:
                yield tokens
            tokens = []
            position += len(delimiter)
            continue
        word = _WORD.match(text, position)
        if word:
            tokens.append(word.group().lower())
            position = word.end()
        else:
            tokens.append(text[position])
            position += 1
    if tokens:
        yield tokens


def mutates_media_source(statement):
    """Match only executed INSERT/REPLACE/UPDATE/DELETE/TRUNCATE fixture heads."""
    for tokens in _statements(statement):
        command, position = tokens[0], 1
        if command in {'insert', 'replace'}:
            while position < len(tokens) and tokens[position] in {'low_priority', 'delayed', 'high_priority', 'ignore'}:
                position += 1
            if position < len(tokens) and tokens[position] == 'into':
                position += 1
        elif command == 'update':
            while position < len(tokens) and tokens[position] in {'low_priority', 'ignore'}:
                position += 1
        elif command == 'delete':
            while position < len(tokens) and tokens[position] in {'low_priority', 'quick', 'ignore'}:
                position += 1
            if position >= len(tokens) or tokens[position] != 'from':
                continue
            position += 1
        elif command == 'truncate':
            if position < len(tokens) and tokens[position] == 'table':
                position += 1
        else:
            continue
        if position >= len(tokens):
            continue
        table = tokens[position]
        if tokens[position + 1:position + 2] == ['.']:
            if table != 'teachingopen_dev' or position + 2 >= len(tokens):
                continue
            table = tokens[position + 2]
        if table in MEDIA_SOURCES:
            return True
    return False


def rebuild_media_index_after_sql(api, statement):
    """Explicitly finish an owned raw-SQL fixture import; fail on repair denial."""
    if not mutates_media_source(statement):
        return False
    if not api.tokens.get('admin'):
        api.login('admin')
    status, payload, _ = api.request('POST', '/sys/localMediaReferences/rebuild', 'admin')
    if (status != 200 or not isinstance(payload, dict)
            or payload.get('success') is not True or payload.get('code') != 200):
        raise RuntimeError('Owned raw-SQL fixture media-index rebuild failed')
    return True


def media_index_snapshot(sql):
    """Digest the original derived rows and state without first rebuilding them."""
    statements = {
        'sys_local_file_reference':
            'SELECT HEX(source_type),HEX(source_id),HEX(field_name),HEX(reference_kind),'
            'HEX(reference_hash),HEX(reference_value) FROM teachingopen_dev.sys_local_file_reference '
            'ORDER BY source_type,source_id,field_name,reference_kind,reference_hash',
        'sys_local_file_reference_state':
            "SELECT id,version,IFNULL(HEX(static_domain),'NULL') "
            'FROM teachingopen_dev.sys_local_file_reference_state ORDER BY id',
    }
    return {table: hashlib.sha256(sql(statement).encode()).hexdigest()
            for table, statement in statements.items()}
