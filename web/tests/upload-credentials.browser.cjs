// Read-only review of another checkout's SFC. Real Vue + Ant Upload + browser XHR.
// Every destination is a synthetic loopback server; no real storage host is used.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const http = require('node:http')
const { spawn } = require('node:child_process')
const crypto = require('node:crypto')
const target = path.resolve(process.argv[2] || path.join(__dirname, '../src/components/jeecg/JUpload.vue'))
const modules = path.resolve(process.env.TEACHING_NODE_MODULES || path.join(__dirname, '../node_modules'))
const browser = process.env.CHROME_BIN || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(fs.existsSync)
assert.ok(fs.existsSync(target) && browser && fs.existsSync(browser), 'Set CHROME_BIN to an installed Chromium browser')
const source = fs.readFileSync(target, 'utf8')
const compiler = require(path.join(modules, 'vue-template-compiler'))
const sfc = compiler.parseComponent(source)
const render = compiler.compile(sfc.template.content)
assert.deepEqual(render.errors, [])
const component = sfc.script.content.replace(/^\s*import .*$/gm, '').replace('export default', 'const component =')
const transport = fs.readFileSync(path.join(modules, 'ant-design-vue/lib/vc-upload/src/request.js'), 'utf8')
  .replace(/Object\.defineProperty\(exports,[\s\S]*?\}\);/, '').replace("exports['default'] = upload;", '')
const requests = []
let fixtureHtml, failNext = false

function server (external) {
  return http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'X-Requested-With, X-Access-Token, Content-Type')
    res.setHeader('Cache-Control', 'no-store')
    if (!external && req.url === '/') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); return res.end(fixtureHtml) }
    if (!external && req.url === '/requests') { res.setHeader('Content-Type', 'application/json'); return res.end(JSON.stringify(requests)) }
    if (!external && req.url === '/fail-next') { failNext = true; return res.end('ok') }
    if (req.method === 'OPTIONS') {
      requests.push({ origin: external ? 'third-party-loopback' : 'platform-loopback', method: 'OPTIONS', headers: req.headers })
      res.statusCode = 204; return res.end()
    }
    if (req.method !== 'POST') { res.statusCode = 404; return res.end() }
    const chunks = []
    req.on('data', b => chunks.push(b))
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString()
      requests.push({ origin: external ? 'third-party-loopback' : 'platform-loopback', method: 'POST', headers: req.headers, body })
      res.setHeader('Content-Type', 'application/json')
      if (!external && failNext) { failNext = false; res.statusCode = 500; return res.end(JSON.stringify({ success: false })) }
      if (!external && !req.headers['x-access-token']) { res.statusCode = 401; return res.end(JSON.stringify({ success: false })) }
      res.end(JSON.stringify(external ? { key: 'fixture-qiniu/file.txt' } : { success: true, message: 'fixture-local/file.txt' }))
    })
  })
}
const platform = server(false), storage = server(true)
const listen = s => new Promise(resolve => s.listen(0, '127.0.0.1', resolve))
const escapeScript = s => s.replace(/<\/script/gi, '<\\/script')

