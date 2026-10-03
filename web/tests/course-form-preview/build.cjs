const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.argv[2]), before = process.argv[3]
fs.mkdirSync(out, { recursive: true })
let course = path.join(root, 'src/views/teaching/modules/TeachingCourseModal.vue')
let unit = path.join(root, 'src/views/teaching/modules/TeachingCourseUnitModal.vue')
if (before) {
  for (const file of ['TeachingCourseModal.vue', 'TeachingCourseUnitModal.vue']) {
    const target = path.join(out, file)
    let source = cp.execFileSync('git', ['show', `${before}:web/src/views/teaching/modules/${file}`], {cwd:root,encoding:'utf8'})
    source = source.replace("'./TeachingMapEditor'", "'@/views/teaching/modules/TeachingMapEditor'")
    fs.writeFileSync(target, source)
  }
  course = path.join(out,'TeachingCourseModal.vue'); unit = path.join(out,'TeachingCourseUnitModal.vue')
}
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课程表单 · 合成组件检查</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
 resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: { vue$: 'vue/dist/vue.esm.js', './TeachingMapEditor$': path.join(__dirname,'map.js'), '@/utils/util$': path.join(__dirname,'util.js'), 'preview-course': course, 'preview-unit': unit, '@/components/jeecg/JUpload$': path.join(__dirname,'field.js'), '@/components/jeecg/JEditor$': path.join(__dirname,'editor.js'), '@/components/jeecgbiz/JSelectDepart$': path.join(__dirname,'field.js'), '@/components/dict/JDictSelectTag$': path.join(__dirname,'field.js'), '@/views/teaching/modules/TeachingMapEditor$': path.join(__dirname,'map.js'), '@/api/manage$': path.join(__dirname,'api.js'), '@assets': path.join(root,'src/assets'), '@': path.join(root, 'src') } },
 resolveLoader: { modules: [path.join(root, 'node_modules')] }, module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; ${before || 'working tree'}; synthetic API and peripheral editor/upload/dict/depart/map controls; real course/unit form, Ant Design and JModal`) })
