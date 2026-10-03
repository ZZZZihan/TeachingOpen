const { test } = require('node:test')
const assert = require('node:assert/strict')
const { mount, flush, row, success } = require('./admin-course-harness.cjs')

for (const kind of ['course', 'unit']) {
  test(`${kind} baseline: draft query enters a pagination request before query submission`, () => {
    const h = mount(kind, { old: true }); h.i.queryParam[kind === 'course' ? 'courseName' : 'courseId'] = 'synthetic-draft'
    h.i.handleTableChange({ ...h.i.ipagination, current: 2 }, {}, {})
    assert.equal(h.calls[0].data[kind === 'course' ? 'courseName' : 'courseId'], 'synthetic-draft')
    h.calls[0].resolve(success(kind))
  })
  test(`${kind} baseline: late response overwrites newer query`, async () => {
    const h = mount(kind, { old: true }); h.i.loadData(); h.i.searchQuery()
    h.calls[1].resolve(success(kind, 1, [{ ...row(kind), id: 'new' }])); await flush()
    h.calls[0].resolve(success(kind, 99, [{ ...row(kind), id: 'old' }])); await flush()
    assert.equal(h.i.dataSource[0].id, 'old'); assert.equal(h.i.ipagination.total, 99)
  })
  test(`${kind} baseline: business rejection silently retains old rows`, async () => {
    const h = mount(kind, { old: true }); h.i.dataSource = [row(kind)]; h.i.loadData()
    h.calls[0].resolve({ success: false, message: 'synthetic rejection' }); await flush()
    assert.equal(h.i.dataSource.length, 1); assert.equal(h.i.listError, undefined)
  })
  test(`${kind} baseline: repeated delete dispatches two actual DELETE requests`, async () => {
    const h = mount(kind, { old: true }); h.i.handleDelete(row(kind).id); h.i.handleDelete(row(kind).id)
    assert.equal(h.calls.filter(call => call.method === 'DELETE').length, 2)
    h.calls.forEach(call => call.resolve({ success: false, message: 'synthetic rejection' })); await flush()
  })
}
test('unit baseline: initial route sends both unfiltered and filtered list requests', async () => {
  const h = mount('unit', { old: true, courseId: 'synthetic-course-1' }); h.created()
  assert.equal(h.calls.length, 2); assert.equal(h.calls[0].data.courseId, undefined); assert.equal(h.calls[1].data.courseId, 'synthetic-course-1')
  h.calls.forEach(call => call.resolve(success('unit'))); await flush()
})

