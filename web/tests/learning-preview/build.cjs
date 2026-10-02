// Isolated component preview. No authentication, API server, store or business writes.
// Usage: node tests/learning-preview/build.cjs OUTPUT_DIRECTORY [BASE_GIT_REF]
const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2] || '/tmp/teaching-learning-preview')
const source = path.join(root, 'src/views/account/course'); const base = process.argv[3]
fs.mkdirSync(out, { recursive: true })
const chosen = base ? path.join(out, 'baseline') : source
if (base) {
  fs.mkdirSync(chosen, { recursive: true })
  for (const name of ['CourseListCard.vue', 'CourseUnitListCard.vue']) fs.writeFileSync(path.join(chosen, name), cp.execFileSync('git', ['show', `${base}:web/src/views/account/course/${name}`], { cwd: root }))
}
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课程学习入口 · 合成组件预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: path.join(__dirname, 'entry.js'), output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: {
    vue$: 'vue/dist/vue.esm.js',
    'preview-courses': path.join(chosen, 'CourseListCard.vue'), 'preview-units': path.join(chosen, 'CourseUnitListCard.vue'),
    '@/api/manage$': path.join(__dirname, 'fixtures.js'), '@/mixins/JeecgListMixin$': path.join(__dirname, 'reader-stub.js'), '@': path.join(root, 'src')
  } },
  resolveLoader: { modules: [path.join(root, 'node_modules')] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] },
  plugins: [new VueLoaderPlugin(), new webpack.NormalModuleReplacementPlugin(/\.\/modules\/UnitViewModal$/, path.join(__dirname, 'reader-stub.js'))],
  performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Preview built: ${out}; ${base || 'working source'}; isolated synthetic data`) })
