async (rootPage) => {
 const page=await rootPage.context().newPage(),errors=[],reads=[];
 const base='http://127.0.0.1:18160';
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(r.method()==='GET'&&(r.url().includes('/fixtures/')||r.url().includes('/studentWorkInfo')))reads.push(r.url());});
 const before=await (await page.request.get(base+'/__state')).json();
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(base+'/python/index.html?queryEncoding=uri&workId=seed-work&url=%2Ffixtures%2Fignored.py');
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
 if(reads.filter(u=>u.includes('/fixtures/')).length!==1||reads.some(u=>u.includes('ignored.py')))throw Error('workId priority/duplicate failed');
 await page.getByRole('textbox',{name:'作品名称'}).fill('源码加载保存回归');
 await page.locator('.ace_content').click();await page.keyboard.press('ControlOrMeta+A');
 const code='print "SOURCE_SAVE_OK"\nprint 6 * 7\n';await page.keyboard.insertText(code);
 await page.getByRole('button',{name:/^提\s*交$/}).click();
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='saved');
 const savedUrl=page.url();await page.reload();
 await page.waitForFunction(()=>document.querySelector('#persistence-status')?.dataset.phase==='ready');
 const reopened=await page.evaluate(()=>({code:document.querySelector('.ace_editor').env.editor.getValue(),title:document.querySelector('input[aria-label="作品名称"]').value}));
 if(reopened.code!==code||reopened.title!=='源码加载保存回归')throw Error(JSON.stringify(reopened));
 await page.getByRole('button',{name:/运\s*行$/}).click();
 await page.waitForFunction(()=>document.querySelector('#output')?.textContent.includes('42'));
 const after=await (await page.request.get(base+'/__state')).json();
 const diff={uploads:after.uploads.length-before.uploads.length,registrations:after.registrations.length-before.registrations.length,submissions:after.submissions.length-before.submissions.length};
 if(Object.values(diff).some(n=>n!==1)||Object.keys(after.works).length!==Object.keys(before.works).length||errors.length)throw Error(JSON.stringify({diff,errors}));
 await page.screenshot({path:'output/playwright/source-final-save-reopen.png',fullPage:true,scale:'css'});
 const result={pass:true,savedUrl,reopened,reads,writeCount:diff,workId:after.submissions.at(-1).id,workCountUnchanged:true,pageErrors:errors,scope:'Actual UI + isolated synthetic HTTP fixture; not real Java authentication or persistence.'};
 await page.close();return result;
}
