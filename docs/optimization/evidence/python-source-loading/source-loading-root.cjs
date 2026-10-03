async (rootPage) => {
 const results=[];
 const BASE='http://127.0.0.1:18160';
 const state=page=>page.evaluate(()=>({
  phase:document.querySelector('#persistence-status')?.dataset.phase,
  message:document.querySelector('#persistence-status')?.textContent,
  retryVisible:!!document.querySelector('#retry-load:not([hidden])'),
  code:document.querySelector('.ace_editor')?.env?.editor?.getValue(),
  readOnly:document.querySelector('.ace_editor')?.env?.editor?.getReadOnly(),
  runDisabled:Array.from(document.querySelectorAll('button')).find(b=>b.textContent.replace(/\s/g,'')==='运行')?.disabled,
  editors:document.querySelectorAll('.ace_editor').length,
  overflow:document.documentElement.scrollWidth>innerWidth
 }));
 for(const entry of ['player','index'])for(const scenario of ['normal','slow','404-retry','network-retry','invalid-url','html-response','empty-file']){
  const page=await rootPage.context().newPage(),requests=[],errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(r.url().includes('/fixtures/seed.py'))requests.push({url:r.url(),method:r.method(),hasAccessToken:!!r.headers()['x-access-token']});});
  let attempts=0;
  await page.route('**/fixtures/seed.py*',async route=>{
   attempts++;
   if(scenario==='slow')await new Promise(r=>setTimeout(r,1200));
   if(attempts===1&&scenario==='404-retry')return route.fulfill({status:404,contentType:'text/plain',body:'Fixture missing'});
   if(attempts===1&&scenario==='network-retry')return route.abort('failed');
   if(scenario==='html-response')return route.fulfill({status:200,contentType:'text/html',body:'<html>Fixture sign-in page</html>'});
   if(scenario==='empty-file')return route.fulfill({status:200,contentType:'text/plain',body:''});
   return route.continue();
  });
  const source=scenario==='invalid-url'?'javascript:alert(1)':BASE+'/fixtures/seed.py?part=a%2Bb&label=50%25';
  await page.goto(BASE+'/python/'+entry+'.html?queryEncoding=uri&lang=turtle&url='+encodeURIComponent(source));
  await page.waitForSelector('.ace_editor');
  let during;
  if(scenario==='slow'){
   await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='loading');
   during=await state(page);
   if(!during.runDisabled||!during.readOnly)throw Error('loading not locked '+JSON.stringify({entry,during}));
  }
  const fails=['404-retry','network-retry','invalid-url','html-response'].includes(scenario);
  await page.waitForFunction(phase=>document.querySelector('#persistence-status')?.dataset.phase===phase,fails?'load-error':'ready');
  const initial=await state(page);
  if(initial.editors!==1||initial.runDisabled!==fails)throw Error('initial state '+JSON.stringify({entry,scenario,initial}));
  let recovered;
  if(scenario.endsWith('-retry')){
   if(!initial.retryVisible||attempts!==1)throw Error('retry initial '+JSON.stringify({entry,scenario,initial,attempts}));
   await page.locator('#retry-load').click();
   await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
   recovered=await state(page);
   if(recovered.runDisabled||attempts!==2||!recovered.code.includes('print(6 * 7)'))throw Error('retry failed');
  }
  if(!fails){
   if(requests.length!==1||(scenario!=='empty-file'&&!initial.code.includes('print(6 * 7)')))throw Error('source/GET mismatch');
   if(scenario==='empty-file'&&entry==='index'){
    await page.locator('.ace_content').click();await page.keyboard.insertText('print 6 * 7');
    await page.waitForTimeout(550);
    const afterEdit=await state(page);if(afterEdit.code!=='print 6 * 7')throw Error('empty-file delayed overwrite '+JSON.stringify(afterEdit));
   }
   await page.getByRole('button',{name:/运\s*行$/}).click();
   if(scenario==='empty-file'&&entry==='player')await page.waitForFunction(()=>TeachingPythonExecution.getState().state==='completed');
   else await page.waitForFunction(()=>document.querySelector('#output')?.textContent.includes('42'));
  }
  if(requests.some(r=>r.hasAccessToken)||errors.length)throw Error(JSON.stringify({requests,errors}));
  results.push({entry,scenario,pass:true,requests,attempts,during,initial,recovered,pageErrors:errors});
  await page.close();
 }
 for(const entry of ['player','index'])for(const width of [390,768,1440]){
  const page=await rootPage.context().newPage();await page.setViewportSize({width,height:900});
  await page.goto(BASE+'/python/'+entry+'.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fmissing.py');
  await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='load-error');
  const ui=await state(page);if(ui.overflow||!ui.retryVisible||!ui.runDisabled)throw Error('layout '+JSON.stringify({entry,width,ui}));
  await page.screenshot({path:'output/playwright/source-final-'+entry+'-error-'+width+'.png',fullPage:true,scale:'css'});
  results.push({entry,width,pass:true,ui});await page.close();
 }
 return results;
}
