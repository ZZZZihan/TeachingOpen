<template>
  <section class="registered-users" aria-labelledby="registered-users-title">
    <div class="directory-overview">
      <div class="directory-summary">
        <h2 id="registered-users-title">已注册师生</h2>
        <div v-if="total !== null && !error" class="directory-total"><strong>{{ total.toLocaleString('zh-CN') }}</strong><span>人</span></div>
        <p v-else class="directory-total-status">{{ error ? '人数暂时无法获取' : '正在获取人数…' }}</p>
      </div>
      <aside v-if="$slots['registration-entry']" class="directory-entry"><slot name="registration-entry" /></aside>
    </div>
    <div class="directory-list" :aria-busy="loading ? 'true' : 'false'">
      <div class="directory-list-heading">
        <h3>最新加入</h3>
        <button type="button" class="refresh-button" :disabled="loading" @click="loadPage(1)">{{ loading ? '更新中…' : '刷新名单' }}</button>
      </div>
      <p v-if="error" class="directory-status" role="alert">暂时无法获取注册名单。<button type="button" @click="loadPage(pageNo)">重新加载</button></p>
      <p v-else-if="loading" class="directory-status" role="status">正在获取注册名单…</p>
      <template v-else>
        <p v-if="total === 0" class="directory-status">暂时还没有注册用户。</p>
        <table v-else class="directory-table">
          <caption class="sr-only">注册用户名单</caption>
          <thead><tr><th scope="col">姓名</th><th scope="col">学校</th><th scope="col">身份</th></tr></thead>
          <tbody><tr v-for="(user, index) in records" :key="index"><td class="directory-name">{{ user.name }}</td><td class="directory-school">{{ user.school }}</td><td><span class="identity-tag" :class="{ teacher: user.identity === '教师' }">{{ user.identity }}</span></td></tr></tbody>
        </table>
        <nav v-if="total > 10" class="directory-pagination" aria-label="注册名单分页"><button type="button" :disabled="pageNo <= 1" @click="loadPage(pageNo - 1)">上一页</button><span>第 {{ pageNo }} / {{ Math.ceil(total / 10) }} 页</span><button type="button" :disabled="pageNo * 10 >= total" @click="loadPage(pageNo + 1)">下一页</button></nav>
      </template>
    </div>
  </section>
</template>
<script>
import { getAction } from '@/api/manage'
export default {
    name: 'PublicUserDirectory',
    data () { return { total: null, records: [], pageNo: 1, loading: false, error: false, requestId: 0, destroyed: false } },
    mounted () { this.loadPage(1) },
    beforeDestroy () { this.destroyed = true; this.requestId++ },
    methods: {
        async loadPage (page) {
            const requestId = ++this.requestId
            this.loading = true
            this.error = false
            try {
                const response = await getAction('/teaching/user/publicDirectory', { pageNo: page })
                if (this.destroyed || requestId !== this.requestId) return
                const result = response && response.result
                if (!response.success || !result || !Number.isSafeInteger(result.total) || result.total < 0 || result.pageSize !== 10 || !Number.isSafeInteger(result.pageNo) || result.pageNo < 1 || result.pageNo > Math.max(1, Math.ceil(result.total / 10)) || !Array.isArray(result.records) || result.records.length !== Math.min(10, Math.max(0, result.total - (result.pageNo - 1) * 10)) || result.records.some(user => !user || ['name', 'school', 'identity'].some(field => typeof user[field] !== 'string'))) throw new Error('Invalid public directory')
                this.total = result.total
                this.pageNo = result.pageNo
                this.records = result.records.map(user => ({ name: user.name, school: user.school, identity: user.identity }))
            } catch (e) {
                if (this.destroyed || requestId !== this.requestId) return
                this.error = true
            } finally {
                if (!this.destroyed && requestId === this.requestId) this.loading = false
            }
        }
    }
}
</script>
<style scoped lang="less">
.registered-users { margin-top: 38px; border: 1px solid #d5e5f5; border-radius: 8px; overflow: hidden; color: #29222b; background: #fff; }
.directory-overview { display: flex; align-items: center; justify-content: space-between; gap: 32px; padding: 30px 36px; background: #eef6ff; }
.directory-summary { flex: 1; min-width: 0; }
h2 { margin: 0 0 10px; font-size: 17px; line-height: 1.5; font-weight: 500; color: #534757; }
.directory-total { display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px; color: #146fc2; }
.directory-total strong { min-width: 0; max-width: 100%; overflow-wrap: anywhere; font-size: 64px; line-height: 1.15; font-weight: 600; letter-spacing: -1px; font-variant-numeric: tabular-nums; }
.directory-total span { font-size: 18px; color: #77637a; }
.directory-total-status { margin: 18px 0; color: #79717a; font-size: 16px; }
.directory-entry { flex: 0 1 360px; min-width: 0; }
.directory-list { min-width: 0; padding: 24px 36px 28px; }
.directory-list-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px; }
h3 { margin: 0; font-size: 17px; line-height: 1.5; font-weight: 500; color: #423547; }
button { background: transparent; border: 1px solid #bccfe2; border-radius: 4px; color: #146fc2; padding: 7px 12px; cursor: pointer; white-space: nowrap; }
.refresh-button { border-color: transparent; color: #726777; font-size: 12px; padding: 5px 0 5px 8px; }
.refresh-button:hover:not(:disabled) { color: #146fc2; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible { outline: 2px solid #146fc2; outline-offset: 3px; }
.directory-status { padding: 24px 0; color: #79717a; line-height: 1.8; }
.directory-status button { margin-left: 12px; }
.directory-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 14px; line-height: 1.7; }
th { background: #f4f8fd; font-size: 12px; font-weight: 400; color: #726777; }
th, td { text-align: left; padding: 14px 16px; border-bottom: 1px solid #d5e5f5; overflow-wrap: anywhere; }
th:first-child { width: 20%; } th:last-child { width: 16%; }
.directory-name { font-weight: 500; color: #49364e; }
.directory-school { color: #625967; }
.identity-tag { display: inline-block; padding: 2px 9px; border-radius: 4px; font-size: 12px; color: #6d6570; background: #f3f2f4; }
.identity-tag.teacher { color: #146fc2; background: #eef6ff; }
.directory-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 16px; margin-top: 22px; font-size: 12px; color: #79717a; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 700px) {
  .directory-overview { flex-direction: column; align-items: stretch; gap: 24px; padding: 26px 22px; }
  .directory-entry { flex: auto; }
  .directory-list { padding: 22px 18px 24px; }
  .directory-total strong { font-size: 56px; }
  th, td { padding: 13px 8px; }
  th:first-child { width: 22%; } th:last-child { width: 22%; }
  .identity-tag { padding: 2px 7px; }
  .directory-pagination { justify-content: center; gap: 12px; }
}
</style>
