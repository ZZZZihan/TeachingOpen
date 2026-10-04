// Actual recovery SFCs and UserLayout; public requests use only the local synthetic server.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(path.join(__dirname, '../..'))
if (!process.argv[2]) throw Error('Usage: node tests/account-recovery-preview/build.cjs OUTPUT')
const out = path.resolve(process.argv[2]), deps = fs.realpathSync(path.join(root, 'node_modules'))
const files = ['src/views/user/Alteration.vue', 'src/views/user/Step1.vue', 'src/views/user/Step2.vue', 'src/views/user/Step3.vue', 'src/views/user/Step4.vue', 'src/api/accountRecovery.js', 'src/utils/accountRecovery.js', 'src/components/layouts/UserLayout.vue', 'src/components/brand/CampusMasthead.vue']
fs.mkdirSync(out, { recursive: true })
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify({ scope: 'Actual recovery SFCs, API functions and UserLayout. HTTP is synthetic, loopback-only. No real SMS, CAPTCHA bypass, authentication or password change.', sha256: Object.fromEntries(files.map(file => [file, crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')])) }, null, 2) + '\n')
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>找回密码 · 合成 HTTP 组件验证</title><div id="app"></div><script src="preview.js"></script></html>')
webpack({ mode: 'development', devtool: false, context: root, entry: path.join(__dirname, 'entry.js'), output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [deps], alias: { vue$: 'vue/dist/vue.esm.js', '@/utils/request$': path.join(__dirname, 'request.js'), '@/api/manage$': path.join(__dirname, 'manage.js'), '@': path.join(root, 'src') } }, resolveLoader: { modules: [deps] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.(png|jpe?g|gif)$/, loader: 'url-loader', options: { limit: 0 } }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', { loader: 'less-loader', options: { javascriptEnabled: true, modifyVars: { 'primary-color': '#74256A', 'border-radius-base': '3px' } } }] }] },
  plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log('Actual recovery SFC and UserLayout preview built; only loopback synthetic HTTP.') })
