// Executes the product's unmodified app.js with a small DOM adapter.
// This probes application state and storage branches; it is not a browser test,
// a DOM conformance test, or a keyboard/visual accessibility acceptance test.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';

const directory = dirname(fileURLToPath(import.meta.url));
const root = resolve(directory, '../../../..');
const source = readFileSync(resolve(root, 'design/club-learning-preview/app.js'), 'utf8');
const key = 'teachingopen-club-preview-v1';

function mount({ stored = null, hash = '#/learn/geometry', readDenied = false, writeDenied = false } = {}) {
  let record = stored;
  const writes = [];
  const handlers = {};
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, {
      innerHTML: '', textContent: '', value: '', open: false,
      dataset: {}, attrs: {},
      setAttribute(name, value) { this.attrs[name] = value; },
      removeAttribute(name) { delete this.attrs[name]; },
      getAttribute(name) { return this.attrs[name] || null; },
      focus() {}, scrollIntoView() {},
      showModal() { this.open = true; }, close() { this.open = false; },
    });
    return nodes.get(selector);
  };
  const location = { hash };
  const document = {
    title: '', querySelector: node, querySelectorAll: () => [],
    addEventListener(type, callback) { handlers[type] = callback; },
  };
  const window = {
    scrollTo() {}, setTimeout(callback) { callback(); },
    addEventListener(type, callback) { handlers[type] = callback; },
  };
  const localStorage = {
    getItem(requested) {
      assert.equal(requested, key);
      if (readDenied) throw new Error('SecurityError: simulated storage access denial');
      return record;
    },
    setItem(requested, value) {
      assert.equal(requested, key);
      if (writeDenied) throw new Error('QuotaExceededError: simulated write denial');
      record = value;
      writes.push({ key: requested, value });
    },
  };
  runInNewContext(source, { document, window, location, localStorage, Intl, Date }, { filename: 'app.js' });
  return {
    node, document, get html() { return node('#main').innerHTML; },
    get record() { return record; }, writes,
    input(id, value, dataset = {}) { handlers.input({ target: { id, value, dataset } }); },
    change(dataset, checked) { handlers.change({ target: { dataset, checked } }); },
    click(action, dataset = {}) {
      const button = { dataset: { action, ...dataset }, textContent: '' };
      handlers.click({ target: { closest(selector) { return selector === '[data-action]' ? button : null; } }, preventDefault() {} });
    },
    route(next) { location.hash = next; handlers.hashchange(); },
  };
}

const scenarios = [];
function probe(name, operation) {
  try { scenarios.push({ name, passed: true, details: operation() }); }
  catch (error) { scenarios.push({ name, passed: false, error: error.message }); }
}

probe('save_reload_continue_actual_edits', () => {
  const page = mount();
  page.input('rotation', '37', { param: 'rotation' });
  page.input('work-title', '37度花园');
  page.input('work-note', '只改角度，观察线条重叠。');
  page.click('complete-step');
  page.change({ task: '1' }, true);
  page.click('save');
  const saved = JSON.parse(page.record);
  assert.equal(saved.params.rotation, 37);
  assert.equal(saved.title, '37度花园');
  assert.equal(saved.note, '只改角度，观察线条重叠。');
  assert.deepEqual(saved.completed, [0]);
  assert.deepEqual(saved.tasks, [1]);
  assert.equal(page.writes.length, 1);
  const reloaded = mount({ stored: page.record, hash: '#/studio' });
  assert.match(reloaded.html, /37度花园/);
  assert.match(reloaded.html, /只改角度，观察线条重叠。/);
  assert.match(reloaded.html, /松绿 \/ 37°/);
  assert.match(reloaded.html, /aria-valuenow="1"/);
  reloaded.route('#/learn/geometry');
  assert.match(reloaded.html, /id="rotation"[^>]*value="37"/);
  assert.match(reloaded.html, /value="37度花园"/);
  reloaded.click('tab', { tab: 'basic' });
  assert.match(reloaded.node('#learning-panel').innerHTML, /data-task="1" checked/);
  return { savedFields: ['params', 'title', 'note', 'completed', 'tasks'], writes: page.writes.length };
});

probe('write_failure_keeps_session_without_claiming_save', () => {
  const page = mount({ writeDenied: true });
  page.input('rotation', '45', { param: 'rotation' });
  page.input('work-title', '未保存的45度');
  page.click('save');
  assert.equal(page.record, null);
  assert.equal(page.writes.length, 0);
  assert.match(page.node('#save-caption').textContent, /无法保存/);
  assert.match(page.node('#announcer').textContent, /仍留在这次页面中/);
  page.route('#/studio');
  assert.match(page.html, /未保存的45度/);
  assert.match(page.html, /松绿 \/ 45°/);
  const reloaded = mount({ stored: page.record });
  assert.match(reloaded.html, /id="rotation"[^>]*value="28"/);
  return { successfulWrites: 0, retainedUntilReload: true, newMountRestoredDefault: true };
});

