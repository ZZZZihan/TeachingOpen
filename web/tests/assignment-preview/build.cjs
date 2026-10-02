const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2] || '/tmp/assignment-preview'); const before = process.argv[3]
fs.mkdirSync(out, { recursive: true })
let dialog = path.join(root, 'src/views/teaching/modules/TeachingWorkSubmitModal.vue')
if (before) { dialog = path.join(out, 'BeforeSubmit.vue'); fs.writeFileSync(dialog, cp.execFileSync('git', ['show', `${before}:web/src/views/teaching/modules/TeachingWorkSubmitModal.vue`], { cwd: root })) }
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>文件作业提交 · 本机预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, 'bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
 resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: { vue$: 'vue/dist/vue.esm.js', 'preview-dialog': dialog, '@/utils/request$': path.join(__dirname, 'api.js'), '@/api/manage$': path.join(__dirname, 'api.js'), '@': path.join(root, 'src') } },
 resolveLoader: { modules: [path.join(root, 'node_modules')] }, module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; component ${before || 'working tree'}`) })
