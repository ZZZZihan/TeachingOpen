async (rootPage) => {
 const all=[];
 for(const port of [18112,18142,18150]){
  for(const entry of ['player','index']){
   const page=await rootPage.context().newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.goto('http://127.0.0.1:'+port+'/python/'+entry+'.html?lang=turtle');
   await page.waitForSelector('.ace_content');
   await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
   await page.evaluate(()=>TeachingPythonFrameProbe.run('import turtle\nt=turtle.Turtle()\nt.speed(0)\nfor i in range(4):\n    t.forward(30)\n    t.right(90)\nprint "CANDIDATE_42", 6*7\n'));
   await page.waitForFunction(()=>TeachingPythonFrameProbe.output().includes('CANDIDATE_42 42')&&TeachingPythonFrameProbe.state().state==='completed');
   const child=page.frames().find(f=>f!==page.mainFrame());const canvasCount=await child.locator('canvas').count();
   const drawOutput=await page.evaluate(()=>TeachingPythonFrameProbe.output());
   await page.locator('#python-execution-stop').click();
   await page.waitForFunction(()=>TeachingPythonFrameProbe.state().state==='stopped'&&!document.querySelector('#mycanvas iframe'));
   await page.evaluate(()=>TeachingPythonFrameProbe.run('value=raw_input("组合输入：")\nprint "CANDIDATE_INPUT",value\n'));
   await page.locator('#python-execution-input').fill('ok');
   await page.locator('#python-execution-input-form button[type=submit]').click();
   await page.waitForFunction(()=>TeachingPythonFrameProbe.output().includes('CANDIDATE_INPUT ok')&&TeachingPythonFrameProbe.state().state==='completed');
   const inputOutput=await page.evaluate(()=>TeachingPythonFrameProbe.output());
   await page.evaluate(()=>TeachingPythonExecution.clear());
   const finalState=await page.evaluate(()=>TeachingPythonFrameProbe.state());
   const pass=canvasCount===2&&errors.length===0&&finalState.state==='idle';
   all.push({port,entry,pass,canvasCount,drawOutput,inputOutput,finalState,pageErrors:errors});await page.close();
   if(!pass)throw Error(JSON.stringify(all));
  }
 }
 return {all,scope:'Actual combined built dist with existing loopback CSP headers; self-authored code, anonymous, no save or authentication.'};
}
