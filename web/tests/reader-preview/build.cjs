// Render the real UnitViewModal and JModal against local synthetic data and media.
const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2] || '/tmp/teaching-reader-preview'); const base = process.argv[3]
fs.mkdirSync(out, { recursive: true })
let reader = path.join(root, 'src/views/account/course/modules/UnitViewModal.vue')
if (base) { reader = path.join(out, 'BeforeReader.vue'); fs.writeFileSync(reader, cp.execFileSync('git', ['show', `${base}:web/src/views/account/course/modules/UnitViewModal.vue`], { cwd: root })) }
fs.cpSync(path.join(__dirname, 'assets'), path.join(out, 'fixtures'), { recursive: true })
// Read-only built editor/player assets. The preview server has no API proxy or credentials.
for (const dir of ['scratch3', 'scratchjr', 'python', 'js']) {
  const dest = path.join(out, dir)
  if (!fs.existsSync(dest)) fs.symlinkSync(path.join(root, 'public', dir), dest, 'dir')
}
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>学习阅读器 · 本机媒体预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: path.join(__dirname, 'entry.js'), output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: { vue$: 'vue/dist/vue.esm.js', 'preview-reader': reader, '@/api/manage$': path.join(__dirname, 'fixtures.js'), '@/utils/util$': path.join(__dirname, 'resize.js'), '@': path.join(root, 'src') } },
  resolveLoader: { modules: [path.join(root, 'node_modules')] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] },
  plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Reader preview built: ${out}; ${base || 'working source'}; real modal, local media, synthetic API`) })
