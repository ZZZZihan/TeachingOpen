const path = require('path')
const CompressionPlugin = require("compression-webpack-plugin")

function resolve (dir) {
  return path.join(__dirname, dir)
}

// vue.config.js
module.exports = {
  // Tiptap's maintained vanilla API works in Vue 2; transpile its modern JS for webpack 4.
  transpileDependencies: [/@tiptap/, /prosemirror/, /dompurify/],
  /*
    Vue-cli3:
    Crashed when using Webpack `import()` #2463
    https://github.com/vuejs/vue-cli/issues/2463
   */
  // 如果你不需要生产环境的 source map，可以将其设置为 false 以加速生产环境构建。
  productionSourceMap: false,


  //打包app时放开该配置
  //publicPath:'./',
  configureWebpack: config => {
    // 生产环境取消 console.log
    if (process.env.NODE_ENV === 'production') {
      config.optimization.minimizer[0].options.terserOptions.compress.drop_console = true
      // Terser 1.x hashes its disk cache with MD4, unavailable in modern OpenSSL.
      config.optimization.minimizer[0].options.cache = false
      if (process.env.TEACHING_DEPENDENCY_REPORT === '1') {
        const RuntimeDependencyReport = require('./runtime-dependency-report.cjs')
        config.plugins.push(new RuntimeDependencyReport())
      }
    }
  },
  chainWebpack: (config) => {
    // webpack 4 predates package exports; point the official ProseMirror wrapper subpaths at their ESM files.
    for (const name of ['changeset', 'commands', 'dropcursor', 'gapcursor', 'history', 'inputrules', 'keymap', 'model', 'schema-list', 'state', 'tables', 'transform', 'view']) {
      config.resolve.alias.set('@tiptap/pm/' + name + '$', resolve('node_modules/@tiptap/pm/dist/' + name + '/index.js'))
    }
    // Load lazy route assets when visited instead of prefetching every async chunk.
    config.plugins.delete('prefetch')

    config.resolve.alias
      .set('@$', resolve('src'))
      .set('@api', resolve('src/api'))
      .set('@assets', resolve('src/assets'))
      .set('@comp', resolve('src/components'))
      .set('@views', resolve('src/views'))
      .set('@layout', resolve('src/layout'))
      .set('@static', resolve('src/static'))
      .set('@mobile', resolve('src/modules/mobile'))

    //生产环境，开启js\css压缩
    if (process.env.NODE_ENV === 'production') {
        config.plugin('compressionPlugin').use(new CompressionPlugin({
          test: /\.js$|.\css|.\less/, // 匹配文件名
          threshold: 10240, // 对超过10k的数据压缩
          deleteOriginalAssets: false // 不删除源文件
        }))
    }

    // 配置 webpack 识别 markdown 为普通的文件
    config.module
      .rule('markdown')
      .test(/\.md$/)
      .use()
      .loader('file-loader')
      .end()
  },

  css: {
    loaderOptions: {
      less: {
        modifyVars: {
          /* less 变量覆盖，用于自定义 ant design 主题 */
          'primary-color': '#146fc2',
          'link-color': '#146fc2',
          'border-radius-base': '4px'
        },
        javascriptEnabled: true
      }
    }
  },

  devServer: {
    port: 80,
    proxy: {
      '/api': {
        target: 'http://localhost:8081', 
        ws: true,
        changeOrigin: true
      },
    }
  },

  lintOnSave: undefined
}
