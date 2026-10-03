// Real HTTP/DB contract probe; credentials arrive only on stdin from the owned Python runner.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const crypto = require('node:crypto')
const input = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = path.resolve(process.argv[2])
const scratch = require(path.join(source, 'web/public/scratch3/persistence.js'))
const python = require(path.join(source, 'web/public/python/persistence.js'))
const sfc = fs.readFileSync(path.join(source, 'web/src/views/account/course/modules/UnitViewModal.vue'), 'utf8')
const script = sfc.split('<script>')[1].split('</script>')[0].replace(/^import .*$/mg, '').replace('export default', 'module.exports =')
const sandbox = { module: { exports: {} }, URL, URLSearchParams, window: { location: { origin: input.origin } },
  getFileAccessHttpUrl: value => /^https?:/.test(value) ? value : input.origin + '/api/sys/common/static/' + value,
  getAction: () => {}, getFilePrevew: value => value }
vm.runInNewContext(script, sandbox)
const component = sandbox.module.exports
const cases = [], observations = []
const hash = value => crypto.createHash('sha256').update(value).digest('hex')
function check(name, passed) { cases.push({ case: name, passed: !!passed }) }
function endpoint(value) {
  const u = new URL(value, input.origin)
  if (!['http://127.0.0.1:18173', 'http://127.0.0.1:18174'].includes(u.origin) || !u.pathname.startsWith('/api/')) throw Error('Non-fixture address rejected')
  // This CLI probe talks directly to the actual backend, not a browser or its cookie session.
  return input.origin + u.pathname + u.search
}
async function request(value, options = {}, actor = 'student_a') {
  const response = await fetch(endpoint(value), { ...options, headers: { ...options.headers, 'X-Access-Token': input.tokens[actor] }, signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw Error('Synthetic HTTP request failed: ' + response.status)
  return response
}
async function api(value, body, actor) {
  const response = await request('/api' + value, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}, actor)
  const result = await response.json()
  if (!result || result.success !== true) throw Error('Synthetic business request failed')
  return result.result
}
async function upload(name, bytes) {
  const form = new FormData()
  form.append('file', new Blob([bytes]), name)
  form.append('bizPath', input.prefix)
  const result = await (await request('/api/sys/common/upload', { method: 'POST', body: form })).json()
  if (!result.success || !result.message) throw Error('Synthetic upload failed')
  return api('/system/sysFile/add', { filePath: result.message, fileName: name, fileLocation: 1, fileType: 2 })
}
async function main() {
  for (const fixture of input.fixtures) {
    const label = fixture.kind
    const mod = fixture.type === 4 ? python : scratch
    const unit = await api('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + fixture.unitId)
    const ctx = { unit }
    Object.assign(ctx, component.methods)
    const link = component.computed.workUrl.call(ctx)
    check(label + ': real course entry has unit and no explicit work ID', new URL(link, input.origin).searchParams.get('unitId') === fixture.unitId && !new URL(link, input.origin).searchParams.has('workId'))
    const params = mod.query(new URL(link, input.origin).search)
    const expected = Buffer.from(fixture.student, 'base64')
    const template = Buffer.from(fixture.template, 'base64')
    function editor() {
      const e = { content: null, title: '', infoCalls: 0, unitCalls: 0, bodies: [], events: [] }
      const options = {
        params, acceptedTypes: fixture.type === 3 ? ['3'] : ['1', '2'], workType: fixture.type,
        unit: async id => { e.unitCalls++; return api('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + encodeURIComponent(id)) },
        info: async id => { e.infoCalls++; return api('/teaching/teachingWork/studentWorkInfo?workId=' + encodeURIComponent(id)) },
        notify: state => e.events.push(state.phase), opened: () => {}, saved: () => {},
        title: () => e.title,
        open: async (url, title) => { e.title = title; e.content = Buffer.from(await (await request(url)).arrayBuffer()) },
        text: async url => (await request(url)).text(),
        apply: async (title, code) => { e.title = title; e.content = Buffer.from(code) },
        capture: async () => ({ project: new Blob([e.content]), cover: new Blob([Buffer.from(input.cover, 'base64')]) }),
        upload: async (title, snapshot) => {
          if (fixture.type === 4) return upload('student.py', Buffer.from(snapshot))
          const project = await upload('student.' + fixture.extension, Buffer.from(await snapshot.project.arrayBuffer()))
          const cover = await upload('cover.png', Buffer.from(await snapshot.cover.arrayBuffer()))
          return { project: project.id, cover: cover.id }
        },
        submit: async body => { e.bodies.push(body); return api('/teaching/teachingWork/submit', body) }
      }
      e.session = mod.create(options)
      e.save = () => fixture.type === 4 ? e.session.save(e.title, e.content.toString()) : e.session.save(0)
      return e
    }
    const first = editor()
    check(label + ': first entry loads the teacher template', await first.session.load() && first.content.equals(template))
    first.content = expected; first.title = label + ' 学生已保存修改'
    check(label + ': actual upload and first save succeed', await first.save())
    const id = first.session.state.workId
    check(label + ': server exposes the saved work in the same unit', !!id && (await api('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + fixture.unitId)).mineWorkId === id)
    const reopened = editor()
    check(label + ': close and reenter the original course URL restores student bytes', await reopened.session.load() && reopened.content.equals(expected))
    check(label + ': restored title and work ID match', reopened.title === first.title && reopened.session.state.workId === id)
    check(label + ': reentry resolves existing student details', reopened.unitCalls === 1 && reopened.infoCalls === 1)
    // A user can supply the title even when the old Python course entry leaves it empty.
    // Keep the loaded bytes untouched so the next actual save exposes template overwrite.
    reopened.title = first.title
    check(label + ': next save succeeds with original ID and unit', await reopened.save() && reopened.bodies[0].id === id && reopened.bodies[0].courseId === fixture.unitId)
    const saved = await api('/teaching/teachingWork/studentWorkInfo?workId=' + id)
    const final = Buffer.from(await (await request(saved.workFileKey_url)).arrayBuffer())
    check(label + ': database readback and attachment preserve student content', saved.workName === first.title && saved.courseId === fixture.unitId && final.equals(expected))
    observations.push({ kind: label, unitId: fixture.unitId, workId: id, reentryInfoCalls: reopened.infoCalls, reentryUnitCalls: reopened.unitCalls,
      templateSha256: hash(template), expectedStudentSha256: hash(expected), reopenedSha256: hash(reopened.content), finalSha256: hash(final) })
  }
}
main().then(() => {
  process.stdout.write(JSON.stringify({ passed: cases.filter(c => c.passed).length, total: cases.length, cases, observations }) + '\n')
  process.exitCode = cases.every(c => c.passed) ? 0 : 1
}).catch(error => { process.stdout.write(JSON.stringify({ passed: cases.filter(c => c.passed).length, total: cases.length, cases, observations, error: error.message }) + '\n'); process.exitCode = 2 })
