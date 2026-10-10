async (page) => {
  const cases = [], check = (name, passed) => { cases.push({ case: name, passed: Boolean(passed) }); if (!passed) throw Error(name) }
  const stable = async () => { await page.waitForTimeout(150); await page.waitForFunction(() => !document.querySelector('.ant-zoom-enter-active,.ant-zoom-leave-active')) }
  const main = () => page.locator('.j-editor[data-probe=main]'), editor = () => main().getByRole('textbox', { name: '正文编辑区' })
  const dialog = () => page.locator('.ant-modal:visible').last(), confirm = () => dialog().locator('.ant-modal-footer .ant-btn-primary')
  const click = async label => { await main().getByRole('button', { name: label, exact: true }).click(); await stable() }
  const html = () => page.evaluate(() => window.newsProbe.value)
  const reset = async value => { await page.evaluate(value => { window.newsProbe.value = value }, value); await stable() }
  const errors = []; page.on('pageerror', error => errors.push(String(error)))
  try {
    await page.setViewportSize({ width: 1440, height: 1000 }); await page.goto('http://127.0.0.1:18347'); await stable()
    check('actual maintained Axios browser transport loaded', await page.evaluate(() => window.newsAxiosVersion === '0.34.0'))
    check('initial existing HTML and height', await editor().innerText() === '原有正文' && (await main().locator('.j-editor-surface').boundingBox()).height >= 320)
    await editor().fill('编辑后的中文正文'); await stable()
    check('v-model input reaches parent', (await html()).includes('编辑后的中文正文') && await page.evaluate(() => window.newsProbe.inputs > 0))
    await editor().press('ControlOrMeta+A'); await click('粗体'); check('bold formatting', (await html()).includes('<strong>'))
    await click('斜体'); check('italic formatting', (await html()).includes('<em>'))
    await click('居中'); check('alignment formatting', (await html()).includes('text-align:center'))
    await main().getByLabel('文字颜色').fill('#123abc'); await stable(); check('text color formatting', (await html()).includes('rgb(18, 58, 188)'))
    await main().getByLabel('背景颜色').fill('#ffeeaa'); await stable(); check('background color formatting', (await html()).includes('rgb(255, 238, 170)'))
    await click('无序列表'); check('list formatting', (await html()).includes('<ul>'))
    await click('撤销'); await click('重做'); check('undo redo restore list', (await html()).includes('<ul>'))
    await reset('<p>表格前</p>'); await editor().click(); await main().getByLabel('表格操作').selectOption('insertTable'); await stable()
    check('insert table', await main().locator('table').count() === 1 && await main().locator('tr').count() === 3)
    await main().locator('td').first().click(); await main().getByLabel('表格操作').selectOption('addRowAfter'); await stable(); check('add table row', await main().locator('tr').count() === 4)
    await main().getByLabel('表格操作').selectOption('addColumnAfter'); await stable(); check('add table column', await main().locator('tr').first().locator('th,td').count() === 4)
    await reset('<p>链接文字</p>'); await editor().click(); await editor().press('ControlOrMeta+A'); await click('链接'); await dialog().getByLabel('链接地址').fill('https://example.test/page'); await confirm().click(); await stable()
    check('safe link inserted', (await html()).includes('https://example.test/page') && (await html()).includes('noopener noreferrer'))
    await click('取消链接'); check('unlink works', !(await html()).includes('<a '))
    await click('代码示例'); await dialog().getByLabel('代码语言').selectOption('java'); await dialog().getByLabel('代码示例').fill('System.out.println("你好");'); await confirm().click(); await stable()
    check('code sample language and text retained', (await html()).includes('language-java') && (await html()).includes('System.out.println'))
    await click('HTML 源码'); await dialog().getByLabel('HTML 源码').fill('<p style="color:#112233;text-align:right">安全正文</p><img src="/bad.png" onerror="window.newsXss=1"><script>window.newsXss=2</script><svg onload="window.newsXss=3"></svg><a href="javascript:alert(1)" data-mce-href="javascript:alert(2)">无执行</a>'); await confirm().click(); await stable()
    check('source edits remove executable HTML', !/onerror|<script|<svg|javascript:|data-mce-/.test(await html()) && !await page.evaluate(() => window.newsXss))
    check('source edit keeps allowed style', /#112233|rgb\(17, 34, 51\)/.test(await html()) && (await html()).includes('text-align:right'))
    await click('预览'); check('preview renders safe text and no script', (await main().locator('.j-editor-preview').innerText()).replace(/\s/g, '') === '安全正文无执行' && await main().locator('.j-editor-preview script,.j-editor-preview svg').count() === 0); await click('继续编辑')
    await click('全屏'); const box = await main().boundingBox(); check('fullscreen uses full viewport', box.x === 0 && box.y === 0 && box.width === 1440 && box.height === 1000); await page.keyboard.press('Escape'); await stable(); check('Escape exits fullscreen', await main().getAttribute('class') === 'j-editor')
    const preserved = await html(); await page.getByRole('button', { name: '重载编辑器', exact: true }).click(); await stable(); check('reload retains content and one editor', await html() === preserved && await main().locator('.tiptap').count() === 1)
    await page.getByRole('tab', { name: '其他', exact: true }).click(); await page.getByRole('tab', { name: '正文', exact: true }).click(); await stable(); await editor().fill('切换标签后仍可编辑'); check('tab reload remains editable', (await html()).includes('切换标签后仍可编辑'))
    await page.getByRole('button', { name: '切换只读', exact: true }).click(); check('disabled editor and toolbar', await editor().getAttribute('contenteditable') === 'false' && await main().getByRole('button', { name: '图片', exact: true }).isDisabled()); await page.getByRole('button', { name: '切换只读', exact: true }).click()
    await page.locator('.j-editor').nth(1).getByRole('textbox', { name: '正文编辑区' }).fill('系统配置输入'); await stable(); check('triggerChange decorator form receives change only', await page.evaluate(() => window.newsProbe.form.getFieldValue('body').includes('系统配置输入') && window.newsProbe.changes > 0))
    await reset('<p>上传前正文</p>'); await click('图片'); await dialog().locator('input[type=file]').setInputFiles({ name: 'probe.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGv8AAAAASUVORK5CYII=', 'base64') }); await page.waitForFunction(() => !window.newsProbe.$refs.main.uploading)
    check('real local image upload returns media path', (await dialog().getByLabel('媒体地址').inputValue()).includes('/api/sys/common/static/'))
    await confirm().click(); await stable(); check('uploaded image inserted', (await html()).includes('<img'))
    await page.evaluate(() => { window.newsUploadFailure = true }); await click('图片'); await dialog().locator('input[type=file]').setInputFiles({ name: 'probe.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgo=', 'base64') }); await dialog().getByRole('alert').waitFor()
    check('upload failure releases controls and preserves text', await dialog().getByRole('alert').innerText() === '合成网络故障' && !await dialog().locator('input[type=file]').isDisabled() && (await html()).includes('上传前正文'))
    await page.evaluate(() => { window.newsUploadFailure = false }); await dialog().locator('input[type=file]').setInputFiles({ name: 'probe-retry.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGv8AAAAASUVORK5CYII=', 'base64') }); await page.waitForFunction(() => !window.newsProbe.$refs.main.uploading); check('same upload can retry successfully', Boolean(await dialog().getByLabel('媒体地址').inputValue())); await confirm().click(); await stable()
    await page.getByLabel('存储方式').selectOption('database'); await click('图片'); await dialog().locator('input[type=file]').setInputFiles({ name: 'inline.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgo=', 'base64') }); await page.waitForFunction(() => !window.newsProbe.$refs.main.uploading); await confirm().click(); await stable(); check('database raster image mode retained', (await html()).includes('data:image/png;base64,'))
    await click('视频'); await dialog().locator('input[type=file]').setInputFiles({ name: 'probe.mp4', mimeType: 'video/mp4', buffer: Buffer.from('0000') }); await dialog().getByRole('alert').waitFor(); check('database video limitation gives recoverable error', (await dialog().getByRole('alert').innerText()).includes('不支持上传至数据库')); await dialog().locator('.ant-modal-close').click(); await stable()
    await page.getByLabel('存储方式').selectOption('local'); await click('视频'); await dialog().locator('input[type=file]').setInputFiles({ name: 'probe.mp4', mimeType: 'video/mp4', buffer: Buffer.from('0000') }); await page.waitForFunction(() => !window.newsProbe.$refs.main.uploading); await confirm().click(); await stable(); check('real local video upload inserted with controls', (await html()).includes('<video') && (await html()).includes('controls=""'))
    let delayedUpload; await page.route('**/api/sys/common/upload', route => { delayedUpload = route })
    await click('图片'); await dialog().locator('input[type=file]').setInputFiles({ name: 'late.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgo=', 'base64') }); await page.waitForFunction(() => window.newsProbe.$refs.main.uploading); await dialog().locator('.ant-modal-close').click(); await stable(); await page.getByRole('button', { name: '重载编辑器', exact: true }).click(); await stable(); await click('图片'); await delayedUpload.fulfill({ json: { success: true, message: 'jeditor/late.png' } }); await stable(); check('late upload after close and reload cannot alter a new dialog', await dialog().getByLabel('媒体地址').inputValue() === '' && !await page.evaluate(() => window.newsProbe.$refs.main.uploading) && await main().locator('.tiptap').count() === 1); await dialog().locator('.ant-modal-close').click(); await page.unroute('**/api/sys/common/upload'); await stable()
    const valueBoundary = await page.evaluate(async () => {
      const component = window.newsProbe.$refs.main, original = component.uploadMedia
      let finish; component.uploadMedia = () => new Promise(resolve => { finish = resolve })
      component.openDialog('image'); const pending = component.uploadFile({ target: { files: [new File(['x'], 'A.png', { type: 'image/png' })] } })
      window.newsProbe.value = '<p>B 新正文</p>'; await component.$nextTick()
      finish('https://example.test/A.png'); await pending; component.uploadMedia = original
      return component.myValue === '<p>B 新正文</p>' && component.dialog === '' && component.draft === '' && !component.uploading
    }); check('external value change invalidates prior upload and dialog', valueBoundary)
    await editor().fill('B record edited'); await reset('<p>C 原稿</p>'); await click('撤销')
    check('external record value resets undo history', (await html()) === '<p>C 原稿</p>')
    await page.evaluate(() => window.newsProbe.$refs.news.edit({ id: 'session-A', newsContent: '<p>相同正文</p>' })); await stable()
    const sessionBoundary = await page.evaluate(async () => {
      const modal = window.newsProbe.$refs.news
      const find = node => node.$options.name === 'JEditor' ? node : node.$children.map(find).find(Boolean)
      const component = find(modal), original = component.uploadMedia
      let finish; component.uploadMedia = () => new Promise(resolve => { finish = resolve })
      component.openDialog('image'); const pending = component.uploadFile({ target: { files: [new File(['x'], 'A.png', { type: 'image/png' })] } })
      modal.edit({ id: 'session-B', newsContent: '<p>相同正文</p>' }); await modal.$nextTick(); await component.$nextTick()
      finish('https://example.test/A.png'); await pending; component.uploadMedia = original
      return component.dialog === '' && component.draft === '' && !component.uploading
    }); check('switching records with identical HTML invalidates media session', sessionBoundary)
    await page.locator('.ant-modal:visible').first().getByRole('textbox', { name: '正文编辑区' }).fill('相同正文修改')
    await page.evaluate(async () => { const modal = window.newsProbe.$refs.news; const body = modal.form.getFieldValue('newsContent'); modal.edit({ id: 'session-C', newsContent: body }); await modal.$nextTick() }); await stable()
    await page.locator('.ant-modal:visible').first().getByRole('button', { name: '撤销', exact: true }).click(); await stable()
    check('identical-body new session cannot undo into another record', (await page.locator('.ant-modal:visible').first().getByRole('textbox', { name: '正文编辑区' }).innerText()) === '相同正文修改')
    await page.locator('.ant-modal:visible').first().getByRole('button', { name: '全屏', exact: true }).click(); await stable()
    await page.evaluate(() => window.newsProbe.$refs.news.close()); await page.waitForFunction(() => !document.querySelector('.j-editor-fullscreen') && Array.from(document.querySelectorAll('.ant-modal')).every(node => node.getBoundingClientRect().width === 0)); await stable()
    check('closing parent modal restores fullscreen editor and hides it', await page.locator('.j-editor-fullscreen').count() === 0 && await page.locator('.ant-modal:visible').count() === 0)
    await page.route('**/api/common/qiniu/getToken*', route => route.fulfill({ json: { success: true, keyPrefix: 'editor/', result: 'synthetic-only' } })); await page.evaluate(() => { window.newsQiniuResponse = { key: 'editor/qiniu.png' } }); await page.getByLabel('存储方式').selectOption('qiniu'); await click('图片'); await dialog().locator('input[type=file]').setInputFiles({ name: 'qiniu.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgo=', 'base64') }); await page.waitForFunction(() => !window.newsProbe.$refs.main.uploading); check('Qiniu token and upload result use configured domain (simulated cloud)', (await dialog().getByLabel('媒体地址').inputValue()).endsWith('/fake-qiniu/editor/qiniu.png') && await page.evaluate(() => window.newsQiniuRequest.url === 'https://upload-z0.qiniup.com' && window.newsQiniuRequest.key.startsWith('editor/') && window.newsQiniuRequest.token === 'synthetic-only')); await confirm().click(); await stable(); await page.unroute('**/api/common/qiniu/getToken*'); await page.evaluate(() => { delete window.newsQiniuResponse }); await page.getByLabel('存储方式').selectOption('local')
    await page.getByRole('button', { name: '新增新闻', exact: true }).click(); await stable(); const news = page.locator('.ant-modal:visible').first(); await news.getByPlaceholder('请输入标题').fill('news_content_browser'); await news.getByLabel('新闻状态').selectOption('1'); await news.getByRole('textbox', { name: '正文编辑区' }).fill('真实新闻编辑器内容'); await news.locator('.ant-modal-footer .ant-btn-primary').click(); await stable(); await page.waitForFunction(() => !window.newsProbe.$refs.news.visible)
    const reply = await (await page.request.get('http://127.0.0.1:18347/api/teaching/teachingNews/list?newsTitle=news_content_browser')).json(); check('actual TeachingNewsModal decorator saves to MySQL', reply.success && reply.result.records.some(row => row.newsTitle === 'news_content_browser' && row.newsContent.includes('真实新闻编辑器内容')))
    await page.getByRole('button', { name: '新增新闻', exact: true }).click(); await stable(); await page.waitForFunction(() => Array.from(document.querySelectorAll('.ant-modal .tiptap')).filter(node => node.offsetParent).every(node => !node.textContent.trim())); check('reopened modal uses empty new value', !(await page.locator('.ant-modal:visible').first().getByRole('textbox', { name: '正文编辑区' }).innerText()).trim() && !await page.evaluate(() => window.newsProbe.$refs.news.form.getFieldValue('newsContent'))); await page.locator('.ant-modal:visible').first().getByRole('button', { name: '全屏', exact: true }).click(); await stable(); const modalFull = await page.locator('.j-editor-fullscreen').boundingBox(); check('editor fullscreen inside actual news modal', modalFull.x === 0 && modalFull.y === 0 && modalFull.height === 1000); await page.keyboard.press('Escape'); await stable(); check('modal editor restored after fullscreen', await page.locator('.ant-modal:visible').first().locator('.j-editor .tiptap').count() === 1); await page.locator('.ant-modal:visible').first().getByRole('button', { name: 'Close', exact: true }).click(); await stable()
    await page.getByRole('button', { name: '新闻阅读', exact: true }).click(); await stable(); await page.evaluate(() => { window.newsProbe.$refs.reader.cmsInfo = { newsContent: '<p>历史正文</p><img src=x onerror="window.newsXss=6"><svg onload="window.newsXss=7"></svg><a href="javascript:alert(1)">历史链接</a>' } }); await stable(); check('actual NewsDetail sanitizes historical or compromised API HTML', await page.locator('.article-content').locator('[onerror],svg,a[href^="javascript"]').count() === 0 && !await page.evaluate(() => window.newsXss))
    await page.screenshot({ path: 'output/playwright/news-editor-1440.png', fullPage: true }); check('no uncaught browser errors', errors.length === 0)
    return { scope: 'Chromium real JEditor, Ant Design form/modal/tab, NewsModal and NewsDetail; dictionary stub; real MySQL API via synthetic-admin proxy. Qiniu cloud calls simulated separately.', cases, passed: cases.filter(item => item.passed).length, total: cases.length, errors }
  } catch (error) { return { cases, passed: cases.filter(item => item.passed).length, total: cases.length, error: String(error), errors } }
}
