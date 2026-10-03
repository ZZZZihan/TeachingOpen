async (page) => {
  const data = {"file": "http://127.0.0.1:18155/fixtures/seed.py?revision=1&label=a+b", "links": {"teacher": "http://127.0.0.1:18155/python/player.html?queryEncoding=uri&lang=turtle&url=http%3A%2F%2F127.0.0.1%3A18155%2Ffixtures%2Fseed.py%3Frevision%3D1%26label%3Da%2Bb", "course": "http://127.0.0.1:18155/python/player.html?lang=turtle&url=http%3A%2F%2F127.0.0.1%3A18155%2Ffixtures%2Fseed.py%3Frevision%3D1%26label%3Da%2Bb&queryEncoding=uri", "community": "http://127.0.0.1:18155/python/player.html?queryEncoding=uri&lang=turtle&url=http%3A%2F%2F127.0.0.1%3A18155%2Ffixtures%2Fseed.py%3Frevision%3D1%26label%3Da%2Bb"}, "scope": "Synthetic loopback HTTP fixture; not a Java API or real-role acceptance."};
  const results = [];
  for (const [caller, url] of Object.entries(data.links)) {
    const files = [], errors = [];
    const onResponse = response => {if(response.url().includes('/fixtures/')) files.push({url:response.url(),status:response.status()});};
    const onError = error => errors.push(error.message);
    page.on('response', onResponse); page.on('pageerror', onError);
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('.ace_content')?.textContent.includes('Python persistence fixture'));
    await page.getByRole('button', {name:'运 行', exact:true}).click();
    await page.waitForFunction(() => document.getElementById('output').textContent.includes('42'));
    const output = await page.getByLabel('程序输出', {exact:true}).textContent();
    await page.getByRole('button', {name:'清 空', exact:true}).click();
    const cleared = await page.getByLabel('程序输出', {exact:true}).textContent();
    await page.getByRole('button', {name:'运 行', exact:true}).click();
    await page.waitForFunction(() => document.getElementById('output').textContent.includes('42'));
    const rerun = await page.getByLabel('程序输出', {exact:true}).textContent();
    page.off('response', onResponse); page.off('pageerror', onError);
    if (files.length !== 2 || files.some(x => x.url !== data.file || x.status !== 200)) throw Error(caller+' wrong requests '+JSON.stringify(files));
    if (output.trim() !== 'Python persistence fixture\n42' || cleared !== '' || rerun !== output || errors.length) throw Error(caller+' unexpected output/errors');
    results.push({caller,files,output,cleared,rerun,pageErrors:errors});
  }
  await page.screenshot({path:'output/playwright/python-preview-url/new-player.png',scale:'css'});
  return results;
}
