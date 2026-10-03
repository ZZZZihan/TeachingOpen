/* Inject into an owned loopback page after browser-probe.js. No credentials or
 * unbounded programs. Network denial requires external browser evidence. */
(function () {
  'use strict'
  function wait (ms) { return new Promise(function (resolve) { setTimeout(resolve, ms) }) }
  async function run () {
    if (!window.TeachingPythonFrameProbe) throw new Error('Load browser-probe.js first')
    if (location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') throw new Error('Probe is limited to an owned loopback fixture')
    var id = 'python-frame-canary-' + Date.now(), key = id, original = localStorage.getItem(key)
    var element = document.getElementById('mycanvas'), oldAttribute = element.getAttribute('data-synthetic-canary')
    var sentinel = 'parent-' + id, url = new URL('/__python_frame_network_canary', location.href)
    url.searchParams.set('id', id)
    localStorage.setItem(key, sentinel); element.setAttribute('data-synthetic-canary', sentinel)
    var js = '(function(){var r={};function check(name,fn){try{r[name]={ok:true,value:fn()}}catch(e){r[name]={ok:false,error:e.name}}}' +
      'check("document",function(){return typeof document});' +
      'check("parentDOM",function(){parent.document.getElementById("mycanvas").setAttribute("data-synthetic-canary","changed");return "changed"});' +
      'check("storage",function(){localStorage.setItem(' + JSON.stringify(key) + ',"changed");return "changed"});' +
      'check("nestedWorker",function(){return typeof Worker});' +
      'addEventListener("securitypolicyviolation",function(e){console.log("FRAME_REALM_CSP ' + id + ' "+e.effectiveDirective+" "+e.blockedURI)});' +
      'fetch(' + JSON.stringify(url.href) + ',{credentials:"omit",mode:"no-cors"}).then(function(){console.log("FRAME_REALM_NETWORK ' + id + ' ALLOWED")},function(e){console.log("FRAME_REALM_NETWORK ' + id + ' REJECTED "+e.name)});' +
      'return JSON.stringify(r)})()'
    var code = 'print jseval(' + JSON.stringify(js) + ')\nprint "REALM_PROBE_FINISHED"\n'
    try {
      await TeachingPythonFrameProbe.run(code)
      var end = Date.now() + 5000
      while (TeachingPythonFrameProbe.output().indexOf('REALM_PROBE_FINISHED') < 0 || TeachingPythonFrameProbe.state().state !== 'completed') {
        if (Date.now() > end) throw new Error('Finite realm probe did not complete')
        await wait(20)
      }
      await wait(200)
      var text = TeachingPythonFrameProbe.output(), value = JSON.parse(text.split('\n')[0])
      var unchanged = element.getAttribute('data-synthetic-canary') === sentinel && localStorage.getItem(key) === sentinel
      return { id: id, networkURL: url.href, realm: value, canariesUnchanged: unchanged,
        realmPassed: unchanged && value.document.value === 'undefined' && !value.parentDOM.ok && !value.storage.ok && value.nestedWorker.value === 'undefined',
        network: 'unverified: attach external console and request-failure evidence', state: TeachingPythonFrameProbe.state(), output: text }
    } finally {
      await window.TeachingPythonExecution.clear()
      if (original === null) localStorage.removeItem(key); else localStorage.setItem(key, original)
      if (oldAttribute === null) element.removeAttribute('data-synthetic-canary'); else element.setAttribute('data-synthetic-canary', oldAttribute)
    }
  }
  function attachEvidence (report, consoleEvents, requestFailures) {
    var lines = (consoleEvents || []).map(function (event) { return typeof event === 'string' ? event : event.text || '' })
    var marker = 'FRAME_REALM_NETWORK ' + report.id
    var rejected = lines.some(function (line) { return line.indexOf(marker + ' REJECTED') >= 0 })
    var allowed = lines.some(function (line) { return line.indexOf(marker + ' ALLOWED') >= 0 })
    var csp = lines.filter(function (line) {
      return line.indexOf('FRAME_REALM_CSP ' + report.id) >= 0 && /connect-src/.test(line) ||
        line.indexOf(report.networkURL) >= 0 && /Content Security Policy|connect-src|content-security-policy/i.test(line)
    })
    var failures = (requestFailures || []).filter(function (item) { return item.url === report.networkURL })
    var blockedFailure = failures.some(function (item) { return /CSP|CONTENT_SECURITY_POLICY|BLOCKED_BY_CSP/i.test(item.failure || '') })
    report.networkConsole = lines.filter(function (line) { return line.indexOf(marker) >= 0 })
    report.cspEvidence = csp; report.requestFailures = failures
    report.network = allowed ? 'failed: synthetic fetch completed' : rejected && (csp.length || blockedFailure)
      ? 'passed: synthetic fetch rejected with browser CSP evidence' : 'unverified: no matched browser CSP denial evidence'
    report.passed = report.realmPassed && report.network.indexOf('passed:') === 0
    return report
  }
  window.TeachingPythonFrameRealmProbe = { run: run, attachEvidence: attachEvidence }
}())
