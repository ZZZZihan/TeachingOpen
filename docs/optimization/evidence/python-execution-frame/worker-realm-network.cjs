async (rootPage) => {
 const all=[];
 for(const path of ['player.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fseed.py','index.html?workId=seed-work']){
  const page=await rootPage.context().newPage();const consoleEvents=[],failures=[],errors=[];
  page.on('console',m=>consoleEvents.push({text:m.text()}));
  page.on('requestfailed',r=>failures.push({url:r.url(),failure:r.failure()?.errorText||''}));page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:18160/python/'+path);
  await page.waitForSelector('.ace_content');
  await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
  await page.addScriptTag({path:'web/tests/python-execution-frame/realm-network-probe.js'});
  const report=await page.evaluate(()=>TeachingPythonFrameRealmProbe.run());
  const result=await page.evaluate(({report,events,failures})=>TeachingPythonFrameRealmProbe.attachEvidence(report,events,failures),{report,events:consoleEvents,failures});
  all.push({path,result,pageErrors:errors});await page.close();
  if(!result.passed||errors.length)throw Error(JSON.stringify(all));
 }
 return all;
}
