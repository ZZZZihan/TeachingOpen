const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2] || '/tmp/task-preview'); const before = process.argv[3]
fs.mkdirSync(out, { recursive: true })
let dialog = path.join(root, 'src/views/account/course/MyAdditionalWorkList.vue')
if (before) { dialog = path.join(out, 'BeforeList.vue'); fs.writeFileSync(dialog, cp.execFileSync('git', ['show', `${before}:web/src/views/account/course/MyAdditionalWorkList.vue`], { cwd: root })) }
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>任务与反馈 · 本机组件预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
 resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: { vue$: 'vue/dist/vue.esm.js', 'preview-list': dialog, '@/utils/mixin.js$': path.join(__dirname, 'stubs.js'), '@/components/dict/JDictSelectTag.vue$': path.join(__dirname, 'dict-stub.js'), '@/utils/request$': path.join(__dirname, 'api.js'), '@/api/manage$': path.join(__dirname, 'api.js'), '@': path.join(root, 'src') } },
 resolveLoader: { modules: [path.join(root, 'node_modules')] }, module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; component ${before || 'working tree'}`) })
