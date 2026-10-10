const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const compiler = require('vue-template-compiler')

function component (file, globals) {
  const parsed = compiler.parseComponent(readFileSync(resolve(__dirname, '../src', file), 'utf8'))
  assert.deepEqual(compiler.compile(parsed.template.content).errors, [])
  const context = { ...globals, console: { log () {} } }
  vm.runInNewContext(parsed.script.content.replace(/^\s*import .*$/gm, '').replace('export default', 'this.component ='), context)
  return context.component
}

function tree (dict = 'category_tree', value = '') {
  const requests = []
  const definition = component('components/jeecg/JTreeSelect.vue', {
    getAction: async (url, params) => {
      requests.push({ url, params: JSON.parse(JSON.stringify(params)) })
      return { success: true, result: url.includes('loadDictItem') ? ['分类'] : [{ key: 'node-1', title: '分类', leaf: false }] }
    }
  })
  const instance = { ...definition.data(), dict, value, pidField: 'pid', pidValue: '0', hasChildField: '', condition: '', multiple: false, loadTriggleChange: false }
  for (const [name, method] of Object.entries(definition.methods)) instance[name] = method.bind(instance)
  instance.initDictInfo()
  return { instance, requests }
}

test('命名分类树首次加载和展开只提交固定用途与父节点', async () => {
  const { instance, requests } = tree()
  instance.loadRoot()
  await Promise.resolve()
  await instance.asyncLoadTreeData({ $vnode: { key: 'node-1' } })
  assert.deepEqual(requests, [
    { url: '/sys/dict/loadTreeData', params: { dictCode: 'category_tree', pid: '0' } },
    { url: '/sys/dict/loadTreeData', params: { dictCode: 'category_tree', pid: 'node-1' } }
  ])
  assert.equal(instance.treeData[0].title, '分类')
  assert.equal(instance.treeData[0].children[0].key, 'node-1')
})

test('已选分类使用命名用途回显文本', async () => {
  const { instance, requests } = tree('category_tree', 'node-1')
  instance.loadItemByCode()
  await Promise.resolve()
  assert.deepEqual(requests, [{ url: '/sys/dict/loadDictItem/category_tree', params: { key: 'node-1' } }])
  assert.equal(instance.treeValue[0].value, 'node-1')
  assert.equal(instance.treeValue[0].label, '分类')
})

test('旧固定树配置仍沿用既有参数形式，由服务端精确映射', () => {
  const { instance } = tree('sys_category,name,id')
  assert.deepEqual(JSON.parse(JSON.stringify(instance.treeRequest('0'))), {
    pid: '0', tableName: 'sys_category', text: 'name', code: 'id', pidField: 'pid', hasChildField: '', condition: ''
  })
})

test('课程和角色选项使用真实字典组件加载命名用途并保留选中值', async () => {
  for (const purpose of ['course_options', 'registration_roles']) {
    const requests = []
    const definition = component('components/dict/JDictSelectTag.vue', {
      getDictItemsFromCache: () => null,
      ajaxGetDictItems: async code => {
        requests.push(code)
        return { success: true, result: [{ value: 'choice-1', text: '正常选项' }] }
      }
    })
    const instance = { ...definition.data(), dictCode: purpose, defaultShowAll: purpose === 'course_options', defaultDictOptions: [], value: 'choice-1' }
    definition.methods.initDictData.call(instance)
    await Promise.resolve()
    assert.deepEqual(requests, [purpose])
    assert.equal(instance.dictOptions.at(-1).text, '正常选项')
    assert.equal(definition.computed.getValueSting.call(instance), 'choice-1')
    if (purpose === 'course_options') assert.equal(instance.dictOptions[0].value, '')
  }
})

test('迁移后的管理与示例页面模板均能编译', () => {
  for (const file of ['views/teaching/TeachingCourseUnitList.vue', 'views/system/SysConfig.vue', 'views/system/modules/SysCategoryModal.vue', 'views/jeecg/SelectDemo.vue', 'views/jeecg/JeecgDemoList.vue']) {
    const parsed = compiler.parseComponent(readFileSync(resolve(__dirname, '../src', file), 'utf8'))
    assert.deepEqual(compiler.compile(parsed.template.content).errors, [], file)
  }
})
