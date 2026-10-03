// Actual three SFCs, inherited list mixin, Vue/Antd and JDate; only API/storage are synthetic.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.argv[2] || '')
if (!process.argv[2]) throw Error('Usage: node tests/class-course-context-preview/build.cjs OUTPUT')
const deps = fs.realpathSync(process.env.NODE_PATH || path.join(root, 'node_modules'))
fs.mkdirSync(out, { recursive: true })
const files = ['src/views/system/modules/DeptCourseInfo.vue', 'src/views/teaching/modules/SelectCourseModal.vue', 'src/views/teaching/modules/TeachingCourseDeptModal.vue', 'src/mixins/JeecgListMixin.js', 'src/components/jeecg/JDate.vue']
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify({ scope: 'Actual Vue/Antd components with controlled API; no login, backend or database.', sha256: Object.fromEntries(files.map(file => [file, crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')])) }, null, 2) + '\n')
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>班级课程上下文 · 合成组件检查</title><div id="app"></div><script src="preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [deps], alias: { vue$: 'vue/dist/vue.esm.js', '@/api/manage$': path.join(__dirname, 'api.js'), '@/utils/util$': path.join(__dirname, '../admin-course-preview/util.js'), '@': path.join(root, 'src') } }, resolveLoader: { modules: [deps] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log('Actual class course SFC preview built; controlled API; no authenticated E2E.') })
