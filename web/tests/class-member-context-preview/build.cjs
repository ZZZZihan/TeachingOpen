// Actual four member-management SFCs with synthetic transport and peripheral selectors.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(process.env.PREVIEW_SOURCE_ROOT || path.join(__dirname, '../..'))
if (!process.argv[2]) throw Error('Usage: node tests/class-member-context-preview/build.cjs OUTPUT')
const out = path.resolve(process.argv[2]), deps = fs.realpathSync(path.join(root, 'node_modules'))
const files = ['DeptUserInfo', 'SelectUserModal', 'UserModal', 'DeptRoleUserModal'].map(name => 'src/views/system/modules/' + name + '.vue')
fs.mkdirSync(out, { recursive: true })
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify({ scope: 'Actual member SFCs and list mixin. Memory API; position/department/avatar helpers substituted. Not authenticated E2E.', sha256: Object.fromEntries(files.map(file => [file, crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')])) }, null, 2) + '\n')
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>班级成员 · 合成组件验证</title><div id="app"></div><script src="preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root,
  entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')], output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [deps], alias: { vue$: 'vue/dist/vue.esm.js', '@/api/manage$': path.join(__dirname, 'api.js'), '@/api/api$': path.join(__dirname, 'api.js'), '@/utils/authFilter$': path.join(__dirname, 'api.js'), '@/components/dict/JDictSelectUtil$': path.join(__dirname, 'api.js'), '@/utils/util$': path.join(__dirname, '../admin-course-preview/util.js'), '@': path.join(root, 'src') } }, resolveLoader: { modules: [deps] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }] },
  plugins: [new VueLoaderPlugin(), new webpack.NormalModuleReplacementPlugin(/(?:^|\/)(?:DepartWindow|JSelectPosition|JImageUpload)(?:\.vue)?$/, path.join(__dirname, 'peripheral.js'))], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log('Actual member SFC preview built; synthetic API; no authenticated E2E.') })
