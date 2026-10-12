// Compile the real Vue SFCs and real Ant/JCron/dictionary widgets. Only API boundaries are synthetic.
const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process'), crypto = require('node:crypto')
const root = path.resolve(process.argv[2]), ref = process.argv[3], out = path.resolve(process.argv[4])
const modules = path.resolve(process.env.TEACHING_NODE_MODULES)
const webpack = require(path.join(modules, 'webpack')), VueLoaderPlugin = require(path.join(modules, 'vue-loader/lib/plugin'))
const files = ['web/src/views/system/modules/SysDataSourceModal.vue', 'web/src/views/system/modules/QuartzJobModal.vue', 'web/src/components/dict/JDictSelectTag.vue', 'web/src/components/jeecg/JCron.vue', 'web/src/components/jeecg/modal/JCronModal.vue']
fs.mkdirSync(out, { recursive: true })
const manifests = files.map(file => {
  const source = ref === 'working-tree' ? fs.readFileSync(path.join(root, file), 'utf8') : cp.execFileSync('git', ['show', ref + ':' + file], { cwd: root, encoding: 'utf8' })
  const target = path.join(out, file)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, source)
  return { file, sha256: crypto.createHash('sha256').update(source).digest('hex') }
})
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify({ root, ref, resolved_ref: cp.execFileSync('git', ['rev-parse', ref === 'working-tree' ? 'HEAD' : ref], {cwd:root,encoding:'utf8'}).trim(), files: manifests }, null, 2))
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>H01 运维弹窗 · 合成环境</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: path.join(root, 'web'),
  entry: path.join(__dirname, 'entry.js'), output: {path:out, filename:'preview.js',hashFunction:'sha256'},
  resolve: {extensions:['.js','.vue'],modules:[modules],alias:{
    vue$:path.join(modules,'vue/dist/vue.esm.js'),
    'preview-data-source':path.join(out,files[0]), 'preview-quartz':path.join(out,files[1]),
    'preview-dict':path.join(out,files[2]),
    '@/components/jeecg/JCron$':path.join(out,files[3]),
    '@/api/manage$':path.join(__dirname,'api.js'), '@/api/api$':path.join(__dirname,'dict-api.js'),
    '@/utils/util$':path.join(__dirname,'util.js'), '@':path.join(root,'web/src') }},
  resolveLoader:{modules:[modules]},
  module:{rules:[{test:/\.vue$/,loader:'vue-loader'}, {test:/\.js$/,exclude:/node_modules/,loader:path.join(modules,'@vue/cli-plugin-babel/node_modules/babel-loader'),options:{cwd:path.join(root,'web'),babelrc:false,configFile:false,presets:[[path.join(modules,'@vue/babel-preset-app'),{useBuiltIns:false}]]}},
    {test:/\.css$/,use:['vue-style-loader','css-loader']}, {test:/\.less$/,use:['vue-style-loader','css-loader','less-loader']}]},
  plugins:[new VueLoaderPlugin()],performance:{hints:false}
}, (error, stats) => {
  if (error || stats.hasErrors()) { console.error(error || stats.toString({all:false,errors:true})); process.exitCode=1 }
  else console.log(JSON.stringify({built:out,ref,source_files:manifests.length,synthetic:'API requests and dictionary data only'}))
})