for (const kind of ['course', 'unit']) {
  const field = kind === 'course' ? 'courseName' : 'courseId'
  const queryValue = kind === 'course' ? '合成课程' : 'synthetic-course-1'
  test(`${kind}: one initial request, preserving route filter and raw maintenance fields`, async () => {
    const h = mount(kind, { courseId: 'synthetic-course-1' }); h.created()
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].data.pageNo, 1)
    if (kind === 'unit') assert.equal(h.calls[0].data.courseId, 'synthetic-course-1')
    const fields = h.calls[0].data.field.split(',')
    for (const name of kind === 'course' ? ['id', 'courseType', 'courseCategory', 'isShared', 'showHome', 'departIds', 'courseDesc', 'courseMap'] : ['id', 'courseId', 'unitIntro', 'courseWorkType', 'courseVideo', 'showCourseVideo', 'showCourseCase', 'mediaContent']) assert.ok(fields.includes(name), name)
    h.calls[0].resolve(success(kind)); await flush(); assert.equal(h.i.dataSource[0].id, row(kind).id)
  })
  test(`${kind}: query and reset return to page one, preserve page size and draft isolation`, async () => {
    const h = mount(kind); h.i.ipagination.current = 3; h.i.ipagination.pageSize = 20; h.i.queryParam[field] = queryValue
    let done = h.i.searchQuery(); assert.equal(h.calls[0].data[field], queryValue); assert.equal(h.calls[0].data.pageNo, 1); assert.equal(h.calls[0].data.pageSize, 20)
    h.calls[0].resolve(success(kind, 50)); await done
    h.i.queryParam[field] = 'synthetic-unsent'; done = h.i.changePage(2)
    assert.equal(h.calls[1].data[field], queryValue); assert.equal(h.calls[1].data.pageNo, 2)
    h.calls[1].resolve(success(kind, 50)); await done
    done = h.i.searchReset(); assert.equal(h.calls[2].data[field], undefined); assert.equal(h.calls[2].data.pageNo, 1); assert.equal(h.calls[2].data.pageSize, 20)
    h.calls[2].resolve(success(kind)); await done; assert.equal(h.i.hasAppliedFilters, false)
  })
  test(`${kind}: page size and sorting carry applied filters, reject invalid or busy changes`, async () => {
    const h = mount(kind); h.i.queryParam[field] = queryValue
    let done = h.i.searchQuery(); h.calls[0].resolve(success(kind, 50)); await done
    h.i.queryParam[field] = 'unsent'; done = h.i.changePageSize('30')
    assert.equal(h.calls[1].data.pageSize, 30); assert.equal(h.calls[1].data[field], queryValue)
    h.i.changePageSize('10'); h.i.changeSort('orderNum:asc'); assert.equal(h.calls.length, 2)
    h.calls[1].resolve(success(kind, 50)); await done
    done = h.i.changeSort('orderNum:asc'); assert.equal(h.calls[2].data.column, 'orderNum'); assert.equal(h.calls[2].data.order, 'asc'); assert.equal(h.calls[2].data.pageNo, 1); assert.equal(h.calls[2].data[field], queryValue)
    h.calls[2].resolve(success(kind, 50)); await done
    h.i.changePageSize('999'); h.i.changeSort('bad:asc'); h.i.changePage(99); assert.equal(h.calls.length, 3)
  })
  test(`${kind}: failures and malformed responses clear stale rows and recover same query`, async () => {
    const h = mount(kind); h.i.queryParam[field] = queryValue
    for (const bad of ['network', null, {}, { success: false, message: 'SQL secret' }, { success: 'true', result: { records: [], total: 0 } }, { success: true, result: null }, { success: true, result: { records: [null], total: 1 } }, { success: true, result: { records: [{ id: '' }], total: 1 } }, { success: true, result: { records: [], total: -1 } }, { success: true, result: { records: [], total: 'bad' } }, { success: true, result: { records: [] } }]) {
      h.i.dataSource = [row(kind)]; h.i.ipagination.total = 99; h.i.selectedRowKeys = [row(kind).id]; h.i.selectionRows = [row(kind)]
      const done = h.i.searchQuery(), call = h.calls.at(-1)
      assert.equal(h.i.loading, true); assert.equal(h.i.selectedRowKeys.length, 0)
      if (bad === 'network') call.reject(new Error('synthetic offline')); else call.resolve(bad)
      await done
      assert.equal(h.i.loading, false); assert.equal(h.i.dataSource.length, 0); assert.equal(h.i.ipagination.total, 0); assert.ok(h.i.listError); assert.doesNotMatch(h.i.listError, /SQL/); assert.equal(h.i.queryParam[field], queryValue)
    }
    const done = h.i.loadData(); assert.equal(h.calls.at(-1).data[field], queryValue); h.calls.at(-1).resolve(success(kind)); await done
    assert.equal(h.i.listError, ''); assert.equal(h.i.dataSource.length, 1)
  })
  test(`${kind}: old success cannot replace newer rows or stop the active loading state`, async () => {
    const h = mount(kind); const older = h.i.loadData(), newer = h.i.searchQuery()
    h.calls[0].resolve(success(kind, 99, [{ ...row(kind), id: 'old' }])); await older
    assert.equal(h.i.loading, true); assert.equal(h.i.dataSource.length, 0)
    h.calls[1].resolve(success(kind, 1, [{ ...row(kind), id: 'new' }])); await newer
    assert.equal(h.i.dataSource[0].id, 'new'); assert.equal(h.i.ipagination.total, 1)
    const late = h.i.loadData(), fresh = h.i.searchQuery(); h.calls[3].resolve(success(kind, 1, [{ ...row(kind), id: 'fresh' }])); await fresh
    h.calls[2].resolve(success(kind, 90, [{ ...row(kind), id: 'late' }])); await late
    assert.equal(h.i.dataSource[0].id, 'fresh'); assert.equal(h.i.ipagination.total, 1)
  })
  test(`${kind}: an older network failure cannot put a current successful query in error`, async () => {
    const h = mount(kind), older = h.i.loadData(), newer = h.i.searchQuery()
    h.calls[1].resolve(success(kind)); await newer; h.calls[0].reject(new Error('late synthetic failure')); await older
    assert.equal(h.i.listError, ''); assert.equal(h.i.loading, false); assert.equal(h.i.dataSource[0].id, row(kind).id)
  })
  test(`${kind}: selection reflects current rows and is cleared for page changes`, async () => {
    const h = mount(kind); h.i.dataSource = [row(kind), { ...row(kind), id: 'second' }]; h.i.ipagination.total = 30
    h.i.selectRow(row(kind), true); assert.equal(h.i.selectionRows[0].id, row(kind).id); assert.equal(h.i.allSelected, false)
    h.i.toggleAll(true); assert.equal(h.i.selectedRowKeys.length, 2); assert.equal(h.i.allSelected, true)
    const done = h.i.changePage(2); assert.equal(h.i.selectedRowKeys.length, 0); assert.equal(h.i.selectionRows.length, 0)
    h.calls[0].resolve(success(kind, 30)); await done
  })
  test(`${kind}: repeated deletion dispatches once, list refresh keeps the delete lock`, async () => {
    const h = mount(kind), done = h.i.handleDelete(row(kind).id); h.i.handleDelete(row(kind).id); h.i.batchDel()
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].method, 'DELETE'); assert.equal(h.i.actionBusy, 'delete')
    h.calls[0].resolve({ success: true }); await flush(); assert.equal(h.calls[1].method, 'GET'); assert.equal(h.i.actionBusy, 'delete')
    h.i.handleDelete(row(kind).id); assert.equal(h.calls.length, 2)
    h.calls[1].resolve(success(kind, 0, [])); await done; assert.equal(h.i.actionBusy, ''); assert.equal(h.notices.filter(n => n.type === 'success').length, 1)
  })
  test(`${kind}: delete rejection retains rows, shows outcome warning and manual retry recovers`, async () => {
    const h = mount(kind); h.i.dataSource = [row(kind)]
    for (const response of ['network', { success: false, message: 'SQL secret' }, { success: 'true' }]) {
      const done = h.i.handleDelete(row(kind).id), call = h.calls.at(-1)
      if (response === 'network') call.reject(new Error('synthetic offline')); else call.resolve(response)
      await done; assert.equal(h.i.actionBusy, ''); assert.ok(h.i.actionError); assert.doesNotMatch(h.i.actionError, /SQL/); assert.equal(h.i.dataSource[0].id, row(kind).id); assert.equal(h.notices.length, 0)
    }
    const done = h.i.handleDelete(row(kind).id); h.calls.at(-1).resolve({ success: true }); await flush(); h.calls.at(-1).resolve(success(kind, 0, [])); await done
    assert.equal(h.i.actionError, ''); assert.equal(h.notices.length, 1)
  })
  test(`${kind}: deleting a last-page item falls back to the last valid page`, async () => {
    const h = mount(kind); h.i.ipagination.current = 3; h.i.ipagination.total = 21
    const done = h.i.handleDelete(row(kind).id); h.calls[0].resolve({ success: true }); await flush()
    assert.equal(h.calls[1].data.pageNo, 3); h.calls[1].resolve(success(kind, 20, [])); await flush()
    assert.equal(h.calls[2].data.pageNo, 2); assert.equal(h.i.loading, true); h.calls[2].resolve(success(kind, 20)); await done
    assert.equal(h.i.ipagination.current, 2); assert.equal(h.i.dataSource.length, 1); assert.equal(h.i.loading, false)
  })
  test(`${kind}: batch confirmation cannot stack, uses a snapshot, and can be cancelled`, async () => {
    const h = mount(kind); h.i.selectedRowKeys = ['first', 'second']; h.i.batchDel(); h.i.batchDel(); assert.equal(h.confirms.length, 1)
    h.i.selectedRowKeys.reverse(); const done = h.confirms[0].onOk(); h.confirms[0].onOk()
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].data.ids, 'first,second'); assert.equal(h.calls[0].url, h.i.url.deleteBatch)
    h.calls[0].resolve({ success: false }); await done
    h.i.batchDel(); h.confirms[1].onCancel(); h.i.batchDel(); assert.equal(h.confirms.length, 3); h.confirms[2].onCancel()
  })
  test(`${kind}: late list and delete results after disposal cannot change data or notify success`, async () => {
    const h = mount(kind), read = h.i.loadData(); h.destroy(); h.calls[0].resolve(success(kind)); await read; assert.equal(h.i.dataSource.length, 0)
    const d = mount(kind), deletion = d.i.handleDelete(row(kind).id); d.destroy(); d.calls[0].resolve({ success: true }); await deletion; assert.equal(d.calls.length, 1); assert.equal(d.notices.length, 0)
  })
  test(`${kind}: maintenance add and edit use inherited actual refs`, () => {
    const h = mount(kind); h.i.handleAdd(); h.i.handleEdit(row(kind)); assert.equal(h.entries[0], 'add'); assert.equal(h.entries[1].edit.id, row(kind).id)
    assert.equal(h.i.$refs.modalForm.title, '编辑'); assert.equal(h.i.$refs.modalForm.disableSubmit, false)
  })
  test(`${kind}: export uses applied filters and selected IDs, one download at a time`, async () => {
    const h = mount(kind); h.i.appliedQuery[field] = queryValue; h.i.queryParam[field] = 'synthetic-unsent'; h.i.selectedRowKeys = ['first', 'second']
    const done = h.i.handleExportXls('合成导出'); h.i.handleExportXls('合成导出')
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].method, 'DOWNLOAD'); assert.equal(h.calls[0].data[field], queryValue); assert.equal(h.calls[0].data.selections, 'first,second')
    h.calls[0].resolve(Uint8Array.from([208, 207, 17, 224, 161, 177, 26, 225])); await done
    assert.equal(h.i.actionBusy, ''); assert.equal(h.i.actionError, '')
  })
  test(`${kind}: export rejects an HTTP-200 JSON denial instead of downloading it`, async () => {
    const h = mount(kind), done = h.i.handleExportXls('合成导出'); h.calls[0].resolve(new Blob(['{"success":false,"message":"SQL secret"}'])); await done
    assert.equal(h.i.actionBusy, ''); assert.ok(h.i.actionError); assert.doesNotMatch(h.i.actionError, /SQL/)
  })
}

