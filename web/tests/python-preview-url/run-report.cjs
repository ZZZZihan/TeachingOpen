const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { execFileSync, spawnSync } = require('node:child_process')
const { repository } = require('./harness.cjs')
const args = process.argv.slice(2)
const option = name => args[args.indexOf(name) + 1]
if (!args.includes('--output') || !option('--output')) throw new Error('Required --output <report.json>; optional --ref <git-ref>')
const output = path.resolve(option('--output'))
const ref = args.includes('--ref') ? option('--ref') : ''
const sourceFiles = [
  'web/public/python/static/js/app.js', 'web/public/python/static/js/appPlayer.js',
  'web/public/python/persistence.js', 'web/public/python/player.html',
  'web/src/views/teaching/modules/TeachingWorkPreviewModal.vue',
  'web/src/views/account/course/modules/UnitViewModal.vue', 'web/src/views/home/WorkDetail.vue'
]
const hashes = Object.fromEntries(sourceFiles.map(file => {
  const data = ref ? execFileSync('git', ['show', ref + ':' + file], { cwd: repository }) : fs.readFileSync(path.join(repository, file))
  return [file, crypto.createHash('sha256').update(data).digest('hex')]
}))
const suiteFiles = ['web/tests/python-preview-url.test.cjs', 'web/tests/python-preview-url/harness.cjs', 'web/tests/python-preview-url/run-report.cjs']
const suiteHashes = Object.fromEntries(suiteFiles.map(file => [file, crypto.createHash('sha256').update(fs.readFileSync(path.join(repository, file))).digest('hex')]))
const command = ['--test', '--test-reporter=tap', 'web/tests/python-preview-url.test.cjs']
const result = spawnSync(process.execPath, command, {
  cwd: repository, env: { ...process.env, PYTHON_PREVIEW_SOURCE_REF: ref }, encoding: 'utf8'
})
const tap = result.stdout + result.stderr
const count = name => Number((tap.match(new RegExp('^# ' + name + ' (\\d+)$', 'm')) || [])[1] || 0)
const exitCode = result.status === null || count('tests') === 0 ? 1 : result.status
const tapPath = output.replace(/\.json$/, '') + '.tap'
fs.writeFileSync(tapPath, tap)
const report = {
  command: [process.execPath, ...command], source_ref: ref || 'working tree',
  head_sha: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repository, encoding: 'utf8' }).trim(),
  node_version: process.version, exit_code: exitCode, tests: count('tests'),
  passed: count('pass'), failed: count('fail'), skipped: count('skipped'),
  source_sha256: hashes, suite_sha256: suiteHashes, tap_path: tapPath,
  scope: 'Actual prebuilt component methods and actual SFC caller methods in controlled Node VM; no Java API, authenticated browser or human acceptance.'
}
fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n')
process.stdout.write(JSON.stringify({ report: output, tap: tapPath, ...Object.fromEntries(['source_ref', 'exit_code', 'tests', 'passed', 'failed', 'skipped'].map(key => [key, report[key]])) }, null, 2) + '\n')
process.exitCode = exitCode
