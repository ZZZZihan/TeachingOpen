const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process')
const phase = process.argv[2], output = process.argv[3]
if (!['baseline', 'browser', 'stale-confirm'].includes(phase) || !output) throw new Error('Usage: node web/tests/admin-course-preview/run-check.cjs baseline|browser|stale-confirm OUTPUT_JSON')
const target = path.resolve(output)
if (fs.existsSync(target)) throw new Error('Evidence exists; use a fresh output path to retain previous results')
const wrapper = path.join(process.env.CODEX_HOME || path.join(process.env.HOME, '.codex'), 'skills/playwright/scripts/playwright_cli.sh')
const result = cp.spawnSync(wrapper, ['--session', 'admin-course', 'run-code', fs.readFileSync(path.join(__dirname, `verify-${phase}.js`), 'utf8')], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 })
fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target.replace(/\.json$/, '') + '.cli.txt', (result.stdout || '') + (result.stderr || ''))
const match = result.stdout && result.stdout.match(/### Result\s*\n([^\n]+)/)
if (result.status !== 0 || !match) { console.error(result.stdout, result.stderr); process.exit(1) }
const data = JSON.parse(match[1]); fs.writeFileSync(target, JSON.stringify(data, null, 2))
console.log(JSON.stringify({ evidence: target, passed: data.passed, total: data.total, error: data.error, shots: data.shots?.length, observations: data.observations?.length }))
if (data.error || data.cases?.some(value => !value.passed)) process.exitCode = 1
