<template>
  <main class="teacher-workbench">
    <header class="workbench-heading"><div><p class="workbench-eyebrow">TeachingOpen · 教学管理</p><h1>作业与反馈</h1><p>查看学生的思考与创作，让每一次提交都有回应。</p></div><button class="work-button secondary" :disabled="loading" @click="loadData()"><a-icon type="reload" /> 刷新列表</button></header>
    <nav class="work-status-tabs" aria-label="作业状态筛选"><button v-for="status in statuses" :key="status.value" :class="{ active: applied.workStatus === status.value }" :aria-current="applied.workStatus === status.value ? 'page' : null" @click="chooseStatus(status.value)">{{ status.label }}</button></nav>
    <form class="work-filters" @submit.prevent="searchQuery">
      <div class="primary-filters">
        <label>作品名称<input v-model="queryParam.workName" type="search" placeholder="查找一份作品"></label>
        <label>学生姓名<input v-model="queryParam.realname" type="search" placeholder="输入姓名"></label>
        <label>创作来源<select v-model="queryParam.workScene"><option value="">全部来源</option><option value="course">课程作业</option><option value="additional">班级作业</option><option value="create">自由创作</option><option value="exam">考试作品</option></select></label>
        <div class="filter-actions"><button type="submit" class="work-button">查询</button><button type="button" class="work-link" @click="searchReset">重置</button><button type="button" class="work-link" :aria-expanded="showFilters" aria-controls="work-more-filters" @click="showFilters = !showFilters">{{ showFilters ? '收起筛选' : '更多筛选' }} <a-icon :type="showFilters ? 'up' : 'down'" /></button></div>
      </div>
      <div v-if="showFilters" id="work-more-filters" class="more-filters">
        <label>学生账号<input v-model="queryParam.username" placeholder="输入账号"></label>
        <label>作品类型<j-dict-select-tag v-model="queryParam.workType" dict-code="work_type" placeholder="全部类型" /></label>
        <label>我的标签<select v-model="queryParam.workTag"><option value="">全部标签</option><option v-for="tag in workTags" :key="tag" :value="tag">{{ tag }}</option></select></label>
        <label v-for="field in advancedFields" :key="field.key">{{ field.label }}<input v-model="queryParam[field.key]" :placeholder="'输入' + field.label"></label>
      </div>
      <p v-if="tagsError" class="work-muted">标签暂时无法读取。<button class="work-link" type="button" @click="getWorkTags">重试标签</button></p>
    </form>
    <section class="work-results" aria-label="作业列表" :aria-busy="loading">
      <div class="results-toolbar"><div><h2>{{ currentStatusLabel }}</h2><span v-if="!loading && !listError">{{ total }} 份作品</span></div><label class="sort-control">排序<select v-model="sort" @change="loadData(1)"><option value="createTime:desc">最近提交</option><option value="createTime:asc">最早提交</option><option value="viewNum:desc">查看最多</option><option value="starNum:desc">点赞最多</option><option value="workType:asc">作品类型</option><option value="workScene:asc">创作来源</option><option value="workStatus:asc">作品状态</option></select></label></div>
      <div v-if="loading" class="work-state" role="status"><a-spin /><h3>正在读取学生作品…</h3><p>列表准备好后即可开始批改。</p></div>
      <div v-else-if="listError" class="work-state error" role="alert"><a-icon type="exclamation-circle" /><h3>作业列表暂时无法读取</h3><p>{{ listError }}</p><button class="work-button" @click="loadData()">重新加载</button></div>
      <div v-else-if="!dataSource.length" class="work-state"><a-icon type="inbox" /><h3>{{ applied.workStatus === '1' ? '当前没有待批改的作业' : '没有找到符合条件的作品' }}</h3><p>可以调整筛选条件，或查看其他状态的作品。</p><button class="work-button secondary" @click="searchReset">查看全部作品</button></div>
      <template v-else>
        <div class="selection-toolbar"><label><input type="checkbox" :checked="allSelected" @change="toggleAll($event.target.checked)"> 选择本页</label><span v-if="selectedRowKeys.length">已选 {{ selectedRowKeys.length }} 份 <button class="work-link" @click="selectedRowKeys = []">清空</button></span><div><button class="work-link" :disabled="Boolean(actionBusy)" @click="exportWorks">{{ actionBusy === 'export' ? '正在导出…' : selectedRowKeys.length ? '导出选中' : '导出列表' }}</button><button v-if="selectedRowKeys.length" class="work-link danger" :disabled="Boolean(actionBusy)" @click="deleteWorks(selectedRowKeys)">删除选中</button></div></div>
        <p v-if="actionError" class="work-error" role="alert">{{ actionError }}</p>
        <article v-for="row in dataSource" :key="row.id" class="work-row">
          <label class="row-select"><input v-model="selectedRowKeys" type="checkbox" :value="row.id" :aria-label="'选择作品：' + row.workName"></label>
          <div class="work-cover"><img v-if="coverUrl(row)" :src="coverUrl(row)" alt="" loading="lazy" @error="$set(brokenCovers, row.id, true)"><a-icon v-else :type="String(row.workType) === '0' ? 'file-text' : 'code'" /></div>
          <div class="work-summary"><div class="work-meta"><span :class="['work-badge', 'state-' + row.workStatus]">{{ statusLabel(row.workStatus) }}</span><span>{{ row.workType_dictText || '作品' }}</span><span>{{ sceneLabel(row.workScene) }}</span></div><h3><button @click="handlePreview(row)">{{ row.workName || '未命名作品' }}</button></h3><p class="work-student">{{ row.realname || row.username || '学生未标注' }}<span v-if="row.realname && row.username"> · {{ row.username }}</span><span v-if="row.departId_dictText"> · {{ row.departId_dictText }}</span></p><p class="work-time">{{ row.createTime || '提交时间未记录' }}<span v-if="row.courseId_dictText || row.courseName"> · {{ row.courseId_dictText || row.courseName }}</span><span v-if="row.additionalId_dictText"> · {{ row.additionalId_dictText }}</span></p><details class="work-details"><summary>作品详情<span v-if="row.workTag"> · {{ row.workTag }}</span></summary><p>查看 {{ row.viewNum == null ? '—' : row.viewNum }} 次 · 点赞 {{ row.starNum == null ? '—' : row.starNum }} 次</p><p v-if="row.score != null">当前评分 {{ row.score }} / 5</p><p v-if="row.teacherComment">{{ row.teacherComment }}</p><button class="work-link" :disabled="Boolean(actionBusy)" @click="openTag(row)">{{ row.workTag ? '编辑标签' : '添加标签' }}</button></details></div>
          <div class="work-row-actions"><button class="work-button" @click="handleEdit(row)">{{ String(row.workStatus) === '1' ? '开始批改' : '查看批改' }} <a-icon type="arrow-right" /></button><button class="work-link" @click="handlePreview(row)">预览作品</button><a-dropdown :trigger="['click']"><button class="work-link" :disabled="Boolean(actionBusy)" :aria-label="row.workName + '的更多操作'">更多 <a-icon type="down" /></button><a-menu slot="overlay"><a-menu-item @click="handleView(row)">在新窗口打开</a-menu-item><a-menu-item @click="download(row.workFileKey_url)">下载作品文件</a-menu-item><a-menu-item v-if="['1', '2'].includes(String(row.workType))" @click="shareRecord = row">分享二维码</a-menu-item><a-menu-item @click="handleSend(row)">克隆至其他账号</a-menu-item><a-menu-item @click="openTag(row)">管理作品标签</a-menu-item><a-menu-item @click="deleteWorks([row.id])">删除作品</a-menu-item></a-menu></a-dropdown></div>
        </article>
        <nav class="work-pagination" aria-label="作业分页"><p>第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 份</p><div><label>每页 <select v-model.number="pageSize" @change="loadData(1)"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select> 份</label><button class="work-button secondary" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button><button class="work-button secondary" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button></div></nav>
      </template>
    </section>
    <teaching-work-modal ref="modalForm" @ok="loadData()" @preview="handlePreview" />
    <teaching-work-preview-modal ref="previewModal" />
    <select-user-modal ref="selectUserModal" @selectFinished="selectStudentOK" />
    <a-modal
      :visible="Boolean(tagRecord)"
      title="作品标签"
      :width="460"
      :confirm-loading="actionBusy === 'tag'"
      :mask-closable="false"
      @ok="saveTag"
      @cancel="closeTag">
      <label class="tag-label" for="teacher-work-tag">{{ tagRecord ? tagRecord.workName : '' }}</label><a-input id="teacher-work-tag" v-model="tagValue" :disabled="Boolean(actionBusy)" placeholder="输入标签，留空可移除本作品标签" />
      <p class="work-muted">标签仅用于你自己的作品整理。</p><div class="tag-choices"><span v-for="tag in workTags" :key="tag"><button :disabled="Boolean(actionBusy)" @click="tagValue = tag">{{ tag }}</button><button :disabled="Boolean(actionBusy)" :aria-label="'删除快捷标签 ' + tag" @click="deleteTag(tag)">×</button></span></div><p v-if="tagError" class="work-error" role="alert">{{ tagError }}</p>
    </a-modal>
    <a-modal :visible="Boolean(shareRecord)" title="作品分享" :footer="null" :width="340" @cancel="shareRecord = null"><p>访问者仍需满足作品的查看权限。</p><qr-code v-if="shareRecord" :value="shareUrl(shareRecord)" :size="240" /></a-modal>
  </main>
