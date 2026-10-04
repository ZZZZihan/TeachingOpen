// Freeze all product src dependencies; only explicit preview transports/controls are substituted.
const fs = require('node:fs'); const path = require('node:path'); const cp = require('node:child_process'); const crypto = require('node:crypto')
const webpack = require('webpack'); const VueLoaderPlugin = require('vue-loader/lib/plugin')
if (!process.argv[2]) throw Error('Usage: node tests/student-work-loading-preview/build.cjs OUTPUT [REVISION]')
const root = path.resolve(__dirname, '../..'); const out = path.resolve(process.argv[2]); const revision = process.argv[3]
const deps = fs.realpathSync(path.join(root, 'node_modules'))
const frozen = path.join(out, 'frozen'); const src = path.join(frozen, 'web/src')
fs.mkdirSync(frozen, { recursive: true })
if (revision) {
    const archive = cp.execFileSync('git', ['archive', revision, 'web/src'], { cwd: path.resolve(root, '..'), maxBuffer: 256 * 1024 * 1024 })
    cp.execFileSync('tar', ['-x', '-C', frozen], { input: archive, maxBuffer: 256 * 1024 * 1024 })
} else fs.cpSync(path.join(root, 'src'), src, { recursive: true })
const hashFiles = directory => fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name)
    return entry.isDirectory() ? hashFiles(file) : [[path.relative(path.join(frozen, 'web'), file), crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]]
})
const aliases = { vue$: 'vue/dist/vue.esm.js', 'preview-list': path.join(src, 'views/account/center/MineWorkList.vue'), 'preview-center': path.join(src, 'views/account/center/Index.vue'), '@/api/manage$': path.join(__dirname, 'api.js'), '@/utils/util$': path.join(__dirname, 'util.js'), '@/components/dict/JDictSelectTag.vue$': path.join(__dirname, 'dict.js'), '@/views/teaching/modules/TeachingWorkPreviewModal$': path.join(__dirname, 'preview-frame.js'), '@/components/page/PageLayout$': path.join(__dirname, 'unused.js'), '@assets': path.join(src, 'assets'), '@': src }
const manifest = { revision: revision || 'working tree', scope: 'Entire product src frozen; actual MineWorkList and Index → page/MineWorks, shared mixin, feedback, global filters, Vue and AntD. Ordinary container replaces authenticated layout. Axios controlled loopback read-only HTTP transport replaces manage and global auth/notification interceptors. Dictionary, unused PageLayout and unrelated preview iframe substituted. Synthetic timeout shortened to 1.2 seconds; product timeout unchanged. No session/auth/real data.', sha256: Object.fromEntries(hashFiles(src)) }
fs.writeFileSync(path.join(out, 'source-manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>学生作品加载 · 合成故障预览</title><div id="app"></div><script src="/preview.js"></script></html>')
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
}, (error, stats) => { if (error || stats.hasErrors()) { console.error(error || stats.toString({ all: false, errors: true })); process.exitCode = 1 } else console.log(`Built ${out}; ${revision || 'working tree'}; frozen src, actual list and personal center, synthetic fault HTTP.`) })
