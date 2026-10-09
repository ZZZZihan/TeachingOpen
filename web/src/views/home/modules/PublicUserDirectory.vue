<template>
  <section class="registered-users" aria-labelledby="registered-users-title">
    <div class="directory-heading">
      <div><h2 id="registered-users-title">已注册用户 <span v-if="total !== null && !error">{{ total }} 人</span></h2></div>
      <button type="button" class="refresh-button" :disabled="loading" @click="loadPage(1)">{{ loading ? '更新中…' : '刷新名单' }}</button>
    </div>
    <div class="directory-body" :class="{ 'with-entry': Boolean($slots['registration-entry']) }">
      <div class="directory-list" :aria-busy="loading ? 'true' : 'false'">
        <p v-if="error" class="directory-status" role="alert">暂时无法获取注册名单。<button type="button" @click="loadPage(pageNo)">重新加载</button></p>
        <p v-else-if="loading" class="directory-status" role="status">正在获取注册名单…</p>
        <template v-else>
          <p v-if="total === 0" class="directory-status">暂时还没有注册用户。</p>
          <table v-else class="directory-table"><caption class="sr-only">注册用户名单</caption><thead><tr><th scope="col">姓名</th><th scope="col">学校</th><th scope="col">身份</th></tr></thead><tbody><tr v-for="(user, index) in records" :key="index"><td>{{ user.name }}</td><td>{{ user.school }}</td><td>{{ user.identity }}</td></tr></tbody></table>
          <nav v-if="total > 10" class="directory-pagination" aria-label="注册名单分页"><button type="button" :disabled="pageNo <= 1" @click="loadPage(pageNo - 1)">上一页</button><span>第 {{ pageNo }} / {{ Math.ceil(total / 10) }} 页</span><button type="button" :disabled="pageNo * 10 >= total" @click="loadPage(pageNo + 1)">下一页</button></nav>
        </template>
      </div>
      <aside v-if="$slots['registration-entry']" class="directory-entry"><slot name="registration-entry" /></aside>
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
.registered-users { margin-top: 38px; padding-top: 26px; border-top: 1px solid #e4dce3; color: #29222b; }
.directory-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 20px; }
h2 { margin: 0 0 10px; font-size: 22px; font-weight: 500; color: #29222b; }
h2 span { margin-left: 14px; color: #74256a; font-size: 18px; }
button { background: transparent; border: 1px solid #d5c8d2; border-radius: 2px; color: #74256a; padding: 7px 12px; cursor: pointer; white-space: nowrap; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
.directory-body.with-entry { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 320px); gap: 32px; }
.directory-list, .directory-entry { min-width: 0; }
.directory-status { padding: 24px 0; color: #79717a; }
.directory-status button { margin-left: 12px; }
.directory-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 14px; }
th { background: #f5f0f4; font-weight: 500; color: #534757; }
th, td { text-align: left; padding: 13px 16px; border-bottom: 1px solid #eae3e8; overflow-wrap: anywhere; }
th:first-child { width: 24%; } th:last-child { width: 20%; }
.directory-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 16px; margin-top: 20px; font-size: 12px; color: #79717a; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 900px) { .directory-body.with-entry { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .directory-heading { flex-wrap: wrap; gap: 12px; } th, td { padding: 12px 8px; } .directory-pagination { justify-content: center; gap: 12px; } }
</style>
