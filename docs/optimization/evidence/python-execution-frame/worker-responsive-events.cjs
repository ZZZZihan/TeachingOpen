async (rootPage) => {
 const all=[]; const errors=[];
 for(const [entry,path] of [['player','player.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fseed.py'],['editor','index.html?workId=seed-work']]){
  for(const width of [390,768,1440]){
   const page=await rootPage.context().newPage();
   page.on('pageerror',e=>errors.push(String(e)));
   await page.setViewportSize({width,height:1000});
   await page.goto('http://127.0.0.1:18160/python/'+path);
   await page.waitForFunction(()=>document.querySelector('.ace_content')?.textContent.includes('Python persistence fixture'));
   await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
   await page.evaluate(()=>TeachingPythonFrameProbe.run(TeachingPythonFrameProbe.fixtures.turtleEvents));
   await page.waitForFunction(()=>TeachingPythonFrameProbe.output().includes('EVENTS_READY')&&TeachingPythonFrameProbe.state().state==='completed');
   const child=page.frames().find(f=>f!==page.mainFrame());
   const canvasBefore=await child.locator('canvas').count();
   const visible=await page.locator('#mycanvas iframe').isVisible();
   if(!visible)throw Error('Lazy turtle event surface hidden');
   await child.locator('#mycanvas').click({position:{x:100,y:90}});
   await page.waitForFunction(()=>TeachingPythonFrameProbe.output().includes('MOUSE_CALLBACK'));
   await page.keyboard.press('a');
   await page.waitForFunction(()=>TeachingPythonFrameProbe.output().includes('KEY_CALLBACK'));
   const geometry=await page.evaluate(()=>{const controls=document.querySelector('.python-execution-controls').getBoundingClientRect();const frame=document.querySelector('iframe').getBoundingClientRect();return {overflow:document.documentElement.scrollWidth>innerWidth,controls:{x:controls.x,width:controls.width},frame:{x:frame.x,width:frame.width,height:frame.height},state:TeachingPythonFrameProbe.state(),output:TeachingPythonFrameProbe.output()};});
   const canvases=await child.evaluate(()=>Array.from(document.querySelectorAll('canvas')).map(c=>{const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let pixels=0;for(let i=3;i<a.length;i+=4)if(a[i])pixels++;return {width:c.width,height:c.height,opaquePixels:pixels};}));
   await page.screenshot({path:'output/playwright/python-execution-frame/final-'+entry+'-events-'+width+'.png',fullPage:true,scale:'css'});
   all.push({entry,width,canvasBefore,visible,geometry,canvases});
   await page.close();
  }
 }
 if(errors.length)throw Error(JSON.stringify(errors));
 return {all,pageErrors:errors};
}
