// Actual MineWorkList and actual Index -> page/MineWorks mapping. Controlled read-only API.
const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process'); const crypto = require('node:crypto')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2]); const revision = process.argv[3]
if (!process.argv[2]) throw Error('Usage: node tests/student-feedback-preview/build.cjs OUTPUT [REVISION]')
const deps = fs.realpathSync(path.join(root, 'node_modules'))
fs.mkdirSync(out, { recursive: true })
const source = file => revision ? cp.execFileSync('git', ['show', `${revision}:web/${file}`], { cwd: root }) : fs.readFileSync(path.join(root, file))
const aliases = { vue$: 'vue/dist/vue.esm.js', '@/api/manage$': path.join(__dirname, 'api.js'), '@/utils/util$': path.join(__dirname, 'util.js'), '@/components/dict/JDictSelectTag.vue$': path.join(__dirname, 'dict.js'), '@/views/teaching/modules/TeachingWorkPreviewModal$': path.join(__dirname, 'preview-frame.js'), '@/components/page/PageLayout$': path.join(__dirname, 'unused.js'), '@assets': path.join(root, 'src/assets'), '@': path.join(root, 'src') }
const files = ['src/views/account/center/MineWorkList.vue', 'src/views/account/center/Index.vue', 'src/views/account/center/page/index.js', 'src/views/account/center/page/MineWorks.vue', 'src/mixins/JeecgListMixin.js', 'src/components/brand/CampusMasthead.vue', 'src/utils/filter.js']
for (const file of files.slice(0, 4)) { const target = path.join(out, 'frozen', file); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, source(file)) }
aliases['preview-list'] = path.join(out, 'frozen/src/views/account/center/MineWorkList.vue')
aliases['preview-center'] = path.join(out, 'frozen/src/views/account/center/Index.vue')
const manifest = { revision: revision || 'working tree', scope: 'Actual MineWorkList, actual Index and original page/MineWorks mapping; real shared JeecgListMixin, Vue and AntD. Ordinary sized container substitutes authenticated BasicLayout/RouteView. Synthetic loopback HTTP API; dictionary selector, unused PageLayout and unrelated preview iframe substituted. No session/auth/real teacher feedback.', sha256: Object.fromEntries(files.map(file => [file, crypto.createHash('sha256').update(source(file)).digest('hex')])) }
for (const file of ['src/components/teaching/StudentWorkFeedback.vue', 'src/utils/studentWorkFeedback.js']) if (fs.existsSync(path.join(root, file)) && !revision) manifest.sha256[file] = crypto.createHash('sha256').update(source(file)).digest('hex')
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>学生作品反馈 · 合成组件预览</title><div id="app"></div><script src="/preview.js"></script></html>')
webpack({ mode: 'development',
    devtool: false,
    context: root,
    entry: path.join(__dirname, 'entry.js'),
    output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
    resolve: { extensions: ['.js', '.vue'], modules: [deps], alias: aliases },
    resolveLoader: { modules: [deps] },
    module: { rules: [{ test: /\.vue$/, loader: 'vue-loader' }, { test: /\.(png|jpe?g|gif)$/, loader: 'url-loader', options: { limit: 0 } }, { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } }, { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', { loader: 'less-loader', options: { javascriptEnabled: true, modifyVars: { 'primary-color': '#74256A', 'border-radius-base': '3px' } } }] }] },
    plugins: [new VueLoaderPlugin()],
    performance: { hints: false }
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; ${revision || 'working tree'}; actual list and personal center, synthetic read-only HTTP.`) })
