/* Load into an owned loopback editor/player with Playwright CLI addScriptTag.
 * Calls the mounted shipped component; every program is finite. No credentials.
 */
(function () {
  'use strict'
  var results = []
  function wait (milliseconds) { return new Promise(function (resolve) { setTimeout(resolve, milliseconds) }) }
  function component () {
    var seen = new Set(), queue = []
    document.querySelectorAll('*').forEach(function (node) { if (node.__vue__) queue.push(node.__vue__) })
    while (queue.length) {
      var value = queue.shift()
      if (!value || seen.has(value)) continue
      seen.add(value)
      if (value.$options && value.$options.name === 'PythonEditor') return value
      ;(value.$children || []).forEach(function (child) { queue.push(child) })
    }
    throw new Error('The actual mounted PythonEditor component was not found')
  }
  function output () { return document.getElementById('output').textContent }
  function state () { return window.TeachingPythonExecution.getState() }
  function frame () { return Array.from(document.querySelectorAll('#mycanvas iframe')).find(function (node) { return node.style.display !== 'none' }) || null }
  async function until (condition, label, limit) {
    var end = performance.now() + (limit || 5000)
    while (!condition()) { if (performance.now() > end) throw new Error('Timed out: ' + label); await wait(20) }
  }
  function check (value, label) { if (!value) throw new Error(label) }
  async function run (code) {
    var host = component()
    host.setCode(code)
    // The inherited Ace setCodeContent applies on a 300ms timeout. Reading the
    // actual runit after that delay exercises the same path as a user click.
    await wait(350)
    var previous = frame()
    host.runit()
    await until(function () { return frame() && frame() !== previous || /不可用|失败|不支持/.test(document.getElementById('python-execution-status').textContent) }, 'new runner frame after retirement')
    return frame()
  }
  async function record (name, callback) {
    var started = performance.now()
    try { var evidence = await callback(); results.push({ name: name, pass: true, elapsedMs: Math.round(performance.now() - started), evidence: evidence }) }
    catch (error) { results.push({ name: name, pass: false, elapsedMs: Math.round(performance.now() - started), error: String(error) }) }
    component().clear()
    await until(function () { return !document.querySelector('#mycanvas iframe') && state().state === 'idle' }, 'confirmed cleanup')
  }
  async function basic () {
    results = []
    await record('actual component finite Python2 and literal HTML output', async function () {
      await run('print 6 * 7\nprint "<img src=x onerror=alert(1)> &lt;b&gt; 中文"\n')
      await until(function () { return output().indexOf('42') !== -1 && state().state === 'completed' }, 'finite program')
      check(!document.getElementById('output').querySelector('img'), 'printed HTML parsed as DOM')
      var node = frame(); check(node && node.getAttribute('sandbox') === 'allow-scripts', 'opaque sandbox is required')
      return { output: output(), sandbox: node.getAttribute('sandbox'), state: state(), frameRect: { width: node.clientWidth, height: node.clientHeight } }
    })
    await record('input waits and submits through parent form', async function () {
      await run('name = raw_input("姓名：")\nprint "hello " + name\n')
      var form = document.getElementById('python-execution-input-form')
      await until(function () { return !form.hidden }, 'input form')
      var before = state(); await wait(300); var after = state()
      var input = form.querySelector('input'); input.value = '测试输入'
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      await until(function () { return output().indexOf('hello 测试输入') !== -1 && state().state === 'completed' }, 'input response and completion')
      return { before: before, after: after, output: output(), formHidden: form.hidden }
    })
    await record('cancel input destroys old frame and a rerun succeeds', async function () {
      var old = await run('name = raw_input("取消测试")\nprint "OLD_INPUT_AFTER"\n')
      var form = document.getElementById('python-execution-input-form')
      await until(function () { return !form.hidden }, 'input cancel form')
      document.getElementById('python-execution-input-cancel').click()
      await until(function () { return !old.isConnected && state().state === 'stopped' }, 'input cancellation termination acknowledgment')
      check(!old.isConnected, 'cancel keeps the old runner attached')
      await run('print "fresh after cancel"\n')
      await until(function () { return output().indexOf('fresh after cancel') !== -1 }, 'fresh run')
      check(output().indexOf('OLD_INPUT_AFTER') === -1, 'old input run appended output')
      return { output: output(), state: state() }
    })
    await record('repeated run replaces a sleeping runner', async function () {
      var old = await run('import time\ntime.sleep(0.7)\nprint "OLD_SLEEP_AFTER"\n')
      await run('print "fresh after replace"\n')
      await until(function () { return output().indexOf('fresh after replace') !== -1 }, 'replacement output')
      await wait(800)
      check(!old.isConnected, 'repeat run keeps old frame')
      check(output().indexOf('OLD_SLEEP_AFTER') === -1, 'old sleeping run appended output')
      return { output: output(), state: state() }
    })
    await record('bounded 500ms JS busy work leaves parent timer and Stop usable', async function () {
      var heartbeats = [], start = performance.now(), timer = setInterval(function () { heartbeats.push(Math.round(performance.now() - start)) }, 30)
      var old
      try {
        old = await run('import time\nprint "BUSY_ARMED"\ntime.sleep(0.15)\njseval("(function(){var start=Date.now(),n=0,marked=false;while(Date.now()-start<500){n++;if(!marked&&Date.now()-start>=20){marked=true;console.log(\\"FRAME_PROBE_BUSY_ENTERED at=\\"+Date.now()+\\" elapsed=\\"+(Date.now()-start)+\\" iterations=\\"+n)}};console.log(\\"FRAME_PROBE_BUSY_DONE at=\\"+Date.now());return 1})()")\nprint "BUSY_AFTER"\n')
        await until(function () { return output().indexOf('BUSY_ARMED') !== -1 }, 'busy program armed')
        await wait(200)
        var stoppedAt = performance.now(), stoppedAtEpochMs = Date.now(); document.getElementById('python-execution-stop').click()
        await until(function () { return !old.isConnected && state().state === 'stopped' }, 'Stop acknowledgment')
        await wait(700)
        check(!old.isConnected, 'Stop keeps old runner attached')
        check(output().indexOf('BUSY_AFTER') === -1, 'stopped runner appended output')
        return { heartbeats: heartbeats, stoppedAtMs: Math.round(stoppedAt - start), stoppedAtEpochMs: stoppedAtEpochMs, state: state(), cpuTermination: 'unverified', evidenceLimit: 'Require external CLI console FRAME_PROBE_BUSY_ENTERED and FRAME_PROBE_BUSY_DONE timestamps. Frame removal and missing output do not establish CPU termination.' }
      } finally { clearInterval(timer) }
    })
    await record('turtle square, text and undo use runner DOM', async function () {
      await run('import turtle\nt = turtle.Turtle()\nt.speed(0)\nt.setundobuffer(100)\nfor i in range(4):\n    t.forward(60)\n    t.right(90)\nt.write("Turtle 文本")\nt.forward(20)\nt.undo()\nprint "turtle finished"\n')
      await until(function () { return output().indexOf('turtle finished') !== -1 }, 'turtle output', 10000)
      return { output: output(), state: state(), opaqueFramePresent: !!frame(), evidenceLimit: 'Canvas pixels and interaction require the accompanying browser screenshot / key-mouse probe.' }
    })
    return { userAgent: navigator.userAgent, url: location.href, results: results, passed: results.filter(function (item) { return item.pass }).length, failed: results.filter(function (item) { return !item.pass }).length }
  }
  var fixtures = {
    outputLimit: 'print "x" * 100000\nprint "END_OUTPUT"\n',
    turtleEvents: 'import turtle\ns = turtle.Screen()\nt = turtle.Turtle()\nt.speed(0)\ndef clicked(x, y):\n    print "MOUSE_CALLBACK"\n    t.goto(x, y)\ndef key():\n    print "KEY_CALLBACK"\n    t.forward(10)\ns.onclick(clicked)\ns.onkey(key, "a")\ns.listen()\nprint "EVENTS_READY"\n',
    realm: 'print jseval("(function(){var r=[];try{parent.document.body.dataset.childMutation=1;r.push(\"parent-access\")}catch(e){r.push(e.name)};try{localStorage.setItem(\"synthetic-canary\",\"changed\");r.push(\"storage-write\")}catch(e){r.push(e.name)};try{document.cookie=\"synthetic-canary=changed\";r.push(\"cookie-write\")}catch(e){r.push(e.name)};return r.join(\",\")})()")\n'
  }
  function attachConsoleEvidence (report, events) {
    var busy = report.results.find(function (item) { return item.name.indexOf('bounded 500ms') === 0 })
    if (!busy || !busy.evidence) return report
    var lines = (events || []).map(function (event) { return typeof event === 'string' ? event : event.text || '' })
    var entered = lines.find(function (line) { return /FRAME_PROBE_BUSY_ENTERED at=\d+ elapsed=\d+ iterations=\d+/.test(line) })
    var done = lines.find(function (line) { return /FRAME_PROBE_BUSY_DONE at=\d+/.test(line) })
    busy.evidence.externalConsole = { entered: entered || null, done: done || null }
    var endTime = done && Number(done.match(/at=(\d+)/)[1])
    if (entered && endTime > busy.evidence.stoppedAtEpochMs) {
      busy.evidence.cpuImmediateStop = 'not observed: finite computation completed after Stop'
      busy.evidence.cpuTermination = 'unverified: 500ms work may finish within a browser termination grace period; require longer bounded paired control'
    } else {
      busy.evidence.cpuTermination = 'unverified: missing completion markers cannot prove CPU termination'
    }
    report.passed = report.results.filter(function (item) { return item.pass }).length
    report.failed = report.results.filter(function (item) { return !item.pass }).length
    return report
  }
  window.TeachingPythonFrameProbe = { basic: basic, run: run, component: component, fixtures: fixtures, output: output, state: state, attachConsoleEvidence: attachConsoleEvidence }
}())
