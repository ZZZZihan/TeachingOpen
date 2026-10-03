async (rootPage) => {
 const results=[];
 for(const entry of ['player','index'])for(const missing of [false,true]){
  const page=await rootPage.context().newPage(),requests=[],responses=[],errors=[];
  page.on('request',r=>{if(r.url().includes('/fixtures/'))requests.push({url:r.url(),method:r.method()});});
  page.on('response',r=>{if(r.url().includes('/fixtures/'))responses.push({url:r.url(),status:r.status()});});
  page.on('pageerror',e=>errors.push(String(e)));
  const file=missing?'/fixtures/missing.py':'/fixtures/seed.py';
  await page.goto('http://127.0.0.1:18159/python/'+entry+'.html?queryEncoding=uri&lang=turtle&url='+encodeURIComponent(file));
  await page.waitForSelector('.ace_content');await page.waitForTimeout(1000);
  const ui=await page.evaluate(()=>({title:document.title,text:document.body.innerText,editors:document.querySelectorAll('.ace_editor').length,sourceStatus:document.querySelector('#persistence-status')?.textContent||null,phase:document.querySelector('#persistence-status')?.dataset.phase||null,retryVisible:!!document.querySelector('#retry-load:not([hidden])'),buttons:Array.from(document.querySelectorAll('button')).map(b=>({text:b.textContent,disabled:b.disabled})),code:document.querySelector('.ace_content')?.textContent||''}));
  await page.screenshot({path:'output/playwright/source-baseline-'+entry+'-'+(missing?'missing':'valid')+'.png',fullPage:true,scale:'css'});
  results.push({entry,missing,requests,responses,pageErrors:errors,ui});await page.close();
 }
 return results;
}