</template>
<script>
import { getAction, postAction, deleteAction, downFile } from '@/api/manage'
import TeachingWorkModal from './modules/TeachingWorkModal.vue'
import TeachingWorkPreviewModal from './modules/TeachingWorkPreviewModal.vue'
import SelectUserModal from '@/views/system/modules/SelectUserModal.vue'
import JDictSelectTag from '@/components/dict/JDictSelectTag.vue'
import QrCode from '@/components/tools/QrCode.vue'
const root = '/teaching/teachingWork/'
const emptyQuery = () => ({ workName: '', realname: '', username: '', workScene: '', workType: '', workTag: '', userId: '', courseId: '', departId: '', additionalId: '', workStatus: '1' })
export default {
    name: 'TeachingWorkList',
    components: { TeachingWorkModal, TeachingWorkPreviewModal, SelectUserModal, JDictSelectTag, QrCode },
    data () {
        return { queryParam: emptyQuery(),
            applied: emptyQuery(),
            showFilters: false,
            dataSource: [],
            total: 0,
            page: 1,
            pageSize: 10,
            sort: 'createTime:desc',
            loading: false,
            listError: '',
            requestId: 0,
            tagsRequestId: 0,
            selectedRowKeys: [],
            brokenCovers: {},
            workTags: [],
            tagsError: false,
            actionBusy: '',
            actionError: '',
            tagRecord: null,
            tagValue: '',
            tagError: '',
            sendWorkId: '',
            shareRecord: null,
            statuses: [{ value: '1', label: '待批改' }, { value: '2', label: '已批改' }, { value: '', label: '全部作品' }, { value: '0', label: '草稿' }, { value: '3', label: '公开展示' }, { value: '4', label: '精选' }],
            advancedFields: [{ key: 'departId', label: '班级 ID' }, { key: 'courseId', label: '课程 ID' }, { key: 'additionalId', label: '班级作业 ID' }, { key: 'userId', label: '学生 ID' }]
        }
    },
    computed: {
        currentStatusLabel () { return this.statuses.find(status => status.value === this.applied.workStatus).label },
        totalPages () { return Math.max(1, Math.ceil(this.total / this.pageSize)) },
        allSelected () { return this.dataSource.length > 0 && this.dataSource.every(row => this.selectedRowKeys.includes(row.id)) }
    },
    created () {
        const query = this.$route.query || {}
        Object.keys(this.queryParam).forEach(key => { if (typeof query[key] === 'string') this.queryParam[key] = query[key] })
        if (!this.statuses.some(status => status.value === this.queryParam.workStatus)) this.queryParam.workStatus = '1'
        this.searchQuery(); this.getWorkTags()
    },
    beforeDestroy () { this.requestId++; this.tagsRequestId++ },
    methods: {
        statusLabel (value) { const state = this.statuses.find(status => status.value !== '' && status.value === String(value)); return state ? state.label : '状态未标注' },
        sceneLabel (value) { return { course: '课程作业', additional: '班级作业', create: '自由创作', exam: '考试作品' }[value] || '来源未标注' },
        safeUrl (value) { try { if (!value || !String(value).trim()) return ''; const url = new URL(value, window.location.origin); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '' } catch (error) { return '' } },
        coverUrl (row) { return this.brokenCovers[row.id] ? '' : this.safeUrl(row.coverFileKey_url) },
        shareUrl (row) { return window.location.origin + '/work-detail?id=' + encodeURIComponent(row.id) },
        searchQuery () { this.applied = { ...this.queryParam }; return this.loadData(1) },
        searchReset () { this.queryParam = { ...emptyQuery(), workStatus: '' }; return this.searchQuery() },
        chooseStatus (value) { if (this.applied.workStatus === value) return; this.queryParam.workStatus = value; this.applied = { ...this.applied, workStatus: value }; return this.loadData(1) },
        async loadData (first) {
            if (first === 1) this.page = 1
            const sequence = ++this.requestId; this.loading = true; this.listError = ''; this.selectedRowKeys = []; this.actionError = ''
            const [column, order] = this.sort.split(':'); const params = { ...this.applied, column, order, pageNo: this.page, pageSize: this.pageSize }
            Object.keys(params).forEach(key => { if (params[key] === '' || params[key] === null || params[key] === undefined) delete params[key] })
            try {
                const response = await getAction(root + 'list', params)
                if (sequence !== this.requestId) return
                const result = response.result
                if (!response.success || !result || !Array.isArray(result.records) || result.records.some(row => !row || !row.id) || !Number.isFinite(Number(result.total)) || Number(result.total) < 0) throw new Error('列表响应不完整')
                this.dataSource = result.records; this.total = Number(result.total)
                if (this.page > this.totalPages) { this.page = this.totalPages; return this.loadData() }
            } catch (error) {
                if (sequence === this.requestId) { this.dataSource = []; this.total = 0; this.listError = '请检查网络或当前账号的访问权限后重试。筛选条件已保留。' }
            } finally { if (sequence === this.requestId) this.loading = false }
        },
        changePage (page) { if (page < 1 || page > this.totalPages || page === this.page || this.loading) return; this.page = page; return this.loadData() },
        toggleAll (checked) { this.selectedRowKeys = checked ? this.dataSource.map(row => row.id) : [] },
        async getWorkTags () {
            const sequence = ++this.tagsRequestId
            try { const result = await getAction(root + 'getWorkTags'); if (sequence !== this.tagsRequestId) return; if (!result.success || (result.result !== null && !Array.isArray(result.result))) throw new Error('标签读取失败'); this.workTags = (result.result || []).filter(tag => typeof tag === 'string'); this.tagsError = false } catch (error) { if (sequence === this.tagsRequestId) this.tagsError = true }
        },
        handleEdit (record) { this.$refs.modalForm.edit(record) },
        handlePreview (record) { this.$refs.previewModal.previewCode(record) },
        openUrl (value) { const url = this.safeUrl(value); if (!url) { this.actionError = '作品文件暂不可用，请联系管理员核对资源。'; return } window.open(url, '_blank', 'noopener,noreferrer') },
        download (url) { this.openUrl(url) },
        handleView (record) {
            const paths = { 1: '/scratch3/index.html', 2: '/scratch3/index.html', 3: '/scratchjr/editor.html', 4: '/python/index.html', 10: '/blockly/index.html' }
            const path = paths[record.workType]
            if (!path) return this.openUrl(record.workFileKey_url)
            const params = new URLSearchParams({ workId: record.id })
            if (String(record.workType) === '3') { params.set('queryEncoding', 'uri'); params.set('mode', 'look'); params.set('workFile', record.workFileKey_url || '') }
            if (String(record.workType) === '10') params.set('lang', 'zh-hans')
            this.openUrl(path + '?' + params.toString())
        },
        openTag (row) { if (this.actionBusy) return; this.tagRecord = row; this.tagValue = row.workTag || ''; this.tagError = '' },
        closeTag () { if (!this.actionBusy) this.tagRecord = null },
        async saveTag () {
            if (this.actionBusy || !this.tagRecord) return
            this.actionBusy = 'tag'; this.tagError = ''
            try { const response = await getAction(root + 'setWorkTag', { workId: this.tagRecord.id, workTag: this.tagValue.trim() }); if (!response.success) throw new Error('标签保存失败'); this.tagRecord = null; this.getWorkTags(); await this.loadData() } catch (error) { this.tagError = '标签未能保存，填写内容已保留，请重试。' } finally { this.actionBusy = '' }
        },
        deleteTag (tag) {
            if (this.actionBusy) return
            this.$confirm({ title: '删除快捷标签“' + tag + '”？',
                content: '将从你的快捷选择中移除，已有作品上的标签仍保留。',
                onOk: async () => {
                    if (this.actionBusy) return
                    this.actionBusy = 'tag'; this.tagError = ''
                    try { const response = await deleteAction(root + 'delWorkTag', { tag, force: true }); if (!response.success) throw new Error('标签删除失败'); await this.getWorkTags() } catch (error) { this.tagError = '快捷标签未能删除，请重试。' } finally { this.actionBusy = '' }
                } })
        },
        handleSend (row) { if (this.actionBusy) return; this.sendWorkId = row.id; this.$refs.selectUserModal.visible = true },
        async selectStudentOK (ids) {
            if (this.actionBusy || !this.sendWorkId || !Array.isArray(ids) || !ids.length) return
            this.actionBusy = 'send'; this.actionError = ''
            try { const response = await postAction(root + 'sendWork', { sendWorkId: this.sendWorkId, userIdList: ids }); if (!response.success) throw new Error('发送失败'); this.$message.success('作品已克隆至所选账号') } catch (error) { this.actionError = '未能确认克隆成功，请先核对目标账号中的作品，避免重复发送。' } finally { this.actionBusy = '' }
        },
        deleteWorks (ids) {
            if (this.actionBusy || !ids.length) return
            const selected = [...ids]
            this.$confirm({ title: '删除这 ' + selected.length + ' 份作品？',
                content: '删除后将无法从当前列表访问，请确认已保留需要的作品。',
                okText: '删除作品',
                okType: 'danger',
                cancelText: '保留作品',
                onOk: async () => {
                    if (this.actionBusy) return
                    this.actionBusy = 'delete'; this.actionError = ''
                    try { const response = await deleteAction(root + (selected.length === 1 ? 'delete' : 'deleteBatch'), selected.length === 1 ? { id: selected[0] } : { ids: selected.join(',') }); if (!response.success) throw new Error('删除失败'); await this.loadData(); this.$message.success('作品已删除') } catch (error) { this.actionError = '未能确认删除成功，请刷新列表核对后重试。' } finally { this.actionBusy = '' }
                } })
        },
        async exportWorks () {
            if (this.actionBusy) return
            if (this.applied.workName && !this.selectedRowKeys.length) { this.actionError = '按作品名称导出时，请先选择列表中的作业。'; return }
            if (this.applied.realname && !this.selectedRowKeys.length) { this.actionError = '按学生姓名导出时，请先选择列表中的作业。'; return }
            this.actionBusy = 'export'; this.actionError = ''
            try {
                const params = { ...this.applied }; delete params.realname; delete params.username; delete params.workTag
                if (this.applied.username) params.createBy = this.applied.username
                if (this.applied.workTag && !this.selectedRowKeys.length) { this.actionError = '按标签导出时，请先选择列表中的作业。'; return }
                if (this.selectedRowKeys.length) { params.selections = this.selectedRowKeys.join(','); delete params.workName }
                Object.keys(params).forEach(key => { if (params[key] === '') delete params[key] })
                const data = await downFile(root + 'exportXls', params)
                const bytes = new Uint8Array(await new Blob([data]).arrayBuffer())
                if (![208, 207, 17, 224, 161, 177, 26, 225].every((value, index) => bytes[index] === value)) throw new Error('导出未返回 Excel 文件')
                const url = URL.createObjectURL(new Blob([data], { type: 'application/vnd.ms-excel' })); const link = document.createElement('a'); link.href = url; link.download = '学生作品.xls'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
            } catch (error) { this.actionError = '未能导出作品，请检查网络或访问权限后重试。' } finally { this.actionBusy = '' }
        }
    }
}
</script>
<style scoped>
.teacher-workbench { max-width: 1360px; margin: 0 auto; padding: 30px 32px 48px; color: #3d3740; background: #fff; min-width: 0; }
.workbench-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 30px; }
.workbench-heading h1 { font-size: 32px; line-height: 1.3; letter-spacing: -.03em; font-weight: 600; color: #28252c; margin: 6px 0 12px; }
.workbench-heading p { color: #746b75; margin: 0; line-height: 1.8; }
.workbench-heading .workbench-eyebrow { color: #146fc2; font-size: 12px; letter-spacing: .08em; }
.work-status-tabs { display: flex; flex-wrap: wrap; gap: 6px 28px; border-bottom: 1px solid #d5e5f5; margin-bottom: 24px; }
.work-status-tabs button { border: 0; border-bottom: 3px solid transparent; padding: 12px 0; background: none; color: #746b75; font-size: 14px; cursor: pointer; }
.work-status-tabs button.active { color: #146fc2; font-weight: 600; border-bottom-color: #146fc2; }
.primary-filters { display: grid; grid-template-columns: 1.2fr 1fr 1fr auto; gap: 20px; align-items: end; }
.work-filters label { display: flex; flex-direction: column; gap: 8px; font-size: 12px; color: #675f69; }
.work-filters input, .work-filters select { width: 100%; min-width: 0; height: 40px; border: 1px solid #bccfe2; border-radius: 4px; padding: 8px 10px; background: #fff; color: #3d3740; font-size: 14px; }
.filter-actions { display: flex; align-items: center; gap: 16px; min-height: 40px; }
.more-filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; padding-top: 22px; }
.work-button { display: inline-flex; justify-content: center; align-items: center; gap: 8px; border: 1px solid #146fc2; background: #146fc2; color: #fff; border-radius: 4px; padding: 9px 16px; font-size: 13px; line-height: 20px; cursor: pointer; white-space: nowrap; }
.work-button.secondary { background: #fff; border-color: #bccfe2; color: #524753; }
.work-link { border: 0; background: none; padding: 4px 0; color: #675f69; font-size: 13px; cursor: pointer; }
.work-link:hover { color: #095b9e; text-decoration: underline; }
.work-link.danger { color: #ab4535; }
button:disabled { opacity: .5; cursor: default; }
.teacher-workbench :focus-visible { outline: 2px solid #146fc2; outline-offset: 3px; }
.work-results { margin-top: 28px; border-top: 1px solid #d5e5f5; }
.results-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 22px 0; }
.results-toolbar > div { display: flex; gap: 14px; align-items: baseline; }
.results-toolbar h2 { margin: 0; color: #28252c; font-size: 17px; font-weight: 600; }
.results-toolbar span, .sort-control { font-size: 12px; color: #776d78; }
.sort-control select { color: #524753; border: 0; background: transparent; padding: 5px; }
.selection-toolbar { display: flex; gap: 18px; align-items: center; padding: 12px 16px; background: #f4f8fd; font-size: 12px; color: #675f69; }
.selection-toolbar > div { display: flex; gap: 18px; margin-left: auto; }
.selection-toolbar label { display: flex; gap: 8px; align-items: center; }
input[type='checkbox'] { accent-color: #146fc2; width: 15px; height: 15px; }
.work-row { display: grid; grid-template-columns: 18px 88px minmax(0, 1fr) 130px; gap: 20px; padding: 25px 16px; border-bottom: 1px solid #d5e5f5; align-items: start; }
.row-select { padding-top: 27px; }
.work-cover { width: 88px; height: 72px; border-radius: 3px; overflow: hidden; display: grid; place-items: center; background: #eef6ff; color: #648ab2; font-size: 28px; }
.work-cover img { width: 100%; height: 100%; object-fit: cover; }
.work-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 7px 12px; color: #776d78; font-size: 11px; }
.work-badge { background: #f0f3f0; color: #6b7b72; padding: 2px 7px; border-radius: 3px; }
.work-badge.state-1 { background: #fff1e7; color: #985632; }
.work-badge.state-2 { background: #e9f2eb; color: #3f6b50; }
.work-badge.state-3, .work-badge.state-4 { background: #e9f1f2; color: #3a6b70; }
.work-summary h3 { margin: 10px 0 9px; font-size: 18px; line-height: 1.55; font-weight: 600; }
.work-summary h3 button { color: #28252c; background: none; padding: 0; border: 0; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.work-summary p { margin: 5px 0; overflow-wrap: anywhere; }
.work-student { font-size: 13px; color: #635a65; }
.work-time { font-size: 12px; line-height: 1.8; color: #817582; }
.work-details { margin-top: 10px; font-size: 12px; color: #776d78; }
.work-details summary { cursor: pointer; width: fit-content; }
.work-details p { white-space: pre-wrap; line-height: 1.8; }
.work-row-actions { display: flex; flex-direction: column; align-items: center; gap: 9px; padding-top: 15px; }
.work-pagination { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-top: 24px; font-size: 12px; color: #776d78; }
.work-pagination > div { display: flex; gap: 10px; align-items: center; }
.work-pagination p { margin: 0; }
.work-pagination select { border: 1px solid #bccfe2; background: white; padding: 5px; border-radius: 3px; }
.work-state { text-align: center; color: #817582; padding: 70px 16px; }
.work-state > .anticon { font-size: 30px; }
.work-state h3 { color: #28252c; font-size: 18px; margin: 18px 0 12px; }
.work-state p { font-size: 13px; line-height: 1.8; }
.work-error { color: #a74335; background: #fff4ee; padding: 12px; margin: 14px 0; font-size: 13px; }
.work-muted { color: #817582; font-size: 12px; margin-top: 12px; }
.tag-label { display: block; margin-bottom: 12px; color: #524753; }
.tag-choices { display: flex; flex-wrap: wrap; gap: 8px; }
.tag-choices span { border: 1px solid #bccfe2; border-radius: 3px; display: flex; }
.tag-choices button { background: none; border: 0; padding: 4px 8px; color: #675f69; cursor: pointer; }
@media (max-width: 1050px) { .primary-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; } .filter-actions { grid-column: 1 / -1; } .more-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .teacher-workbench { padding: 24px; } .work-row { grid-template-columns: 18px 64px minmax(0, 1fr) 120px; gap: 14px; padding-inline: 0; } .work-cover { width: 64px; height: 60px; } }
@media (max-width: 600px) { .teacher-workbench { padding: 22px 16px 32px; } .workbench-heading { align-items: flex-start; gap: 12px; } .workbench-heading h1 { font-size: 27px; } .workbench-heading > button { font-size: 0; padding: 9px; } .workbench-heading > button .anticon { font-size: 15px; } .workbench-heading p { font-size: 12px; } .work-status-tabs { gap: 2px 22px; } .primary-filters { grid-template-columns: 1fr 1fr; gap: 14px; } .primary-filters > label:first-child { grid-column: 1 / -1; } .more-filters { grid-template-columns: 1fr; } .work-row { grid-template-columns: 18px minmax(0, 1fr); gap: 12px; padding: 22px 0; } .work-cover { display: none; } .work-summary h3 { font-size: 17px; } .row-select { padding-top: 5px; } .work-row-actions { grid-column: 2; flex-direction: row; justify-content: flex-start; gap: 18px; padding-top: 2px; } .work-row-actions .work-button { padding: 7px 12px; } .selection-toolbar { gap: 10px; flex-wrap: wrap; padding: 10px; } .selection-toolbar > div { gap: 14px; } .results-toolbar { gap: 10px; } .results-toolbar > div { gap: 8px; } .work-pagination { flex-direction: column; align-items: flex-start; } .work-pagination > div { flex-wrap: wrap; } }
</style>
