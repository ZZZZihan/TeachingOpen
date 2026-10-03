async (rootPage) => {
 const page=await rootPage.context().newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const code='print "Saved Worker fixture"\nprint 6 * 7\n';const title='执行隔离保存回归';
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('http://127.0.0.1:18160/python/index.html?queryEncoding=uri&workId=seed-work');
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
 await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
 await page.getByRole('textbox',{name:'作品名称'}).fill(title);
 await page.evaluate(c=>TeachingPythonFrameProbe.component().setCode(c),code);
 await page.waitForFunction(c=>TeachingPythonFrameProbe.component().getCode()===c,code);
 const before=await (await page.request.get('http://127.0.0.1:18160/__state')).json();
 await page.getByRole('button',{name:'提 交',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='saved');
 const savedUrl=page.url();const state=await(await page.request.get('http://127.0.0.1:18160/__state')).json();
 await page.reload();
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
 await page.addScriptTag({path:'web/tests/python-execution-frame/browser-probe.js'});
 const reopened=await page.evaluate(()=>({code:TeachingPythonFrameProbe.component().getCode(),title:TeachingPythonFrameProbe.component().projectName}));
 await page.getByRole('button',{name:/运行/}).click();
 await page.waitForFunction(()=>TeachingPythonFrameProbe.state().state==='completed'&&TeachingPythonFrameProbe.output().includes('42'));
 const output=await page.evaluate(()=>TeachingPythonFrameProbe.output());
 await page.screenshot({path:'output/playwright/python-execution-frame/final-editor-save-reopen.png',fullPage:true,scale:'css'});
 const uploads=state.uploads.slice(before.uploads.length),registrations=state.registrations.slice(before.registrations.length),submissions=state.submissions.slice(before.submissions.length);
 const sameWorks=Object.keys(state.works).length===Object.keys(before.works).length;
 const pass=reopened.code===code&&reopened.title===title&&uploads.length===1&&registrations.length===1&&submissions.length===1&&submissions[0].id==='seed-work'&&sameWorks&&errors.length===0;
 const result={pass,savedUrl,reopened,output,uploads,registrations,submissions,sameWorks,pageErrors:errors,scope:'Actual editor UI and Worker against self-authored synthetic HTTP fixture; no login or real Java save.'};
 await page.close();if(!pass)throw Error(JSON.stringify(result));return result;
}