probe('read_denial_can_render_and_edit', () => {
  const page = mount({ readDenied: true, writeDenied: true });
  assert.match(page.html, /当前浏览器无法保存/);
  page.input('rotation', '29', { param: 'rotation' });
  assert.match(page.node('#pattern-summary').textContent, /29°/);
  return { renderedDefault: true, editedInSession: true };
});

for (const [name, stored] of [
  ['corrupt_json', '{'],
  ['null_parameters', JSON.stringify({ version: 1, params: null, title: '旧作品', note: '', savedAt: '2026-10-05T10:00:00Z' })],
  ['wrong_version', JSON.stringify({ version: 2, params: {}, title: '旧作品', note: '', savedAt: '2026-10-05T10:00:00Z' })],
]) probe(`${name}_recovery_does_not_delete_before_save`, () => {
  const page = mount({ stored });
  assert.match(page.html, /旧记录未能读取/);
  assert.doesNotMatch(page.html, /当前浏览器无法保存/);
  assert.equal(page.record, stored);
  assert.equal(page.writes.length, 0);
  page.click('save');
  assert.equal(page.writes.length, 1);
  assert.doesNotMatch(page.node('#save-caption').textContent, /旧记录未能读取/);
  assert.match(page.node('#save-button').textContent, /已保存到本机/);
  return { untouchedBeforeExplicitSave: true, recoveredWithOneExplicitSave: true };
});

probe('restored_fields_are_bounded_deduplicated_and_escaped', () => {
  const page = mount({ stored: JSON.stringify({
    version: 1, params: { sides: 9000, repeats: -3, rotation: 99, color: 'red" onload="alert(1)' },
    title: '<img src=x onerror=alert(1)>', note: '<script>alert(1)</script>',
    completed: [0, 0, 3, -1, 42], tasks: [2, 2, -1, 42], savedAt: '2026-10-05T10:00:00Z',
  }) });
  assert.match(page.html, /id="sides"[^>]*value="8"/);
  assert.match(page.html, /id="repeats"[^>]*value="4"/);
  assert.match(page.html, /id="rotation"[^>]*value="90"/);
  assert.match(page.html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(page.html, /<script>|<img src=x|stroke="red/);
  page.click('save');
  const saved = JSON.parse(page.record);
  assert.deepEqual(saved.completed, [0, 3]);
  assert.deepEqual(saved.tasks, [2]);
  assert.equal(saved.params.color, '#146d5d');
  return { bounds: { sides: 8, repeats: 4, rotation: 90 }, completed: saved.completed, tasks: saved.tasks, textEscaped: true };
});

probe('dirty_saved_work_resumes_session_and_reload_restores_saved_snapshot', () => {
  const page = mount();
  page.input('work-title', '已保存标题'); page.click('save');
  const saved = page.record;
  page.input('work-title', '本次尚未保存标题');
  page.route('#/studio');
  assert.match(page.html, /本次尚未保存标题/);
  assert.match(page.html, /有尚未保存的修改/);
  const reloaded = mount({ stored: saved, hash: '#/studio' });
  assert.match(reloaded.html, /已保存标题/);
  assert.doesNotMatch(reloaded.html, /本次尚未保存标题/);
  return { sessionDraftVisible: true, reloadUsesLastSavedSnapshot: true };
});

probe('generated_routes_and_project_idea_destinations', () => {
  const page = mount({ hash: '#/unknown-project' });
  assert.equal(page.document.title, '探索项目 · 开放创作');
  assert.match(page.html, /href="#\/learn\/geometry"/);
  assert.match(page.html, /data-project="sound"/);
  assert.match(page.html, /data-project="bridge"/);
  for (const project of ['sound', 'bridge']) {
    page.click('project-idea', { project });
    assert.equal(page.node('#project-dialog').open, true);
    assert.match(page.node('#dialog-content').innerHTML, project === 'sound' ? /给校园留个声音/ : /一张纸的桥梁/);
    page.click('close-dialog');
    assert.equal(page.node('#project-dialog').open, false);
  }
  const routes = ['#/', '#/studio', '#/learn/geometry', '#/learn/geometry/notes', '#/learn/geometry/feedback', '#/learn/geometry/challenge'];
  for (const route of routes) { page.route(route); assert.ok(page.html.length > 100); }
  return { knownRoutesRendered: routes, unknownHashFallback: 'home', projectIdeaBranches: ['sound', 'bridge'] };
});

const report = {
  scope: 'Unmodified app.js executed by Node VM with a minimal DOM adapter. Application-state/storage branches only; no real browser, network, login, database, or product API.',
  sourceSha256: createHash('sha256').update(source).digest('hex'),
  scenarios,
};
const output = resolve(directory, 'storage-route-probe-result.json');
writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ sourceSha256: report.sourceSha256, scenarios, resultPath: output }, null, 2));
process.exitCode = scenarios.some((entry) => !entry.passed) ? 1 : 0;
