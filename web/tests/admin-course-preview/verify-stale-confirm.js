async page => {
  const base = 'http://127.0.0.1:18137', cases = [], shots = [], errors = []
  const check = (name, ok) => { cases.push({ case: name, passed: !!ok }); if (!ok) throw new Error(name) }
  const capture = error => errors.push(String(error)); page.on('pageerror', capture)
  try {
    await page.request.post(base + '/__reset')
    await page.setViewportSize({ width: 1440, height: 1000 })
    const url = base + '/after/?phase=stale-confirm'
    await page.goto(url + '#/course/courseUnit?courseId=synthetic-course-1')
    await page.locator('.unit-row').first().waitFor()
    await page.getByTestId('select-all').check(); await page.getByTestId('batch-delete').click()
    await page.getByRole('button', { name: '删除单元', exact: true }).waitFor()
    // Address-bar navigation changes the route while the same component is retained.
    // No app DOM state, authentication token or production API is injected.
    await page.goto(url + '#/course/courseUnit?courseId=synthetic-course-2')
    await page.getByTestId('list-loading').waitFor({ state: 'hidden' }); await page.locator('.unit-row').first().waitFor()
    check('same unit component route change clears old selection', !await page.getByTestId('select-all').isChecked())
    await page.getByRole('button', { name: '删除单元', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    const state = await (await page.request.get(base + '/__state')).json()
    check('stale route confirmation dispatches no DELETE', state.requests.filter(r => r.method === 'DELETE').length === 0)
    check('new course scope remains visible after declining old confirmation', await page.locator('.unit-row').count() === 9 && state.requests.at(-1).params.courseId === 'synthetic-course-2')
    const screenshot = 'output/playwright/admin-course-after-unit-stale-confirm.png'; await page.screenshot({ path: screenshot }); shots.push(screenshot)
    check('stale confirmation guard has no uncaught browser exception', errors.length === 0)
    return { cases, passed: cases.length, total: cases.length, shots, errors, requests: state.requests, limitation: 'Only the synthetic loopback server; actual Vue/Ant confirm and route watcher.' }
  } catch (error) { cases.push({ case: 'stale confirmation flow completes', passed: false }); return { cases, passed: cases.filter(c => c.passed).length, total: cases.length, shots, errors, error: String(error) } }
  finally { page.off('pageerror', capture) }
}