test('course: dictionaries and course-unit navigation keep their existing targets', () => {
  const h = mount('course'); h.i.handleEditDict('course_type'); h.i.handleEditDict('course_category'); h.i.handleUnit(row('course'))
  assert.equal(h.entries[0].dict, 'course_type'); assert.equal(h.entries[1].dict, 'course_category'); assert.equal(h.routes[0].path, '/course/courseUnit'); assert.equal(h.routes[0].query.courseId, row('course').id)
})

test('unit: route changes submit one fresh course filter and discard late previous results', async () => {
  const h = mount('unit', { courseId: 'synthetic-course-1' }); h.created(); h.i.queryParam.unitName = 'synthetic-unsent'; h.i.ipagination.current = 3; h.i.selectedRowKeys = ['old']
  const done = h.c.watch['$route.query.courseId'].call(h.i, 'synthetic-course-2')
  assert.equal(h.calls.length, 2); assert.equal(h.calls[1].data.courseId, 'synthetic-course-2'); assert.equal(h.calls[1].data.unitName, undefined); assert.equal(h.calls[1].data.pageNo, 1); assert.equal(h.i.selectedRowKeys.length, 0)
  h.calls[1].resolve(success('unit', 1, [{ ...row('unit'), id: 'new-course-unit', courseId: 'synthetic-course-2' }])); await done
  h.calls[0].resolve(success('unit')); await flush(); assert.equal(h.i.dataSource[0].id, 'new-course-unit')
  const reset = h.c.watch['$route.query.courseId'].call(h.i, undefined); assert.equal(h.calls[2].data.courseId, undefined); h.calls[2].resolve(success('unit', 0, [])); await reset
})

