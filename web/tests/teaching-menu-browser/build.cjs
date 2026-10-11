const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process'), crypto = require('node:crypto')
module.exports = async function build (root, ref, out) {
  const modules = path.join(root, 'web/node_modules')
  const webpack = require(path.join(modules, 'webpack')), VueLoaderPlugin = require(path.join(modules, 'vue-loader/lib/plugin'))
  const files = ['web/src/views/home/modules/Header.vue', 'web/src/components/menu/tmenu.js', 'web/src/components/brand/CampusMasthead.vue', 'web/src/assets/brand/wordmark.svg', 'web/src/store/mutation-types.js']
  const hasPolicy = ref === 'working-tree' ? fs.existsSync(path.join(root, 'web/src/utils/teachingMenuUrl.js')) : cp.spawnSync('git', ['cat-file', '-e', ref + ':web/src/utils/teachingMenuUrl.js'], { cwd: root }).status === 0
  if (hasPolicy) files.push('web/src/utils/teachingMenuUrl.js')
  fs.mkdirSync(out, { recursive: true })
  const manifest = files.map(file => {
    const source = ref === 'working-tree' ? fs.readFileSync(path.join(root, file)) : cp.execFileSync('git', ['show', ref + ':' + file], { cwd: root })
    const target = path.join(out, file); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, source)
    return { file, sha256: crypto.createHash('sha256').update(source).digest('hex') }
  })
  fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>H05 菜单合成环境</title><div id="app"></div><script src="/preview.js"></script></html>')
  await new Promise((resolve, reject) => webpack({ mode: 'development', devtool: false, context: path.join(root, 'web'), entry: path.join(__dirname, 'entry.js'),
    output: { path: out, filename: 'preview.js', hashFunction: 'sha256' }, resolve: { extensions: ['.js', '.vue'], modules: [modules], alias: {
      vue$: path.join(modules, 'vue/dist/vue.esm.js'), 'fixture-header': path.join(out, files[0]), '@/api/manage$': path.join(__dirname, 'api.js'), '@': path.join(out, 'web/src') } },
    resolveLoader: { modules: [modules] }, module: { rules: [ { test: /\.vue$/, loader: 'vue-loader' },
      { test: /\.js$/, exclude: /node_modules/, loader: path.join(modules, '@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: path.join(root, 'web'), babelrc: false, configFile: false, presets: [[path.join(modules, '@vue/babel-preset-app'), { useBuiltIns: false }]] } },
      { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] }, { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] },
      { test: /\.svg$/, loader: 'url-loader' } ] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
  }, (error, stats) => error || stats.hasErrors() ? reject(error || new Error(stats.toString({ all: false, errors: true }))) : resolve()))
  return { ref, resolved_ref: cp.execFileSync('git', ['rev-parse', ref === 'working-tree' ? 'HEAD' : ref], { cwd: root, encoding: 'utf8' }).trim(), files: manifest }
}
