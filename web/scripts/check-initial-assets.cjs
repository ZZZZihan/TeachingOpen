// Check the JS/CSS actually declared in the production HTML, including public scripts.
const { readFileSync } = require('node:fs')
const { resolve, join } = require('node:path')
const { gzipSync } = require('node:zlib')
const dist = resolve(process.argv[2] || 'dist')
const html = readFileSync(join(dist, 'index.html'), 'utf8')
const paths = new Set()
for (const tag of html.match(/<(?:script|link)\b[^>]*>/gi) || []) {
  const attrs = Object.fromEntries([...tag.matchAll(/([\w-]+)=(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g)]
    .map(([, key, double, single, bare]) => [key, double ?? single ?? bare]))
  if (attrs.rel === 'prefetch') throw new Error('Initial HTML must not prefetch every async route')
  const value = attrs.src || (['stylesheet', 'preload'].includes(attrs.rel) && attrs.href)
  if (!value) continue
  const url = new URL(value, 'https://local.invalid/')
  if (url.origin !== 'https://local.invalid' || !/\.(js|css)$/.test(url.pathname)) continue
  paths.add(url.pathname.slice(1))
}
if (!paths.size) throw new Error('No initial JS/CSS assets found')
const assets = [...paths].map(path => {
  const bytes = readFileSync(join(dist, path))
  return { path, bytes: bytes.length, gzipBytes: gzipSync(bytes, { level: 9 }).length }
})
const totals = assets.reduce((sum, asset) => ({ bytes: sum.bytes + asset.bytes, gzipBytes: sum.gzipBytes + asset.gzipBytes }), { bytes: 0, gzipBytes: 0 })
// Below the former 8.71 MiB entry; do not relax Webpack's warning thresholds.
const limits = { bytes: 3.25 * 1024 * 1024, gzipBytes: 0.9 * 1024 * 1024 }
console.log(JSON.stringify({ assets, totals, limits }, null, 2))
if (totals.bytes > limits.bytes || totals.gzipBytes > limits.gzipBytes) {
  console.error('Initial JS/CSS exceeds its budget. Inspect eager imports before changing a limit.')
  process.exitCode = 1
}
