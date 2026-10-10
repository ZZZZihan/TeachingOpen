const fs = require('node:fs'), path = require('node:path')
const webpack = require('webpack'), VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.argv[2])
fs.mkdirSync(out, { recursive: true })
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>新闻编辑验证</title><div id="app"></div><script src="/preview.js"></script></html>')
const alias = { vue$: 'vue/dist/vue.esm.js', '@/api/manage$': path.join(__dirname, 'api.js'), '@/utils/util$': path.join(__dirname, 'util.js'), '@/components/dict/JDictSelectTag$': path.join(__dirname, 'dict.js'), '@': path.join(root, 'src') }
for (const name of ['changeset', 'commands', 'dropcursor', 'gapcursor', 'history', 'inputrules', 'keymap', 'model', 'schema-list', 'state', 'tables', 'transform', 'view']) alias['@tiptap/pm/' + name + '$'] = path.join(root, 'node_modules/@tiptap/pm/dist/' + name + '/index.js')
webpack({ mode: 'development', devtool: false, context: root, entry: path.join(__dirname, 'entry.js'), output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
  resolve: { extensions: ['.js', '.vue'], modules: [path.join(root, 'node_modules')], alias }, resolveLoader: { modules: [path.join(root, 'node_modules')] },
  module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.js$/, exclude: /node_modules\/(?!@tiptap|prosemirror|dompurify)/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', { loader: 'less-loader', options: { javascriptEnabled: true } }] }] },
  plugins: [new VueLoaderPlugin()], performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log('Real JEditor / TeachingNewsModal / NewsDetail built. Real HTTP adapter; dictionary selector substituted.') })
