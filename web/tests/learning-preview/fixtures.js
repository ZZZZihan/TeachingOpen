const scenario = new URLSearchParams(window.location.search).get('scenario') || 'normal'
let failed = false
const courses = [
  { id: 'preview-a', showType: 2, courseName: '从零认识人工智能', courseDesc: '<p>从身边的智能应用出发，认识数据、模型与算法。通过观察、讨论与动手实践，建立对人工智能的第一份理解。</p>', courseCategory_dictText: '人工智能基础' },
  { id: 'preview-b', showType: 1, courseName: '用代码创造你的第一个作品', courseDesc: '从图形化编程开始，把想法变成可以互动的故事。在探索中理解顺序、循环与条件。', courseCategory_dictText: '编程与创作', courseCover: '/missing-test-cover.png' }
]
const names = ['发现身边的人工智能', '让计算机学会观察', '数据如何帮助我们做判断', '从一个想法开始创作', '设计并分享你的作品']
export function getAction (url, params) {
  if (scenario === 'loading') return new Promise(() => {})
  if (scenario === 'error' && !failed) { failed = true; return Promise.reject(new Error('Controlled preview outage')) }
  if (url.includes('mineCourse')) return Promise.resolve({ success: true, result: scenario === 'empty' ? [] : courses })
  if (url.includes('queryById')) return Promise.resolve({ success: true, result: courses[0] })
  const records = names.map((name, index) => ({ id: 'unit-' + index, unitName: name, unitIntro: ['观察常见的智能应用，讨论它们如何感知世界并回应我们的需求。', '尝试一个简单的识别案例，理解计算机与人类观察方式的异同。', '收集和整理样本，观察不同数据如何影响判断结果。', '梳理创作思路，用编程表达你的想法。', '完善作品并分享学习过程中的发现。'][index], courseVideo: index < 3 ? 'preview-video' : '', mediaContent: index % 2 ? 'preview-content' : '', courseCase: index === 1 ? 'preview-case' : '', courseWork_url: index > 2 ? 'preview-task' : '', coursePpt: index < 2 ? 'preview-slides' : '' }))
  return Promise.resolve({ success: true, result: { records: scenario === 'empty' ? [] : records, total: scenario === 'empty' ? 0 : records.length } })
}
export const getFileAccessHttpUrl = value => value
