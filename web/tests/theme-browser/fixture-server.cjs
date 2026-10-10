const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')

const menu = [
  { path: '/account/settings', name: 'account-settings', component: 'account/settings/Index', meta: { title: '账户设置', icon: 'setting' }, children: [
    { path: '/account/settings/base', name: 'account-settings-base', component: 'account/settings/BaseSetting', meta: { title: '基本设置' } },
    { path: '/account/settings/custom', name: 'account-settings-custom', component: 'account/settings/Custom', meta: { title: '个性化' } }
  ] },
  { path: '/account/center', name: 'account-center', component: 'account/center/Index', meta: { title: '个人中心', icon: 'user' } }
]
const syntheticUser = { id: 'synthetic-pr94-user', username: 'synthetic-pr94', realname: '合成浏览器用户', userIdentity: 0, avatar: '', birthday: '', sex: 1, email: '', phone: '' }
const syntheticConfig = base => ({ brandName: '合成校园平台', logo: 'fixture-brand.svg', loginLogo: 'fixture-brand.svg', avatar: 'fixture-avatar.svg', uploadType: 'local', staticDomain: base, customCss: '.fixture-custom-css { color: rgb(17, 34, 51); }', customJS: 'window.__fixtureBrandCustomization = "preserved";' })
const svg = label => `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50"><rect width="200" height="50" fill="#e9f1fa"/><text x="10" y="31" fill="#146fc2" font-size="18">${label}</text></svg>`

async function startFixture(dist, port = 0) {
  const requests = []
  const server = http.createServer((req, res) => {
    const base = `http://127.0.0.1:${server.address().port}`
    const url = new URL(req.url, base)
    requests.push({ method: req.method, path: url.pathname, query: Object.fromEntries(url.searchParams) })
    if (url.pathname.startsWith('/api/')) {
      let result
      if (url.pathname.endsWith('/sys/config/getCurrentConfig')) result = syntheticConfig(base)
      else if (url.pathname.endsWith('/teaching/menu/getUserMenu')) result = []
      else if (url.pathname.endsWith('/sys/permission/getUserPermissionByToken')) result = { menu, auth: [], allAuth: [] }
      else if (url.pathname.endsWith('/teaching/teachingNews/newsList')) result = { records: [{ id: 'synthetic-news', newsTitle: '合成资讯标题', description: '只读合成内容', createTime: '2026-10-10 10:00:00' }], total: 1 }
      else if (url.pathname.endsWith('/teaching/teachingWork/userInfo')) result = { ...syntheticUser, realname: '合成创作者', sign: '本机合成资料' }
      else if (url.pathname.endsWith('/teaching/teachingWork/leaderboard')) result = { records: [{ id: 'synthetic-work', workName: '合成作品标题', workType: 4, viewNum: 1, starNum: 1 }], total: 1 }
      else if (/randomImage/.test(url.pathname)) result = 'data:image/svg+xml;base64,' + Buffer.from(svg('1234')).toString('base64')
      else if (/getMyAnnouncementSend|annountCement\/listByUser/.test(url.pathname)) result = { anntMsgList: [], anntMsgTotal: 0, sysMsgList: [], sysMsgTotal: 0 }
      else if (/dict/.test(url.pathname)) result = []
      else result = { records: [], total: 0 }
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
      res.end(JSON.stringify({ success: true, code: 200, result }))
      return
    }
    if (url.pathname.endsWith('fixture-brand.svg') || url.pathname.endsWith('fixture-avatar.svg')) {
      res.writeHead(200, { 'Content-Type': 'image/svg+xml' }); res.end(svg('合成校园平台')); return
    }
    const requestedPath = url.pathname === '/' || !path.extname(url.pathname) ? '/index.html' : url.pathname
    const file = path.resolve(dist, '.' + decodeURIComponent(requestedPath))
    if (!file.startsWith(path.resolve(dist) + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); res.end('Fixture resource unavailable'); return
    }
    const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.less': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff': 'font/woff', '.woff2': 'font/woff2', '.json': 'application/json' }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' })
    fs.createReadStream(file).pipe(res)
  })
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve))
  return { server, base: `http://127.0.0.1:${server.address().port}`, requests }
}
module.exports = { startFixture, syntheticUser, syntheticConfig }
