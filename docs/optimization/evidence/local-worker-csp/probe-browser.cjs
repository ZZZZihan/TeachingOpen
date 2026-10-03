async (page) => {
  return await page.evaluate(async () => {
    const app = JSON.parse(JSON.stringify(window.__workerAudit));
    const violations = [];
    const listener = e => violations.push({directive: e.effectiveDirective, blocked: e.blockedURI});
    document.addEventListener('securitypolicyviolation', listener);
    const asset = '/scratch3/static/assets/bb7c6671cf8cdffe1001dc509d20881c.svg';
    const direct = await (await fetch(asset)).arrayBuffer();
    const hash = async buffer => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))).map(x => x.toString(16).padStart(2, '0')).join('');
    const result = {app, asset, assetBytes: direct.byteLength, assetSha256: await hash(direct)};
    const source = await (await fetch('/scratch3/1ec1a83be92ce3c05727.worker.js')).text();
    const blob = URL.createObjectURL(new Blob([source], {type: 'text/javascript'}));
    for (const [kind, url] of [['self', '/scratch3/1ec1a83be92ce3c05727.worker.js'], ['blob', blob]]) {
      let worker;
      try {
        const buffer = await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('Worker response timeout')), 8000);
          worker = new Worker(url);
          worker.onerror = () => {clearTimeout(timeout); reject(new Error('Worker error'));};
          worker.onmessage = event => {
            if (event.data.support) worker.postMessage({id: 'controlled-asset-probe', url: location.origin + asset, options: {}});
            else if (Array.isArray(event.data)) {
              clearTimeout(timeout);
              const item = event.data.find(x => x.id === 'controlled-asset-probe');
              item && item.buffer ? resolve(item.buffer) : reject(new Error('Missing asset buffer'));
            }
          };
        });
        result[kind + 'Worker'] = {bytes: buffer.byteLength, sha256: await hash(buffer)};
      } finally {if (worker) worker.terminate();}
    }
    URL.revokeObjectURL(blob);
    const addScript = async src => {
      const script = document.createElement('script');
      try {return await new Promise(resolve => {script.onload = () => resolve('loaded'); script.onerror = () => resolve('blocked'); script.src = src; document.head.append(script);});}
      finally {script.remove();}
    };
    const scriptBlob = URL.createObjectURL(new Blob(['window.__forbiddenBlobScript = true'], {type: 'text/javascript'}));
    result.blobScript = await addScript(scriptBlob);
    result.blobScriptRan = window.__forbiddenBlobScript === true;
    URL.revokeObjectURL(scriptBlob);
    result.crossOriginScript = await addScript('http://127.0.0.1:18152/worker-csp-script-probe.js');
    try {await fetch('http://127.0.0.1:18152/worker-csp-connect-probe'); result.crossOriginFetch = 'allowed';}
    catch {result.crossOriginFetch = 'blocked';}
    let dataWorker;
    result.dataWorker = await new Promise(resolve => {
      try {dataWorker = new Worker('data:text/javascript,postMessage(1)'); dataWorker.onmessage = () => resolve('allowed'); dataWorker.onerror = () => resolve('blocked');}
      catch {resolve('blocked');}
    });
    if (dataWorker) dataWorker.terminate();
    await new Promise(resolve => setTimeout(resolve, 100));
    document.removeEventListener('securitypolicyviolation', listener);
    result.violations = violations;
    result.ready = document.body.textContent.includes('作品已打开，可以继续编辑。');
    return result;
  });
}
