const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.argv[2]), before = process.argv[3]
fs.mkdirSync(out, { recursive: true })
let component = path.join(root, 'src/views/teaching/TeachingWorkList.vue')
if (before) {
  const files = ['TeachingWorkList.vue', 'modules/TeachingWorkModal.vue', 'modules/TeachingWorkCorrectForm.vue', 'modules/TeachingWorkPreviewModal.vue']
  for (const file of files) {
    const target = path.join(out, file); fs.mkdirSync(path.dirname(target), { recursive: true })
    let text = cp.execFileSync('git', ['show', `${before}:web/src/views/teaching/${file}`], { cwd: root, encoding: 'utf8' })
    text = text.replace("'../system/modules/SelectUserModal'", "'@/views/system/modules/SelectUserModal.vue'")
    fs.writeFileSync(target, text)
  }
  component = path.join(out, 'TeachingWorkList.vue')
}
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>教师作业 · 合成组件预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
 resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: { vue$: 'vue/dist/vue.esm.js', 'preview-list': component, '@/utils/util$': path.join(__dirname, 'util.js'), '@/views/system/modules/SelectUserModal.vue$': path.join(__dirname, 'select-user.js'), '@/components/dict/JDictSelectTag.vue$': path.join(__dirname, 'dict.js'), '@/components/dict/JDictSelectTag$': path.join(__dirname, 'dict.js'), '@/utils/request$': path.join(__dirname, 'api.js'), '@/api/manage$': path.join(__dirname, 'api.js'), '@assets': path.join(root,'src/assets'), '@': path.join(root, 'src') } },
 resolveLoader: { modules: [path.join(root, 'node_modules')] }, module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; ${before || 'working tree'}; synthetic API + dict/recipient/old comment-table substitutes; real list and grading components`) })
