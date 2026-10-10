const fs = require('fs')
const path = require('path')
const crypto = require('crypto')

// Capture emitted browser modules, including concatenated and lazy route modules.
// Build-tool dependencies declared as production dependencies are not browser code.
class RuntimeDependencyReport {
  apply (compiler) {
    compiler.hooks.done.tap('RuntimeDependencyReport', stats => {
      if (stats.hasErrors()) return
      const packages = new Set()
      const walk = (modules, inherited = false) => {
        for (const module of modules || []) {
          const emitted = inherited || Boolean(module.chunks && module.chunks.length)
          const name = (module.name || '').split('!').pop().replace(/\\/g, '/')
          if (emitted && name.includes('node_modules/')) {
            const parts = name.slice(name.indexOf('node_modules/')).split('/')
            const index = parts.lastIndexOf('node_modules')
            const end = index + (parts[index + 1].startsWith('@') ? 3 : 2)
            packages.add(parts.slice(0, end).join('/'))
          }
          walk(module.modules, emitted)
        }
      }
      walk(stats.toJson({ all: false, modules: true, nestedModules: true, source: false }).modules)
      if (!packages.size) throw Error('Production module inventory is empty')
      const lock = fs.readFileSync(path.join(__dirname, 'package-lock.json'))
      fs.writeFileSync(path.join(compiler.options.output.path, 'runtime-dependencies.json'), JSON.stringify({
        lock_sha256: crypto.createHash('sha256').update(lock).digest('hex'), packages: [...packages].sort()
      }, null, 2) + '\n')
    })
  }
}
module.exports = RuntimeDependencyReport