test('unit: route arrays cannot become a backend course filter', async () => {
  const h = mount('unit'); const done = h.c.watch['$route.query.courseId'].call(h.i, ['synthetic-course-1', 'synthetic-course-2'])
  assert.equal(h.calls[0].data.courseId, undefined); h.calls[0].resolve(success('unit', 0, [])); await done
})

test('unit: upload failure and business rejection retain data and expose safe recovery text', () => {
  const h = mount('unit'); h.i.dataSource = [row('unit')]
  for (const result of [{ status: 'error', error: 'SQL secret' }, { status: 'done', response: { success: false, message: 'SQL secret' } }, { status: 'done', response: { success: 'true' } }]) {
    h.i.handleImportExcel({ file: { status: 'uploading' } }); assert.equal(h.i.actionBusy, 'import')
    h.i.handleImportExcel({ file: result }); assert.equal(h.i.actionBusy, ''); assert.ok(h.i.actionError); assert.doesNotMatch(h.i.actionError, /SQL/); assert.equal(h.i.dataSource[0].id, row('unit').id); assert.equal(h.calls.length, 0); assert.equal(h.notices.length, 0)
  }
})

test('unit: import success refreshes applied scope, while code 201 keeps a safe detail report', async () => {
  const h = mount('unit'); h.i.appliedQuery.courseId = 'synthetic-course-1'; h.i.queryParam.courseId = 'synthetic-unsent'
  h.i.handleImportExcel({ file: { status: 'uploading' } }); const done = h.i.handleImportExcel({ file: { status: 'done', response: { success: true } } })
  assert.equal(h.calls[0].data.courseId, 'synthetic-course-1'); assert.equal(h.notices.length, 1); h.calls[0].resolve(success('unit')); await done
  h.i.handleImportExcel({ file: { status: 'uploading' } }); const report = h.i.handleImportExcel({ file: { status: 'done', response: { success: true, code: 201, result: { fileUrl: '/synthetic-import-details.txt', msg: 'SQL secret' } } } })
  assert.equal(h.i.importReport.url, 'http://synthetic.local/synthetic-import-details.txt'); assert.doesNotMatch(h.i.importReport.message, /SQL/); assert.equal(h.notices.length, 1)
  h.calls[1].resolve(success('unit')); await report
})

