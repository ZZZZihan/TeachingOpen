const assert = require('node:assert/strict')
const {test} = require('node:test')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), crypto = require('node:crypto')
const output = require('../public/python/output.js')
function element() {
  const node = {children: [], parentNode: null, ownerDocument: {
    createTextNode(data) {return {data, parentNode:null, get length(){return this.data.length}, get textContent(){return this.data}, appendData(v){this.data+=v}, deleteData(a,b){this.data=this.data.slice(0,a)+this.data.slice(a+b)}}},
    createElement(){return element()}
  }, appendChild(child){child.parentNode=this;this.children.push(child)}, insertBefore(child,reference){child.parentNode=this;this.children.splice(this.children.indexOf(reference),0,child)}}
  Object.defineProperties(node, {
    textContent: {get(){return this.children.map(c=>c.textContent).join('')},set(v){this.children.forEach(c=>{c.parentNode=null});this.children=[];if(v)this.appendChild(this.ownerDocument.createTextNode(String(v)))}},
    innerHTML: {get(){throw new Error('Output must not read HTML')},set(){throw new Error('Output must not parse HTML')}}
  })
  return node
}
test('HTML, entities and event attributes are literal output across chunks',()=>{
  const n=element();const chunks=['<strong>原样</strong>\n','&lt;b&gt; <img src=x onerror="alert(1)">','\n中文 😀\n',42]
  chunks.forEach(v=>output.append(n,v));assert.equal(n.textContent,chunks.join(''));assert.equal(n.children.length,1)
})
test('many print calls reuse one text node instead of reparsing or multiplying nodes',()=>{
  const n=element();output.append(n,'start\n');const first=n.children[0]
  for(let i=0;i<9000;i++)output.append(n,'x\n')
  assert.equal(n.children.length,1);assert.equal(n.children[0],first);assert.equal(n.textContent.length,18006)
})
test('exact display limit preserves all data; excess adds exactly one fixed notice',()=>{
  const n=element();output.append(n,'x'.repeat(output.maxUnits));assert.equal(n.children.length,1)
  output.append(n,'');assert.equal(n.children.length,1);output.append(n,'y'.repeat(500000));const size=n.textContent.length
  for(let i=0;i<10000;i++)output.append(n,'ignored')
  assert.equal(n.children.length,2);assert.equal(n.children[1].length,output.maxUnits);assert.equal(size,output.maxUnits+output.notice.length);assert.equal(n.textContent.length,size)
})
test('truncation preserves surrogate pairs inside a chunk and across a boundary',()=>{
  const a=element();output.append(a,'x'.repeat(output.maxUnits-1)+'😀more');assert.equal(a.children[1].length,output.maxUnits-1);assert.ok(!a.children[1].data.includes('\ud83d'))
  const b=element();output.append(b,'x'.repeat(output.maxUnits-1)+'\ud83d');output.append(b,'\ude00rest');assert.equal(b.children[1].length,output.maxUnits-1)
  const c=element();output.append(c,'x'.repeat(output.maxUnits-2)+'😀');output.append(c,'tail');assert.ok(c.children[1].data.endsWith('😀'));assert.equal(c.children[1].length,output.maxUnits)
})
test('clear removes the notice and allows full output again; nodes keep independent limits',()=>{
  const a=element(),b=element();output.append(a,'x'.repeat(output.maxUnits+1));output.append(b,'other');output.clear(a);assert.equal(a.textContent,'');output.append(a,'fresh\n');assert.equal(a.textContent,'fresh\n');assert.equal(a.children.length,1);assert.equal(b.textContent,'other')
})
test('replaced DOM content starts a fresh buffer and missing output is harmless',()=>{
  const n=element();output.append(n,'old');n.textContent='';output.append(n,'new');assert.equal(n.textContent,'new');output.clear(null);output.append(null,'ignored')
})
for(const [bundle,method] of [['app','terminalOut'],['appPlayer','outf']]){
 test(bundle+' actual component appends through the shared buffer and clears turtle canvas',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../public/python/static/js/'+bundle+'.js'),'utf8')
  const start=source.indexOf('c={name:"PythonEditor"')+2
  const body=source.slice(start,source.indexOf(',p={render:',start))
  const nodes={output:element(),mycanvas:{innerHTML:'drawing'}}
  const context={component:null,window:{TeachingPythonOutput:output},document:{getElementById:id=>nodes[id]},o:{a:{}},s:{a:{}},u:{}}
  vm.createContext(context);vm.runInContext('component='+body,context)
  context.component.methods[method]('<b>literal</b>');assert.equal(nodes.output.textContent,'<b>literal</b>');assert.equal(nodes.output.children.length,1)
  context.component.methods.clear();assert.equal(nodes.output.textContent,'');assert.equal(nodes.mycanvas.innerHTML,'')
  context.component.methods[method]('rerun');assert.equal(nodes.output.textContent,'rerun')
 })
}
test('both HTML entry points load output helper before vendor bundles and share output styles',()=>{
 for(const page of ['index','player']){
  const html=fs.readFileSync(path.join(__dirname,'../public/python/'+page+'.html'),'utf8')
  assert.ok(html.indexOf('src="./output.js"')>=0);assert.ok(html.indexOf('src="./output.js"')<html.indexOf('src=./static/js/manifest.js'));assert.match(html,/href="\.\/output.css"/)
 }
})
test('the recorded URL substitutions reverse before the six output substitutions and preserve the historical vendor base',()=>{
 const urlPatch=require('./python-preview-url/vendor-patch.json')
 const patch=require('./python-output-preview/vendor-patch.json')
 for(const file of patch.files){
  let source=fs.readFileSync(path.join(__dirname,'../..',file.path),'utf8')
  const urlFile=urlPatch.files.find(value=>value.path===file.path)
  assert.ok(urlFile,'the URL patch records each changed Python bundle')
  for(const {before,after} of urlFile.replacements){assert.equal(source.split(after).length-1,1);source=source.replace(after,before)}
  assert.equal(crypto.createHash('sha256').update(source).digest('hex'),urlFile.before_sha256)
  for(const {before,after} of file.replacements){assert.equal(source.split(after).length-1,1);source=source.replace(after,before)}
  assert.equal(crypto.createHash('sha256').update(source).digest('hex'),file.before_sha256)
 }
})