;(async () => {
  await listen(platform); await listen(storage)
  const platformOrigin = 'http://127.0.0.1:' + platform.address().port
  const storageOrigin = 'http://127.0.0.1:' + storage.address().port
  const scripts = [
    fs.readFileSync(path.join(modules, 'vue/dist/vue.js'), 'utf8'),
    fs.readFileSync(path.join(modules, 'moment/min/moment.min.js'), 'utf8'),
    fs.readFileSync(path.join(modules, 'ant-design-vue/dist/antd.js'), 'utf8'),
    transport + '\nconst uploadTransport = upload;',
    `const ACCESS_TOKEN='fixture-session'; const SYS_CONFIG='fixture-config';
     let sessionToken = 'synthetic-stale-initial'; let registerCount = 0;
     Vue.ls = {get: key => key === ACCESS_TOKEN ? sessionToken : {uploadType:'local'}};
     Vue.config.silent=true;
     Vue.prototype.$store={getters:{sysConfig:{staticDomain:'',qiniuDomain:'',qiniuArea:'z0'}}};
     Vue.prototype.$message={success(){},warning(){},error(){},warn(){}};
     window._CONFIG={domianURL:${JSON.stringify(platformOrigin + '/api')}};
     const getAction=()=>Promise.resolve({success:true,result:'synthetic-qiniu-only',keyPrefix:'fixture-qiniu/'});
     const postAction=(url,value)=>Promise.resolve({success:true,result:{id:'registered-'+(++registerCount),filePath:value.filePath}});
     const deleteAction=()=>Promise.resolve({success:true});`,
    component + `\ncomponent.render=new Function(${JSON.stringify(render.render)}); component.staticRenderFns=${JSON.stringify(render.staticRenderFns)}.map(body=>new Function(body));`,
    `Vue.use(antd);
     const checks=[];
     const check=(name,ok)=>{checks.push({case:name,passed:!!ok});if(!ok)throw Error(name)};
     const next=()=>new Promise(resolve=>Vue.nextTick(resolve));
     const sleep=()=>new Promise(resolve=>setTimeout(resolve,20));
     async function until(predicate){for(let i=0;i<200;i++){if(predicate())return;await sleep()}throw Error('Timed out waiting for actual upload state')}
     const app=new Vue({data:{target:'local'},render(h){return h(component,{ref:'uploader',props:{uploadTarget:this.target,autoDelete:false}})}}).$mount('#app');
     const uploader=app.$refs.uploader;
     uploader.uploadAction.qiniu=${JSON.stringify(storageOrigin + '/qiniu')};
     const ajax=()=>{function find(vm){if(vm.$options.name==='ajaxUploader')return vm;for(const c of vm.$children){const found=find(c);if(found)return found}}return find(uploader)};
     function select(name){const file=new File(['synthetic-body-'+name],name,{type:'text/plain'});const transfer=new DataTransfer();transfer.items.add(file);const input=uploader.$el.querySelector('input[type=file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));return file}
     async function captured(){return (await (await fetch('/requests')).json()).filter(r=>r.method==='POST')}
     async function run(){
       await next(); check('real Ant Upload file input mounted',!!uploader.$el.querySelector('input[type=file]')&&!!ajax());
       sessionToken='synthetic-current-local';select('local.txt');await until(()=>registerCount===1&&uploader.uploadState==='ready');
       let all=await captured();check('actual local XHR carries current token',all[0].headers['x-access-token']===sessionToken);check('local upload completed registration',uploader.confirmedFiles.length===1);
       app.target='qiniu';await next();sessionToken='synthetic-platform-never-third-party';select('qiniu.txt');await until(()=>registerCount===2&&uploader.uploadState==='ready');
       all=await captured();check('Qiniu actual XHR is cross-origin loopback',all[1].origin==='third-party-loopback');check('Qiniu actual XHR has no platform token',!('x-access-token'in all[1].headers)&&!all[1].body.includes(sessionToken));check('Qiniu form keeps its distinct upload credential',all[1].body.includes('synthetic-qiniu-only'));check('Qiniu upload still completes registration',registerCount===2);
       let release;
       ajax().transformFile=file=>new Promise(resolve=>{release=()=>resolve(file)});
       select('delayed-qiniu.txt');await until(()=>!!release);app.target='local';await next();release();await until(()=>uploader.uploadState==='error');
       all=await captured();check('delayed captured Qiniu action cannot inherit local credentials',all[2].origin==='third-party-loopback'&&!('x-access-token'in all[2].headers));
       ajax().transformFile=undefined;
       await fetch('/fail-next');sessionToken='synthetic-failure-token';select('failure.txt');await until(()=>uploader.uploadState==='error');
       all=await captured();check('HTTP failure reaches upload error state with existing files retained',all[3].headers['x-access-token']===sessionToken&&uploader.confirmedFiles.length===2);
       sessionToken='synthetic-retry-token';select('retry.txt');await until(()=>registerCount===3&&uploader.uploadState==='ready');
       all=await captured();check('retry uses newly rotated token',all[4].headers['x-access-token']===sessionToken);check('retry restores ready state and preserves successful attachments',uploader.confirmedFiles.length===3);
       sessionToken=null;select('logged-out.txt');await until(()=>uploader.uploadState==='error');all=await captured();check('logged-out actual local XHR has no stale header',!('x-access-token'in all[5].headers));
       const every=await (await fetch('/requests')).json();check('third-party preflight never requests platform auth header',every.filter(r=>r.origin==='third-party-loopback'&&r.method==='OPTIONS').every(r=>!(r.headers['access-control-request-headers']||'').includes('x-access-token')));
       return {checks,requests:all.map(r=>({origin:r.origin,method:r.method,hasPlatformToken:'x-access-token'in r.headers,hasStorageToken:r.body.includes('synthetic-qiniu-only')}))};
     }
     run().then(result=>{document.querySelector('#result').textContent=JSON.stringify({status:'passed',...result})}).catch(error=>{document.querySelector('#result').textContent=JSON.stringify({status:'failed',error:String(error),checks,html:uploader.$el.outerHTML,names:uploader.$children.map(c=>({name:c.$options.name,children:c.$children.map(x=>({name:x.$options.name,children:x.$children.map(z=>z.$options.name)}))}))})});`
  ]
  fixtureHtml = '<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="app"></div><pre id="result"></pre>'
    + scripts.map(s => '<script>' + escapeScript(s) + '</script>').join('') + '</body></html>'
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'teaching-upload-browser-'))
  try {
    const result = await new Promise((resolve, reject) => {
      const child = spawn(browser, ['--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--no-first-run',
        '--no-default-browser-check','--disable-extensions','--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
        '--user-data-dir='+path.join(directory,'profile'),'--virtual-time-budget=20000','--dump-dom',platformOrigin], {stdio:['ignore','pipe','pipe']})
      let stdout='',stderr='';child.stdout.on('data',b=>{stdout+=b});child.stderr.on('data',b=>{stderr+=b});
      const timer=setTimeout(()=>{child.kill('SIGKILL');reject(Error('Headless browser timed out: '+stderr.slice(-1000)))},30000)
      child.on('error',reject);child.on('close',code=>{clearTimeout(timer);resolve({code,stdout,stderr})})
    })
    assert.equal(result.code,0,result.stderr.slice(-1500))
    const match=result.stdout.match(/<pre id="result">([^<]+)<\/pre>/)
    if(!match)console.error('Incomplete browser DOM: '+result.stdout.slice(-2000))
    assert.ok(match,'Browser did not finish upload scenarios: '+result.stderr.slice(-1500))
    const observed=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&'))
    observed.source_sha256=crypto.createHash('sha256').update(source).digest('hex')
    observed.scope='Real Chromium, Vue SFC, Ant Upload and XHR; two synthetic loopback origins; no production or external storage traffic; not Pro acceptance.'
    console.log(JSON.stringify(observed,null,2))
    assert.equal(observed.status,'passed')
  } finally {fs.rmSync(directory,{recursive:true,force:true})}
})().catch(error=>{console.error(error);process.exitCode=1}).finally(()=>{platform.close();storage.close()})
