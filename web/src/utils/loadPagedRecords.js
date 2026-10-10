/** Load a complete list without requesting an unbounded database page. */
export async function loadPagedRecords(getPage, params = {}) {
  const records = []
  let pageNo = 1
  let total
  while (true) {
    const response = await getPage({ ...params, pageNo, pageSize: 100 })
    if (!response || response.success !== true) {
      throw new Error((response && response.message) || '列表加载失败')
    }
    const page = response.result
    if (!page || !Array.isArray(page.records) || !Number.isSafeInteger(page.total) || page.total < 0 ||
      (total !== undefined && page.total !== total) || page.records.length !== Math.min(100, page.total - records.length)) {
      const error = new Error('列表数据不完整，请重试')
      error.listKind = 'data'
      throw error
    }
    total = page.total
    records.push(...page.records)
    if (records.length === total) return records
    pageNo++
  }
}
