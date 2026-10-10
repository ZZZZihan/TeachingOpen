async (rootPage) => {
 const results=[];
 for(const port of [18112,18142,18150])for(const entry of ['index','player']){
  const page=await rootPage.context().newPage(),requests=[],errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(r.url().includes('/python/static/defaultPython.py'))requests.push(r.url());});
  await page.goto('http://127.0.0.1:'+port+'/python/'+entry+'.html?queryEncoding=uri&url=%2Fpython%2Fstatic%2FdefaultPython.py');
  await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
  const ready=await page.evaluate(()=>({phase:document.querySelector('#persistence-status').dataset.phase,code:document.querySelector('.ace_editor').env.editor.getValue(),runDisabled:Array.from(document.querySelectorAll('button')).find(b=>b.textContent.replace(/\s/g,'')==='运行').disabled}));
  if(requests.length!==1||ready.runDisabled||!ready.code.includes('Teaching Python Editor'))throw Error(JSON.stringify({port,entry,requests,ready}));
  await page.getByRole('button',{name:/运\s*行$/}).click();
  await page.waitForFunction(()=>document.querySelector('#output')?.textContent.includes('Teaching Python Editor'));
  const drawing=await page.evaluate(()=>({state:TeachingPythonExecution.getState().state,output:document.querySelector('#output').textContent}));
  const frameCount=await page.locator('iframe.python-execution-frame').count();
  const canvasCount=await page.frameLocator('iframe.python-execution-frame').locator('canvas').count();
  if(errors.length||frameCount!==1||canvasCount!==2)throw Error(JSON.stringify({errors,frameCount,canvasCount}));
  await page.evaluate(()=>TeachingPythonExecution.clear());
  await page.waitForFunction(()=>TeachingPythonExecution.getState().state==='idle');
  results.push({port,entry,pass:true,sourceRequests:requests.length,ready,drawing,frameCount,canvasCount,pageErrors:errors});
  await page.close();
 }
 return results;
}
