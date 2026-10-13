async page => {
  const checks=[],screenshots=[],submissions=[],consoleErrors=[],pageErrors=[],blocked=[]
  const out='.'
  const origins={before:'http://127.0.0.1:18491',after:'http://127.0.0.1:18492'}
  const check=(name,pass)=>{checks.push({case:name,passed:!!pass});if(!pass)throw Error(name)}
  page.setDefaultTimeout(6000)
  page.on('pageerror',error=>pageErrors.push(String(error)))
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text())})
  await page.context().route('**/*',route=>{
    const url=new URL(route.request().url())
    if(url.protocol==='data:'||Object.values(origins).includes(url.origin))return route.continue()
    blocked.push(route.request().url());return route.abort()
  })
  const state=async()=>await (await page.request.get(new URL('/__state',page.url()).href)).json()
  const close=async dialog=>{await dialog.getByRole('button',{name:/关\s*闭/}).click();await dialog.waitFor({state:'hidden'})}
  const shot=async(name,viewport)=>{
    // Ant's modal entry animation lasts 300 ms; capture after it has settled.
    await page.waitForTimeout(350)
    await page.screenshot({path:out+'/'+name+'.png',fullPage:true,animations:'disabled'})
    screenshots.push({file:name+'.png',viewport,width:viewport.width,height:viewport.height,fullPage:true})
  }
  try {
    for(const viewport of [{width:1440,height:1000},{width:390,height:1200}]) {
      await page.setViewportSize(viewport)
      const desktop=viewport.width===1440
      for(const variant of ['before','after']) {
        const fixed=variant==='after',name=variant+'-'+viewport.width+'x'+viewport.height
        await page.goto(origins[variant])
        await page.request.post(origins[variant]+'/__reset')
        await page.getByRole('button',{name:'编辑数据源',exact:true}).click()
        let dialog=page.getByRole('dialog',{name:'编辑数据源',exact:true})
        const password=dialog.locator('input[type=password]')
        await password.waitFor()
        check(name+' edit has a genuinely empty password field',await password.inputValue()==='')
        check(name+' edit password prompt',await password.getAttribute('placeholder')===(fixed?'留空保留现有密码':'请输入密码'))
        check(name+' source identity remains disabled',await dialog.getByPlaceholder('请输入数据源编码').isDisabled())
        if(!fixed) {
          await dialog.getByRole('button',{name:'OK',exact:true}).click()
          await dialog.getByText('请输入密码!',{exact:true}).waitFor()
          check(name+' baseline rejects blank edit password', (await state()).length===0)
        }
        await shot(name+'-source-edit',viewport)
        if(fixed&&desktop) {
          const beforeTest=await state()
          await dialog.getByRole('button',{name:/测\s*试/}).click()
          await page.getByText('测试连接时请填写密码；编辑保存时留空可保留现有密码',{exact:true}).waitFor()
          check('fixed blank password connection test explains the required credential without making a request',(await state()).length===beforeTest.length)
          await shot(name+'-source-test-password-hint',viewport)
          await password.fill('synthetic-connection-test-password')
          await dialog.getByRole('button',{name:/测\s*试/}).click()
          await page.getByText('连接成功',{exact:true}).waitFor()
          const afterTest=await state(),testRequest=afterTest[afterTest.length-1]
          submissions.push(testRequest)
          check('explicit password connection test retains the real request binding',testRequest.path==='/online/cgreport/api/testConnection'&&testRequest.method==='POST'&&testRequest.body.dbPassword==='synthetic-connection-test-password'&&testRequest.body.dbUrl==='jdbc:synthetic-no-driver')
          await password.fill('')
          await dialog.getByPlaceholder('请输入数据源名称').fill('合成数据源：修改名称')
          await dialog.getByRole('button',{name:'OK',exact:true}).click()
          await dialog.waitFor({state:'hidden'})
          let rows=await state(),record=rows[rows.length-1]
          submissions.push(record)
          check('fixed source edit submits PUT with unchanged identity',record.path==='/sys/dataSource/edit'&&record.method==='PUT'&&record.body.id==='synthetic-source-id'&&record.body.name==='合成数据源：修改名称')
          check('fixed blank password edit sends no stored password or code overwrite',!record.body.dbPassword&&!('code'in record.body))
          await page.getByRole('button',{name:'新增数据源',exact:true}).click()
          dialog=page.getByRole('dialog',{name:'新增数据源',exact:true})
          await dialog.getByRole('button',{name:'OK',exact:true}).click()
          await dialog.getByText('请输入密码!',{exact:true}).waitFor()
          check('fixed source create still requires a password',(await state()).length===rows.length)
          await shot(name+'-source-add-password-required',viewport)
          await close(dialog)
        } else await close(dialog)

        await page.getByRole('button',{name:'编辑既有任务',exact:true}).click()
        dialog=page.getByRole('dialog',{name:'编辑既有任务',exact:true})
        await dialog.getByPlaceholder('请输入描述').waitFor()
        check(name+' existing Cron string binds unchanged',await dialog.getByPlaceholder('corn表达式').inputValue()==='0 0 0 1 1 ? 2099')
        if(fixed) {
          check(name+' existing job type is selected and immutable',await dialog.locator('.ant-select-disabled').count()===1&&(await dialog.getByRole('combobox').textContent()).includes('示例任务'))
          check(name+' no arbitrary class input is rendered',await dialog.getByPlaceholder('请输入任务类名').count()===0)
        } else check(name+' baseline exposes free class input',await dialog.getByPlaceholder('请输入任务类名').inputValue()==='org.jeecg.modules.quartz.job.SampleJob')
        await shot(name+'-quartz-existing',viewport)
        if(fixed&&desktop) {
          await dialog.getByPlaceholder('请输入描述').fill('既有任务已编辑：合成记录')
          await dialog.getByText('停止',{exact:true}).click()
          await dialog.getByRole('button',{name:'保存并安排任务',exact:true}).click()
          await dialog.waitFor({state:'hidden'})
          const rows=await state(),record=rows[rows.length-1]
          submissions.push(record)
          check('existing Quartz edit sends stable type, identity and Cron via PUT',record.path==='/sys/quartzJob/edit'&&record.method==='PUT'&&record.body.id==='synthetic-job-id'&&record.body.jobType==='sample'&&record.body.jobClassName==='org.jeecg.modules.quartz.job.SampleJob'&&record.body.cronExpression==='0 0 0 1 1 ? 2099')
          check('real dictionary radioButton binds scalar stopped status',String(record.body.status)==='-1'&&record.body.description==='既有任务已编辑：合成记录')
        } else await close(dialog)

        await page.getByRole('button',{name:'新增任务',exact:true}).click()
        dialog=page.getByRole('dialog',{name:'新增任务',exact:true})
        await dialog.getByPlaceholder('请输入描述').waitFor()
        if(fixed) {
          await dialog.getByRole('combobox').click()
          await page.getByRole('option',{name:'示例任务',exact:true}).waitFor()
          const options=await page.getByRole('option').allTextContents()
          check(name+' offers exactly the three reviewed job types',JSON.stringify(options.map(v=>v.trim()))===JSON.stringify(['示例任务','带参数示例任务','发送待处理消息']))
          await shot(name+'-quartz-type-options',viewport)
          await page.getByRole('option',{name:'带参数示例任务',exact:true}).click()
          if(desktop) {
            await dialog.getByPlaceholder('请输入参数').fill('synthetic new job parameter')
            await dialog.getByPlaceholder('请输入描述').fill('新增类型化任务：合成记录')
            await dialog.getByText('停止',{exact:true}).click()
            await dialog.getByRole('button',{name:'保存并安排任务',exact:true}).click()
            await dialog.waitFor({state:'hidden'})
            const rows=await state(),record=rows[rows.length-1]
            submissions.push(record)
            check('new Quartz job submits typed command with scalar status and Cron',record.path==='/sys/quartzJob/add'&&record.method==='POST'&&record.body.jobType==='sample-parameter'&&!('jobClassName'in record.body)&&String(record.body.status)==='-1'&&typeof record.body.cronExpression==='string'&&record.body.parameter==='synthetic new job parameter')
          } else await close(dialog)
        } else {await shot(name+'-quartz-free-class',viewport);await close(dialog)}
      }
    }
    check('browser has no uncaught JavaScript errors',pageErrors.length===0)
    check('browser has no console errors',consoleErrors.length===0)
    check('no external service request was attempted',blocked.length===0)
  } catch(error) {
    checks.push({case:'browser scenario completed',passed:false})
    return {status:'failed',error:String(error),checks,screenshots,submissions,consoleErrors,pageErrors,blocked,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed).length,total:checks.length}
  }
  return {status:'passed',checks,screenshots,submissions,consoleErrors,pageErrors,blocked,passed:checks.length,failed:0,total:checks.length,
    scope:'Real compiled before/after Vue SFCs and Ant Design, real JCron and JDictSelectTag; API requests and dictionaries are synthetic; browser form verification, not backend persistence or independent Pro acceptance.'}
}
