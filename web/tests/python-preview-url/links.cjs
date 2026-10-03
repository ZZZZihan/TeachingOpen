// Produce links through the three actual SFC callers for a loopback-only browser probe.
const { caller } = require('./harness.cjs')
const origin = process.argv[2]
if (!origin || new URL(origin).hostname !== '127.0.0.1') throw new Error('Use an explicitly owned 127.0.0.1 fixture origin')
const file = origin + '/fixtures/seed.py?revision=1&label=a+b'
const links = Object.fromEntries(['teacher', 'course', 'community'].map(name => [name, origin + caller(name, origin).link(file)]))
process.stdout.write(JSON.stringify({ file, links, scope: 'Synthetic loopback HTTP fixture; not a Java API or real-role acceptance.' }, null, 2) + '\n')
