async (page) => {
 const all=[];
 for(const [entry,path] of [['player','player.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fseed.py'],['editor','index.html?workId=seed-work']]){
  await page.goto('http://127.0.0.1:18160/python/'+path);
  await page.waitForFunction(()=>document.querySelector('.ace_content')?.textContent.includes('Python persistence fixture'));
  await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
  const errors=[];const onError=e=>errors.push(String(e));page.on('pageerror',onError);
  const basic=await page.evaluate(()=>TeachingPythonFrameProbe.basic());
  page.off('pageerror',onError);
  all.push({entry,basic,pageErrors:errors});
  if(basic.failed||errors.length)throw Error(JSON.stringify(all));
 }
 return all;
}
