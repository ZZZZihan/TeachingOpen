async (rootPage) => {
  // Playwright CLI run-code function. Open the owned Nginx fixture first and run
  // from the repository root. Uses only synthetic programs; never saves a work.
  const origin = new URL(rootPage.url()).origin
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw new Error('An owned loopback Nginx fixture is required')
  const reports = []
  for (const entry of ['index', 'player']) {
    // Separate synthetic tabs avoid navigating away from an unsaved program.
    const page = await rootPage.context().newPage()
    await page.goto(origin + '/python/' + entry + '.html?queryEncoding=uri&url=%2Fpython%2Fstatic%2FdefaultPython.py')
    await page.waitForFunction(() => document.querySelector('#persistence-status')?.dataset.phase === 'ready')
    await page.addScriptTag({ path: 'web/tests/python-execution-frame/browser-probe.js' })
    const basic = await page.evaluate(() => TeachingPythonFrameProbe.basic())
    if (basic.failed) throw new Error(JSON.stringify(basic))

    // A blocked runner still fires the iframe load event. Check recovery without
    // reloading the parent page or replacing the user's source.
    const code = 'print "RECOVERED_WITHOUT_RELOAD"\n'
    let workerStarts = 0
    const workerStarted = () => { workerStarts++ }
    page.on('worker', workerStarted)
    await page.route('**/python/runner.js', route => route.abort('failed'))
    let failure
    try {
      await page.evaluate(code => TeachingPythonFrameProbe.run(code), code)
      await page.waitForFunction(() => TeachingPythonExecution.getState().state === 'error', null, { timeout: 15000 })
      failure = await page.evaluate(() => ({
        status: document.querySelector('#python-execution-status').textContent,
        state: TeachingPythonExecution.getState().state,
        frames: document.querySelectorAll('iframe.python-execution-frame').length,
        code: TeachingPythonFrameProbe.component().code,
        stopDisabled: document.querySelector('#python-execution-stop').disabled
      }))
      if (failure.frames || !failure.stopDisabled || failure.code !== code || workerStarts) throw new Error(JSON.stringify({ failure, workerStarts }))
    } finally {
      await page.unroute('**/python/runner.js')
      page.off('worker', workerStarted)
    }
    // Click the actual Run control with the retained program still in the editor.
    await page.getByRole('button', { name: /运\s*行$/ }).click()
    await page.waitForFunction(() => TeachingPythonExecution.getState().state === 'completed')
    const recovered = await page.locator('#output').textContent()
    if (recovered !== 'RECOVERED_WITHOUT_RELOAD\n') throw new Error('Retry output: ' + recovered)
    await page.evaluate(() => TeachingPythonExecution.clear())

    // Retain a real drawing screenshot alongside protocol/output assertions.
    await page.evaluate(() => TeachingPythonFrameProbe.run('import turtle\nt = turtle.Turtle()\nt.forward(100)\nprint "NGINX_TURTLE_OK"\n'))
    await page.waitForFunction(() => TeachingPythonExecution.getState().state === 'completed')
    const canvases = await page.frameLocator('iframe.python-execution-frame').locator('canvas').count()
    if (canvases !== 2) throw new Error('Expected turtle drawing canvases')
    await page.screenshot({ path: 'output/playwright/nginx-python-' + new URL(origin).port + '-' + entry + '.png' })
    reports.push({ entry, basic, blockedRunner: { ...failure, workerStarts }, recovered, canvases })
    await page.evaluate(() => TeachingPythonExecution.clear())
    await page.close()
  }
  return { origin, reports }
}
