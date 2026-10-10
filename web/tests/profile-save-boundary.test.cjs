const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const pick = require('lodash.pick')

test('个人设置实际保存方法只发送允许字段，不重发完整登录资料', async () => {
  const writes = []
  const context = { AvatarModal: {}, JUpload: {}, moment: () => {}, pick,
    putAction: (url, body) => { writes.push({ url, body }); return Promise.resolve({ success: true }) },
    console: { log () {} } }
  vm.runInNewContext(readFileSync(resolve(__dirname, '../src/views/account/settings/BaseSetting.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const fullAccount = { id: 'self', username: 'account', password: 'never-send', salt: 'never-send',
    phone: '13912345678', departIds: 'school', status: 1, realname: '旧名称' }
  const instance = { userInfo: fullAccount, form: { getFieldsValue: () => ({
    realname: '新名称', avatar: 'safe-avatar', sex: 1, email: 'test@example.test', birthday: null,
    phone: '13900000000', password: 'unexpected', status: 2
  }) }, url: { editUser: '/teaching/user/edit' }, $message: { success () {}, warning () {} }, $emit () {} }
  context.component.methods.handleSubmit.call(instance)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(writes[0].url, '/teaching/user/edit')
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0].body)), {
    id: 'self', realname: '新名称', avatar: 'safe-avatar', sex: 1, email: 'test@example.test', birthday: null
  })
  assert.equal(fullAccount.realname, '旧名称')
  assert.equal(instance.confirmLoading, false)
})
