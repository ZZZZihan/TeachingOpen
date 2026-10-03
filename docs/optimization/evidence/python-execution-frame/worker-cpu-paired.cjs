async (page) => {
 const rows=[];
 for(const mode of ['control','stop']) {
  await page.goto('http://127.0.0.1:18160/python/player.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fseed.py');
  await page.waitForFunction(()=>document.querySelector('.ace_content')?.textContent.includes('Python persistence fixture'));
  await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
  const id=mode+'-'+Date.now(),events=[],errors=[];
  const onConsole=m=>{if(m.text().startsWith('PRODUCT_CPU '+id+' '))events.push({text:m.text(),receivedEpoch:Date.now()});};
  const onError=e=>errors.push(String(e));page.on('console',onConsole);page.on('pageerror',onError);
  const js='(function(){var start=Date.now(),n=0,next=20;while(Date.now()-start<3500){n++;var elapsed=Date.now()-start;if(elapsed>=next){console.log("PRODUCT_CPU '+id+' progress "+Date.now()+" "+elapsed+" "+n);next=next===20?250:next+250}}console.log("PRODUCT_CPU '+id+' done "+Date.now());return 1})()';
  await page.evaluate(()=>{window.__cpuTicks=[];window.__cpuTimer=setInterval(()=>window.__cpuTicks.push(Date.now()),50);});
  await page.evaluate(code=>TeachingPythonFrameProbe.run(code),'jseval('+JSON.stringify(js)+')\nprint "PRODUCT_CPU_COMPLETE"\n');
  const enteredDeadline=Date.now()+10000;while(!events.some(e=>e.text.includes(' progress '))){if(Date.now()>enteredDeadline)throw Error('No actual loop entry marker');await page.waitForTimeout(20);}
  const enteredEpoch=Date.now();let stopRequestedEpoch=null;
  if(mode==='stop'){await page.waitForTimeout(100);stopRequestedEpoch=Date.now();await page.getByRole('button',{name:'停止',exact:true}).click();}
  await page.waitForTimeout(Math.max(0,4500-(Date.now()-enteredEpoch)));
  const observation=await page.evaluate(()=>{clearInterval(window.__cpuTimer);return {state:TeachingPythonFrameProbe.state(),output:TeachingPythonFrameProbe.output(),frames:document.querySelectorAll('#mycanvas iframe').length,heartbeats:window.__cpuTicks};});
  page.off('console',onConsole);page.off('pageerror',onError);
  const done=events.some(e=>e.text.includes(' done '));
  const pass=mode==='control'?done&&observation.output.includes('PRODUCT_CPU_COMPLETE'):!done&&!observation.output.includes('PRODUCT_CPU_COMPLETE')&&observation.state.state==='stopped'&&observation.frames===0;
  rows.push({id,mode,pass,enteredEpoch,stopRequestedEpoch,events,observation,pageErrors:errors,scope:'One finite 3500ms Worker per scenario; parent 50ms heartbeat; observe 4500ms after confirmed >=20ms busy-loop marker. Control required. Evidence of bounded eventual termination, not immediate CPU zero or all-resource measurement.'});
  if(!pass||errors.length)throw Error(JSON.stringify(rows));
 }
 return {rows};
}
