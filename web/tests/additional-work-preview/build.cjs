const fs = require('node:fs')
const path = require('node:path')
const cp = require('node:child_process')
const webpack = require('webpack')
const VueLoaderPlugin = require('vue-loader/lib/plugin')
const defaultRoot = path.resolve(__dirname, '../..')

module.exports = function build (out, before, root = defaultRoot) {
  fs.mkdirSync(out, { recursive: true })
  let component = path.join(root, 'src/views/teaching/modules/TeachingAdditionalWorkModal.vue')
  if (before) {
    component = path.join(out, 'TeachingAdditionalWorkModal.vue')
    fs.writeFileSync(component, cp.execFileSync('git', ['show', `${before}:web/src/views/teaching/modules/TeachingAdditionalWorkModal.vue`], { cwd: root }))
  }
  fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>附加作业 · 本机合成验证</title><div id="app"></div><script src="./preview.js"></script></html>')
  const modules = [path.join(root, 'node_modules'), ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean)]
  return new Promise((resolve, reject) => webpack({
    mode: 'development', devtool: false, context: root,
    entry: [path.join(__dirname, '../assignment-preview/bootstrap.js'), path.join(__dirname, 'entry.js')],
    output: { path: out, filename: 'preview.js', hashFunction: 'sha256' },
    resolve: { extensions: ['.js', '.vue'], modules, alias: {
      vue$: 'vue/dist/vue.esm.js', 'preview-additional': component,
      '@/api/manage$': path.join(__dirname, 'api.js'), '@/api/api$': path.join(__dirname, 'api.js'),
      '@/utils/util$': path.join(__dirname, '../course-form-preview/util.js'), '@': path.join(root, 'src')
    } },
    resolveLoader: { modules },
    module: { rules: [
      { test: /\.vue$/, loader: 'vue-loader' },
      { test: /\.js$/, exclude: /node_modules/, loader: require.resolve('@vue/cli-plugin-babel/node_modules/babel-loader'), options: { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] } },
      { test: /\.css$/, use: ['vue-style-loader', 'css-loader'] },
      { test: /\.less$/, use: ['vue-style-loader', 'css-loader', 'less-loader'] }
    ] }, plugins: [new VueLoaderPlugin()], performance: { hints: false }
  }, (error, stats) => error || stats.hasErrors() ? reject(error || new Error(stats.toString({ all: false, errors: true }))) : resolve(component)))
}
