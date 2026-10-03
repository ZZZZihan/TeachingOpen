async (page) => {
  await page.addInitScript(() => {
    if (window.__workerAudit) return;
    const audit = window.__workerAudit = {created: [], violations: []};
    document.addEventListener('securitypolicyviolation', e => audit.violations.push({directive: e.effectiveDirective, blocked: e.blockedURI.startsWith('blob:') ? 'blob' : e.blockedURI}));
    window.Worker = new Proxy(window.Worker, {construct(Target, args) {
      const entry = {kind: String(args[0]).split(':')[0], messages: 0, errors: 0, supportsFetch: false, fetchedBuffers: 0};
      audit.created.push(entry);
      const worker = Reflect.construct(Target, args);
      worker.addEventListener('error', () => entry.errors++);
      worker.addEventListener('message', e => {
        entry.messages++;
        if (e.data && e.data.support && e.data.support.fetch) entry.supportsFetch = true;
        if (Array.isArray(e.data)) entry.fetchedBuffers += e.data.filter(x => x.buffer instanceof ArrayBuffer).length;
      });
      return worker;
    }});
  });
  const result = {};
  for (const [label, port] of [['old', 18150], ['new', 18151]]) {
    await page.goto(`http://127.0.0.1:${port}/scratch3/index.html`);
    await page.getByText('作品已打开，可以继续编辑。', {exact: true}).waitFor({timeout: 30000});
    await page.waitForFunction(() => window.__workerAudit.created.some(x => x.errors || x.supportsFetch));
    result[label] = await page.evaluate(() => ({...window.__workerAudit, ready: document.body.textContent.includes('作品已打开，可以继续编辑。'), canvas: document.querySelectorAll('canvas').length}));
  }
  return result;
}