for (const kind of ['course', 'unit']) {
  test(`${kind}: quick page jump retains applied query and resets invalid page input`, async () => {
    const h = mount(kind); h.i.ipagination.total = 50; h.i.appliedQuery[kind === 'course' ? 'courseName' : 'courseId'] = 'synthetic-applied'; h.i.pageJump = '4'
    const done = h.i.jumpPage(); assert.equal(h.calls[0].data.pageNo, 4); assert.equal(h.calls[0].data[kind === 'course' ? 'courseName' : 'courseId'], 'synthetic-applied')
    h.calls[0].resolve(success(kind, 50)); await done
    for (const invalid of ['0', '-1', '1.5', '99', 'not-a-page']) { h.i.pageJump = invalid; h.i.jumpPage(); assert.equal(h.calls.length, 1); assert.equal(h.i.pageJump, '4') }
  })
  test(`${kind}: unsafe resources do not become links, and a broken cover falls back`, () => {
    const h = mount(kind)
    for (const value of ['', null, 'javascript:alert(1)', 'data:text/html,synthetic', 'https://user:secret@example.invalid/image']) assert.equal(h.i.resourceUrl(value), '')
    const record = { ...row(kind), [kind === 'course' ? 'courseCover' : 'unitCover']: '/synthetic-cover.png' }
    assert.equal(h.i.coverUrl(record), 'http://synthetic.local/synthetic-cover.png'); h.i.markCoverBroken(record); assert.equal(h.i.coverUrl(record), '')
  })
}

