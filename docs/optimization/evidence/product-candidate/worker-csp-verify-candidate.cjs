async (page) => {
  const results = [];
  for (const port of [18112, 18142, 18150]) {
    await page.goto(`http://127.0.0.1:${port}/scratch3/index.html`);
    const response = await page.reload();
    await page.getByText('作品已打开，可以继续编辑。', {exact: true}).waitFor({timeout: 30000});
    await page.waitForFunction(() => window.__workerAudit.created.some(x => x.supportsFetch));
    results.push({port, csp: response.headers()['content-security-policy'], ...await page.evaluate(() => ({...window.__workerAudit, ready: document.body.textContent.includes('作品已打开，可以继续编辑。')}))});
  }
  return results;
}
