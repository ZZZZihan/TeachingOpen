async (page) => {
 const cases=[],shots=[]; const check=(name,ok)=>{cases.push({case:name,passed:!!ok});if(!ok)throw new Error(name)}
 const out='output/playwright', after='http://127.0.0.1:18136',before='http://127.0.0.1:18135'
 const stable=async()=>{await page.waitForTimeout(400);await page.waitForFunction(()=>!document.querySelector('.ant-zoom-enter-active,.ant-zoom-leave-active'))}
 const mode=async(value)=>{await Promise.all([page.waitForResponse(r=>r.url().endsWith('/__mode')),page.getByLabel('场景').selectOption(value)])}
 const open=async(kind)=>{await page.getByRole('button',{name:'编辑'+kind,exact:true}).click();await stable()}
 const dialog=()=>page.locator('.ant-modal:visible').first()
 const save=()=>dialog().locator('.ant-modal-footer .ant-btn-primary')
 const close=()=>dialog().locator('.ant-modal-footer button').first()
 try {
  for(const [variant,url] of [['before',before],['after',after]]){
   for(const kind of ['课程','单元']){
    for(const width of [1440,768,390]){
     await page.setViewportSize({width,height:900});await page.goto(url);await open(kind)
     const box=await dialog().boundingBox(),footer=await save().boundingBox()
     const filename=`${out}/course-form-${variant}-${kind==='课程'?'course':'unit'}-${width}.png`;await page.screenshot({path:filename});shots.push(filename)
     if(variant==='after'){
      check(kind+' viewport and reachable save '+width,box.x>=0&&box.x+box.width<=width+1&&footer.y>=0&&footer.y+footer.height<=900)
      check(kind+' no internal horizontal overflow '+width,await dialog().evaluate(e=>e.scrollWidth<=e.clientWidth+1))
     }
    }
   }
  }
  await page.setViewportSize({width:1440,height:900})
  for(const kind of ['课程','单元']){
   const field=kind==='课程'?'请输入课程名':'请输入单元名称'
   await page.goto(before);await mode('business-error');await open(kind);await page.getByPlaceholder(field).fill('失败后要保留的内容');await save().click();await page.getByRole('dialog',{name:'编辑'+kind,exact:true}).waitFor({state:'hidden'});check(kind+' old business failure closes actual form',true)
   await page.goto(after);await mode('business-error');await open(kind);await page.getByPlaceholder(field).fill('失败后要保留的内容');await save().click();await page.getByRole('alert').waitFor()
   check(kind+' business failure retains input and focuses recoverable error',await page.getByPlaceholder(field).inputValue()==='失败后要保留的内容'&&await page.getByRole('alert').evaluate(e=>document.activeElement===e))
   const filename=`${out}/course-form-after-${kind==='课程'?'course':'unit'}-error.png`;await page.screenshot({path:filename});shots.push(filename)
   // Change only the isolated fixture mode while the modal prevents access to its background.
   await page.request.post(after+'/__mode',{data:{mode:'network-error'}});await save().click();await page.getByRole('alert').filter({hasText:'未能确认保存结果'}).waitFor()
   check(kind+' transport failure retains input and uncertain-outcome warning',await page.getByPlaceholder(field).inputValue()==='失败后要保留的内容')
   await page.request.post(after+'/__reset');await page.request.post(after+'/__mode',{data:{mode:'slow'}})
   await save().click();await page.keyboard.press('Escape');await page.keyboard.press('Enter');
   check(kind+' busy dialog cannot close and form is inert',await dialog().isVisible()&&await close().isDisabled()&&await dialog().locator('[inert]').count()===1)
   await page.getByRole('dialog',{name:'编辑'+kind,exact:true}).waitFor({state:'hidden'})
   await page.getByText('成功回调 1',{exact:true}).waitFor();const state=await (await page.request.get(after+'/__state')).json();check(kind+' exactly one write and one success callback',state.writes.length===1&&await page.getByText('成功回调 1',{exact:true}).count()===1)
   check(kind+' preserved text reaches save payload',state.writes[0].body[kind==='课程'?'courseName':'unitName']==='失败后要保留的内容')
   await open(kind);await page.getByPlaceholder(field).fill('尚未保存');await close().click();await page.getByText('放弃未保存的修改？',{exact:true}).waitFor();await page.getByRole('button',{name:'继续编辑',exact:true}).click();check(kind+' continue editing retains dirty input',await page.getByPlaceholder(field).inputValue()==='尚未保存')
   await close().click();await page.getByRole('button',{name:'放弃修改',exact:true}).click();await page.getByRole('dialog',{name:'编辑'+kind,exact:true}).waitFor({state:'hidden'});check(kind+' explicit discard closes form',true)
   await page.request.post(after+'/__mode',{data:{mode:'normal'}});await open(kind);await close().click();await page.getByRole('dialog',{name:'编辑'+kind,exact:true}).waitFor({state:'hidden'});check(kind+' clean close requires no discard prompt',true)
  }
  return {cases,shots,passed:cases.filter(c=>c.passed).length,total:cases.length}
 }catch(error){return {cases,shots,error:String(error)}}
}
