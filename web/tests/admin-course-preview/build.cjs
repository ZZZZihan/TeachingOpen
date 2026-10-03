const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const crypto = require('node:crypto')
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.argv[2]), before = process.argv[3]
if (!process.argv[2]) throw new Error('Usage: node tests/admin-course-preview/build.cjs OUTPUT [BASE_REF]')
fs.mkdirSync(out, { recursive: true })
const files = { course: 'TeachingCourseList.vue', unit: 'TeachingCourseUnitList.vue' }, components = {}
const sourceHashes = {}
for (const [kind, file] of Object.entries(files)) {
  if (before) {
    let source = cp.execFileSync('git', ['show', `${before}:web/src/views/teaching/${file}`], { cwd: root, encoding: 'utf8' })
    sourceHashes[file] = crypto.createHash('sha256').update(source).digest('hex')
    source = source.replace(/from ['"]\.\/modules\/(TeachingCourse(?:Unit)?Modal)['"]/g, "from '@/views/teaching/modules/$1'")
      .replace(/from ['"]\.\.\/system\/DictItemList['"]/g, "from '@/views/system/DictItemList'")
    components[kind] = path.join(out, file); fs.writeFileSync(components[kind], source)
  } else { components[kind] = path.join(root, 'src/views/teaching', file); sourceHashes[file] = crypto.createHash('sha256').update(fs.readFileSync(components[kind])).digest('hex') }
}
for (const file of ['src/mixins/JeecgListMixin.js', ...(!before ? ['src/views/teaching/course-workbench.less'] : [])]) sourceHashes[file] = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify({ ref: before || 'working-tree', sourceHashes, scope: 'Actual course/unit list SFCs and shared list mixin. Vue/Ant are real; API, dict/depart and maintenance entry controls are synthetic replacements.' }, null, 2))
const aliases = { vue$: 'vue/dist/vue.esm.js', 'preview-course': components.course, 'preview-unit': components.unit,
  '@/utils/util$': path.join(__dirname, 'util.js'), '@/api/manage$': path.join(__dirname, 'api.js'), '@/utils/request$': path.join(__dirname, 'api.js'),
  '@/views/teaching/modules/TeachingCourseModal$': path.join(__dirname, 'entry-stub.js'), '@/views/teaching/modules/TeachingCourseUnitModal$': path.join(__dirname, 'entry-stub.js'),
  './modules/TeachingCourseModal$': path.join(__dirname, 'entry-stub.js'), './modules/TeachingCourseUnitModal$': path.join(__dirname, 'entry-stub.js'),
  '@/views/system/DictItemList$': path.join(__dirname, 'entry-stub.js'), '../system/DictItemList$': path.join(__dirname, 'entry-stub.js'),
  '@/components/jeecgbiz/JSelectDepart$': path.join(__dirname, 'depart.js'), '@/components/dict/JDictSelectTag$': path.join(__dirname, 'dict.js'),
  '@/components/dict/JDictSelectUtil$': path.join(__dirname, 'dict-util.js'), '@assets': path.join(root, 'src/assets'), '@': path.join(root, 'src') }
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>管理员课程工作台 · 本机合成组件预览</title><div id="app"></div><script src="preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias: aliases }, resolveLoader: { modules: [path.join(root, 'node_modules')] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] },
  plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; ${before || 'working tree'}; actual course/unit lists + inherited mixin + Vue/Ant; synthetic API, dictionary/department and modal/dictionary entry stubs; no login`) })
