const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { execFileSync, spawnSync } = require('node:child_process')
const { repository } = require('./harness.cjs')
const args = process.argv.slice(2)
const option = name => args[args.indexOf(name) + 1]
if (!args.includes('--output') || !option('--output')) throw new Error('Required --output <report.json>; optional --ref <git-ref> / --all')
const output = path.resolve(option('--output')), ref = args.includes('--ref') ? option('--ref') : ''
if (ref && args.includes('--all')) throw new Error('--ref is limited to isolation suites; the existing full suites read their current workspace')
const sourceFiles = [
  'web/public/python/execution.js', 'web/public/python/runner.js', 'web/public/python/runner-loader.js',
  'web/public/python/worker.js', 'web/public/python/worker-turtle.js', 'web/public/python/turtle-renderer.js',
  'web/public/python/execution.css', 'web/public/python/runner.css',
  'web/public/python/output.js', 'web/public/python/static/js/vendor.js',
  'web/public/python/static/js/app.js', 'web/public/python/static/js/appPlayer.js',
  'web/public/python/index.html', 'web/public/python/player.html'
]
const missing = []
const hash = data => crypto.createHash('sha256').update(data).digest('hex')
const hashes = Object.fromEntries(sourceFiles.map(file => {
  try {
    const data = ref
      ? execFileSync('git', ['show', ref + ':' + file], { cwd: repository, stdio: ['ignore', 'pipe', 'pipe'] })
      : fs.readFileSync(path.join(repository, file))
    return [file, hash(data)]
  } catch (error) { missing.push(file); return [file, null] }
}))
const testFiles = args.includes('--all')
  ? fs.readdirSync(path.join(repository, 'web/tests')).filter(file => file.endsWith('.test.cjs')).sort().map(file => 'web/tests/' + file)
  : ['web/tests/python-execution-frame.test.cjs', 'web/tests/python-worker-turtle.test.cjs', ...(ref ? [] : ['web/tests/python-output.test.cjs', 'web/tests/python-preview-url.test.cjs'])]
const suiteFiles = [...testFiles, 'web/tests/python-execution-frame/harness.cjs', 'web/tests/python-execution-frame/runtime-fixture.cjs', 'web/tests/python-execution-frame/run-report.cjs']
const suiteHashes = Object.fromEntries(suiteFiles.map(file => [file, hash(fs.readFileSync(path.join(repository, file)))]))
const command = ['--test', '--test-reporter=tap', ...testFiles]
const result = spawnSync(process.execPath, command, { cwd: repository, env: { ...process.env, PYTHON_EXECUTION_FRAME_SOURCE_REF: ref }, encoding: 'utf8' })
const tap = result.stdout + result.stderr
const count = name => Number((tap.match(new RegExp('^# ' + name + ' (\\d+)$', 'm')) || [])[1] || 0)
const changedDuringRun = ref ? [] : sourceFiles.filter(file => {
  try { return hash(fs.readFileSync(path.join(repository, file))) !== hashes[file] } catch (error) { return hashes[file] !== null }
})
const exitCode = result.status === null || count('tests') === 0 || changedDuringRun.length ? 1 : result.status
const tapPath = output.replace(/\.json$/, '') + '.tap'
fs.writeFileSync(tapPath, tap)
const report = {
  command: [process.execPath, ...command], source_ref: ref || 'working tree',
  head_sha: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repository, encoding: 'utf8' }).trim(),
  node_version: process.version, exit_code: exitCode, tests: count('tests'), passed: count('pass'), failed: count('fail'), skipped: count('skipped'),
  source_sha256: hashes, absent_source_files: missing, source_changed_during_run: changedDuringRun, suite_sha256: suiteHashes, tap_path: tapPath,
  scope: 'Actual shipped component methods, coordinator and renderer-host protocol with controlled DOM/MessageChannel/clock. Real inherited Skulpt, Worker entry, turtle proxy and original turtle renderer execute finite Python2 in separate Node VM realms. Canvas drawing is a no-op surface. Controlled transport/clock is not browser scheduling, OS CPU termination, pixels, production or human acceptance.'
}
fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n')
process.stdout.write(JSON.stringify({ report: output, tap: tapPath, source_ref: report.source_ref, exit_code: exitCode, tests: report.tests, passed: report.passed, failed: report.failed }, null, 2) + '\n')
process.exitCode = exitCode