test('course: visible applied filter labels are snapshots and do not expose department IDs', async () => {
  const h = mount('course'); h.i.$refs.typeFilter = { getCurrentDictOptions: () => [{ value: '1', text: '合成性质 A' }] }; h.i.$refs.departFilter = { getDepartNames: () => '合成部门 A' }
  h.i.queryParam = { courseName: '  合成课程  ', courseType: '1', departId: 'synthetic-private-id' }; const done = h.i.searchQuery()
  assert.equal(h.calls[0].data.courseName, '合成课程'); assert.equal(h.i.appliedFilterSummary.join('；'), '课程名称：合成课程；课程性质：合成性质 A；授权部门：合成部门 A')
  h.i.queryParam.courseName = '尚未查询'; h.i.$refs.departFilter.getDepartNames = () => '合成部门 B'
  assert.doesNotMatch(h.i.appliedFilterSummary.join('；'), /尚未查询|合成部门 B|synthetic-private-id/)
  h.calls[0].resolve(success('course')); await done
})

test('unit: visible parent-course query summary uses a label snapshot', async () => {
  const h = mount('unit'); h.i.$refs.courseFilter = { getCurrentDictOptions: () => [{ value: 'synthetic-course-1', text: '合成课程 1' }] }; h.i.queryParam.courseId = 'synthetic-course-1'; h.i.queryParam.unitName = '  合成单元  '
  const done = h.i.searchQuery(); assert.equal(h.i.appliedFilterSummary.join('；'), '所属课程：合成课程 1；单元名称：合成单元')
  h.i.queryParam.courseId = 'synthetic-unsent'; assert.doesNotMatch(h.i.appliedFilterSummary.join('；'), /synthetic-/); h.calls[0].resolve(success('unit')); await done
})

for (const kind of ['course', 'unit']) {
  test(`${kind}: stale batch confirmation cannot delete after a new query or reset`, async () => {
    for (const action of ['searchQuery', 'searchReset']) {
      const h = mount(kind); h.i.selectedRowKeys = ['synthetic-first', 'synthetic-second']; h.i.batchDel(); const old = h.confirms[0]
      h.i.queryParam[kind === 'course' ? 'courseName' : 'courseId'] = 'synthetic-new-context'; const read = h.i[action](); h.calls[0].resolve(success(kind)); await read
      const deletion = old.onOk(); const deletes = h.calls.filter(call => call.method === 'DELETE')
      for (const call of deletes) call.resolve({ success: false }); await deletion
      assert.equal(deletes.length, 0, `${action} must invalidate a previous delete confirmation`)
    }
  })
}

test('unit: stale batch confirmation cannot delete after the parent route changes', async () => {
  const h = mount('unit', { courseId: 'synthetic-course-1' }); h.i.selectedRowKeys = ['synthetic-first', 'synthetic-second']; h.i.batchDel(); const old = h.confirms[0]
  const read = h.c.watch['$route.query.courseId'].call(h.i, 'synthetic-course-2'); h.calls[0].resolve(success('unit')); await read
  const deletion = old.onOk(); const deletes = h.calls.filter(call => call.method === 'DELETE')
  for (const call of deletes) call.resolve({ success: false }); await deletion
  assert.equal(deletes.length, 0, 'route courseId change must invalidate previous confirmation')
})

for (const kind of ['course', 'unit']) {
  test(`${kind}: changed selection invalidates confirmation and allows a fresh prompt`, async () => {
    for (const selection of [[], ['synthetic-other']]) {
      const h = mount(kind); h.i.selectedRowKeys = ['synthetic-first', 'synthetic-second']; h.i.batchDel(); h.i.selectedRowKeys = selection
      await h.confirms[0].onOk(); assert.equal(h.calls.length, 0); assert.ok(h.i.actionError); assert.equal(h.i.deletePromptOpen, false)
      h.i.selectedRowKeys = ['synthetic-fresh']; h.i.batchDel(); assert.equal(h.confirms.length, 2); h.confirms[1].onCancel()
    }
  })
  test(`${kind}: an old confirmation callback cannot unlock or submit a newer prompt`, async () => {
    const h = mount(kind); h.i.selectedRowKeys = ['synthetic-first', 'synthetic-second']; h.i.batchDel(); const old = h.confirms[0]
    old.onCancel(); h.i.batchDel(); assert.equal(h.i.deletePromptOpen, true)
    old.onCancel(); await old.onOk(); assert.equal(h.i.deletePromptOpen, true); assert.equal(h.calls.length, 0)
    h.confirms[1].onCancel(); assert.equal(h.i.deletePromptOpen, false)
  })
}
