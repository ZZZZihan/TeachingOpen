<template>
  <main class="course-workbench">
    <header class="course-heading">
      <div>
        <p class="course-eyebrow">TeachingOpen · 教学管理</p>
        <h1>课程单元</h1>
        <p class="course-lead">按课程整理教学单元，维护学习内容、作业要求与展示顺序。</p>
      </div>
      <button class="course-button" :disabled="Boolean(actionBusy)" data-testid="add-unit" @click="handleAdd">
        <a-icon type="plus" /> 新增单元
      </button>
    </header>
    <form class="course-filters" @submit.prevent="searchQuery">
      <div class="course-filter-grid unit-filter-grid">
        <div class="course-field">
          <span id="unit-course-label">所属课程</span>
          <j-dict-select-tag
            ref="courseFilter"
            v-model="queryParam.courseId"
            type="list"
            :defaultShowAll="true"
            dictCode="teaching_course,course_name,id"
            placeholder="全部课程"
            aria-labelledby="unit-course-label" />
        </div>
        <label for="unit-name-filter">单元名称
          <input id="unit-name-filter" v-model="queryParam.unitName" type="search" placeholder="输入单元名称" data-testid="unit-name-filter">
        </label>
        <div class="course-filter-actions">
          <button type="submit" class="course-button" data-testid="query-submit"><a-icon type="search" /> 查询</button>
          <button type="button" class="course-link" data-testid="query-reset" @click="searchReset">重置</button>
        </div>
      </div>
    </form>
    <section class="course-results" aria-labelledby="course-results-title" :aria-busy="loading">
      <div class="course-results-heading">
        <div class="course-results-summary">
          <h2 id="course-results-title">单元列表</h2>
          <span v-if="!loading && !listError">共 {{ ipagination.total }} 个单元</span>
          <span v-else>{{ loading ? '正在读取单元…' : '列表暂不可用' }}</span>
          <span v-if="hasAppliedFilters" class="course-filter-note">已应用筛选</span>
        </div>
        <label class="course-sort">排序
          <select :value="sortValue" :disabled="loading || Boolean(actionBusy)" data-testid="list-sort" @change="changeSort($event.target.value)">
            <option value="createTime:desc">最新创建</option>
            <option value="createTime:asc">最早创建</option>
            <option value="orderNum:asc">展示排序 · 升序</option>
            <option value="orderNum:desc">展示排序 · 降序</option>
          </select>
        </label>
      </div>
      <div class="course-maintenance">
        <div class="course-maintenance-links">
          <button class="course-link" :disabled="loading || Boolean(actionBusy) || Boolean(listError)" data-testid="export-list" @click="handleExportXls('课程单元')"><a-icon type="download" /> 导出单元</button>
          <a-upload
            name="file"
            :showUploadList="false"
            :multiple="false"
            :headers="tokenHeader"
            :action="importExcelUrl"
            :disabled="Boolean(actionBusy)"
            @change="handleImportExcel">
            <button class="course-link" :disabled="Boolean(actionBusy)" data-testid="import-list"><a-icon type="upload" /> 导入单元</button>
          </a-upload>
        </div>
        <button class="course-link" :disabled="loading || Boolean(actionBusy)" data-testid="refresh-list" @click="loadData()"><a-icon type="reload" /> 刷新列表</button>
      </div>
      <p v-if="appliedFilterSummary.length" class="course-applied-filters">当前查询：{{ appliedFilterSummary.join('；') }}</p>
      <p v-if="actionError" class="course-action-error" role="alert">{{ actionError }}</p>
      <p v-if="importReport" class="course-import-report" role="status">{{ importReport.message }} <a v-if="importReport.url" :href="importReport.url" target="_blank" rel="noopener noreferrer">下载导入明细</a></p>
      <div v-if="loading" class="course-state" role="status" data-testid="list-loading">
        <a-icon type="loading" /><h3>正在读取单元</h3><p>请稍候，查询条件已保留。</p>
      </div>
      <div v-else-if="listError" class="course-state" role="alert" data-testid="list-error">
        <a-icon type="exclamation-circle" /><h3>单元列表未能加载</h3><p>{{ listError }}</p>
        <button class="course-button secondary" data-testid="retry-list" @click="loadData()">重新加载</button>
      </div>
      <div v-else-if="!dataSource.length" class="course-state" data-testid="list-empty">
        <a-icon type="book" /><h3>{{ hasAppliedFilters ? '没有找到匹配的单元' : '暂无课程单元' }}</h3>
        <p>{{ hasAppliedFilters ? '试试调整所属课程或单元名称。' : '新增单元，为课程补充学习内容与作业安排。' }}</p>
        <button v-if="hasAppliedFilters" class="course-button secondary" data-testid="empty-reset" @click="searchReset">清除筛选</button>
        <button v-else class="course-button secondary" :disabled="Boolean(actionBusy)" @click="handleAdd">新增单元</button>
      </div>
      <template v-else>
        <div class="course-selection" aria-label="单元选择与批量操作">
          <label><input type="checkbox" :checked="allSelected" :disabled="Boolean(actionBusy)" data-testid="select-all" @change="toggleAll($event.target.checked)"> 选择本页</label>
          <span>已选 {{ selectedRowKeys.length }} 个</span>
          <div v-if="selectedRowKeys.length">
            <button class="course-link" :disabled="Boolean(actionBusy)" data-testid="clear-selection" @click="onClearSelected">清空选择</button>
            <button class="course-link danger" :disabled="Boolean(actionBusy)" data-testid="batch-delete" @click="batchDel">删除所选单元</button>
          </div>
        </div>
        <div class="course-list">
          <article v-for="record in dataSource" :key="record.id" class="course-row unit-row" :data-record-id="record.id">
            <label class="course-row-select"><input type="checkbox" :checked="selectedRowKeys.includes(record.id)" :disabled="Boolean(actionBusy)" :aria-label="'选择单元 ' + (record.unitName || '未命名单元')" @change="selectRow(record, $event.target.checked)"></label>
            <div class="course-cover">
              <img v-if="coverUrl(record)" :src="coverUrl(record)" alt="" @error="markCoverBroken(record)">
              <a-icon v-else type="book" aria-hidden="true" />
            </div>
            <div class="course-row-summary">
              <div class="course-row-meta"><span>{{ record.courseName || '所属课程未返回' }}</span><span>{{ record.courseWorkType_dictText || '作业类型未设置' }}</span></div>
              <h3><button :disabled="Boolean(actionBusy)" @click="handleEdit(record)">{{ record.unitName || '未命名单元' }}</button></h3>
              <p class="unit-intro">{{ record.unitIntro || '暂未填写单元简介' }}</p>
              <div class="course-row-meta"><span>展示排序 {{ record.orderNum == null ? '未设置' : record.orderNum }}</span></div>
              <p class="course-record-origin">{{ record.createBy || '创建人未记录' }}<span v-if="record.createTime"> · {{ record.createTime }}</span></p>
            </div>
            <div class="course-row-actions">
              <button class="course-button secondary" :disabled="Boolean(actionBusy)" data-testid="edit-record" @click="handleEdit(record)">编辑单元</button>
              <a-popconfirm title="确认删除这个单元？" okText="删除" cancelText="保留" :disabled="Boolean(actionBusy)" @confirm="handleDelete(record.id)">
                <span><button class="course-link danger" :disabled="Boolean(actionBusy)" data-testid="delete-record">删除</button></span>
              </a-popconfirm>
            </div>
          </article>
        </div>
        <footer class="course-pagination">
          <p>第 {{ ipagination.current }} / {{ totalPages }} 页 · 本页 {{ dataSource.length }} 个单元</p>
          <div>
            <form class="course-page-jump" @submit.prevent="jumpPage">
              <label>跳至 <input
                v-model="pageJump"
                type="number"
                min="1"
                :max="totalPages"
                :disabled="loading || Boolean(actionBusy)"
                aria-label="跳转页码"
                data-testid="page-jump"> 页</label>
              <button class="course-link" :disabled="loading || Boolean(actionBusy)" type="submit">前往</button>
            </form>
            <label>每页 <select :value="ipagination.pageSize" :disabled="loading || Boolean(actionBusy)" data-testid="page-size" @change="changePageSize($event.target.value)"><option value="10">10</option><option value="20">20</option><option value="30">30</option></select> 个</label>
            <button class="course-button secondary" :disabled="ipagination.current <= 1 || loading || Boolean(actionBusy)" data-testid="previous-page" @click="changePage(ipagination.current - 1)">上一页</button>
            <button class="course-button secondary" :disabled="ipagination.current >= totalPages || loading || Boolean(actionBusy)" data-testid="next-page" @click="changePage(ipagination.current + 1)">下一页</button>
          </div>
        </footer>
      </template>
    </section>
    <teaching-course-unit-modal ref="modalForm" @ok="modalFormOk" />
  </main>
</template>

<script>
import { JeecgListMixin } from '@/mixins/JeecgListMixin'
import { getAction, deleteAction, downFile, getFileAccessHttpUrl } from '@/api/manage'
import TeachingCourseUnitModal from './modules/TeachingCourseUnitModal'
import JDictSelectTag from '@/components/dict/JDictSelectTag'

const emptyQuery = () => ({ courseId: '', unitName: '' })
export default {
    name: 'TeachingCourseUnitList',
    mixins: [JeecgListMixin],
    components: { TeachingCourseUnitModal, JDictSelectTag },
    data () {
        return {
            description: '课程单元管理页面',
            disableMixinCreated: true,
            queryParam: emptyQuery(),
            appliedQuery: emptyQuery(),
            appliedFilterSummary: [],
            listError: '',
            actionError: '',
            actionBusy: '',
            deletePromptOpen: false,
            deletePromptId: 0,
            requestId: 0,
            pageJump: '1',
            isDisposed: false,
            brokenCovers: {},
            importReport: null,
            url: {
                list: '/teaching/teachingCourseUnit/list',
                delete: '/teaching/teachingCourseUnit/delete',
                deleteBatch: '/teaching/teachingCourseUnit/deleteBatch',
                exportXlsUrl: '/teaching/teachingCourseUnit/exportXls',
                importExcelUrl: 'teaching/teachingCourseUnit/importExcel'
            }
        }
    },
    computed: {
        totalPages () { return Math.max(1, Math.ceil(this.ipagination.total / this.ipagination.pageSize)) },
        hasAppliedFilters () { return Object.values(this.appliedQuery).some(value => Boolean(value)) },
        sortValue () { return this.isorter.column + ':' + this.isorter.order },
        allSelected () { return this.dataSource.length > 0 && this.dataSource.every(row => this.selectedRowKeys.includes(row.id)) },
        importExcelUrl () { return `${window._CONFIG['domianURL']}/${this.url.importExcelUrl}` }
    },
    created () {
        const courseId = this.$route.query && this.$route.query.courseId
        if (typeof courseId === 'string') this.queryParam.courseId = courseId
        this.searchQuery()
    },
    watch: {
        '$route.query.courseId' (value) {
            this.queryParam = { ...emptyQuery(), courseId: typeof value === 'string' ? value : '' }
            this.actionError = ''; this.importReport = null
            return this.searchQuery()
        }
    },
    beforeDestroy () { this.isDisposed = true; this.requestId++ },
    methods: {
        initDictConfig () {},
        dictFilterLabel (refName, value) {
            const filter = this.$refs[refName]
            const options = filter && typeof filter.getCurrentDictOptions === 'function' ? filter.getCurrentDictOptions() : []
            const item = options.find(option => String(option.value) === String(value))
            return item ? item.text || item.label || '已选择' : '已选择'
        },
        getQueryField () { return 'id,unitName,unitIntro,unitCover,courseId,courseName,courseWorkType,courseWorkType_dictText,courseVideo,courseVideoSource,showCourseVideo,courseCase,showCourseCase,coursePpt,showCoursePpt,coursePlan,showCoursePlan,courseWork,courseWorkAnswer,mapX,mapY,mediaContent,orderNum,createBy,createTime' },
        getQueryParams () {
            const params = { ...this.appliedQuery, ...this.isorter, field: this.getQueryField(), pageNo: this.ipagination.current, pageSize: this.ipagination.pageSize }
            Object.keys(params).forEach(key => { if (params[key] === '' || params[key] === undefined || params[key] === null) delete params[key] })
            return params
        },
        searchQuery () {
            this.appliedQuery = { ...this.queryParam, unitName: (this.queryParam.unitName || '').trim() }
            this.appliedFilterSummary = []
            if (this.appliedQuery.courseId) this.appliedFilterSummary.push('所属课程：' + this.dictFilterLabel('courseFilter', this.appliedQuery.courseId))
            if (this.appliedQuery.unitName) this.appliedFilterSummary.push('单元名称：' + this.appliedQuery.unitName)
            return this.loadData(1)
        },
        searchReset () { this.queryParam = emptyQuery(); return this.searchQuery() },
        async loadData (first) {
            if (this.isDisposed) return
            if (first === 1) this.ipagination.current = 1
            this.pageJump = String(this.ipagination.current)
            const sequence = ++this.requestId
            this.loading = true; this.listError = ''; this.actionError = ''; this.onClearSelected()
            try {
                const response = await getAction(this.url.list, this.getQueryParams())
                if (sequence !== this.requestId || this.isDisposed) return
                const result = response && response.result
                if (!response || response.success !== true || !result || !Array.isArray(result.records) || result.records.some(row => !row || typeof row !== 'object' || !row.id) || result.total === null || result.total === '' || !Number.isSafeInteger(Number(result.total)) || Number(result.total) < 0) throw new Error('列表响应不完整')
                this.ipagination.total = Number(result.total)
                if (this.ipagination.current > this.totalPages) { this.ipagination.current = this.totalPages; return this.loadData() }
                this.dataSource = result.records; this.brokenCovers = {}
            } catch (error) {
                if (sequence === this.requestId && !this.isDisposed) { this.dataSource = []; this.ipagination.total = 0; this.listError = '请检查网络或当前账号的访问权限后重试，查询条件已保留。' }
            } finally { if (sequence === this.requestId && !this.isDisposed) this.loading = false }
        },
        changePage (page) { if (this.loading || this.actionBusy || !Number.isSafeInteger(page) || page < 1 || page > this.totalPages || page === this.ipagination.current) return; this.ipagination.current = page; return this.loadData() },
        jumpPage () { const page = Number(this.pageJump); if (!Number.isSafeInteger(page) || page < 1 || page > this.totalPages) { this.pageJump = String(this.ipagination.current); return } return this.changePage(page) },
        changePageSize (size) { const value = Number(size); if (this.loading || this.actionBusy || ![10, 20, 30].includes(value)) return; this.ipagination.pageSize = value; return this.loadData(1) },
        changeSort (value) { if (this.loading || this.actionBusy || !['createTime:desc', 'createTime:asc', 'orderNum:asc', 'orderNum:desc'].includes(value)) return; const [column, order] = value.split(':'); this.isorter = { column, order }; return this.loadData(1) },
        toggleAll (checked) { if (this.loading || this.actionBusy) return; this.onSelectChange(checked ? this.dataSource.map(row => row.id) : [], checked ? [...this.dataSource] : []) },
        selectRow (record, checked) { if (this.loading || this.actionBusy) return; const keys = this.selectedRowKeys.filter(id => id !== record.id); if (checked) keys.push(record.id); this.onSelectChange(keys, this.dataSource.filter(row => keys.includes(row.id))) },
        resourceUrl (value) { try { if (typeof value !== 'string' || !value.trim()) return ''; const resolved = getFileAccessHttpUrl(value.split(',')[0].trim()); if (typeof resolved !== 'string' || !resolved.trim()) return ''; const url = new URL(resolved, window.location.origin); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '' } catch (error) { return '' } },
        coverUrl (record) { return this.brokenCovers[record.id] ? '' : this.resourceUrl(record.unitCover) },
        markCoverBroken (record) { this.$set(this.brokenCovers, record.id, true) },
        handleDelete (id) { return this.deleteRecords([id]) },
        batchDel () {
            if (this.loading || this.actionBusy || this.deletePromptOpen || !this.selectedRowKeys.length) return
            const ids = [...this.selectedRowKeys]
            const listVersion = this.requestId
            const promptId = ++this.deletePromptId
            this.deletePromptOpen = true
            this.$confirm({
                title: '删除所选的 ' + ids.length + ' 个 单元？',
                content: '请确认这些单元已不再用于教学安排。删除后请核对相关课程内容。',
                okText: '删除单元',
                okType: 'danger',
                cancelText: '保留单元',
                onCancel: () => { if (promptId === this.deletePromptId) this.deletePromptOpen = false },
                onOk: () => {
                    if (this.isDisposed || promptId !== this.deletePromptId) return
                    this.deletePromptOpen = false
                    const sameSelection = ids.length === this.selectedRowKeys.length && ids.every(id => this.selectedRowKeys.includes(id))
                    if (listVersion !== this.requestId || !sameSelection) {
                        this.actionError = '列表或选择已变化，请重新选择要删除的单元。'
                        return
                    }
                    return this.deleteRecords(ids)
                }
            })
        },
        async deleteRecords (ids) {
            if (this.loading || this.actionBusy || this.isDisposed || !ids.length || ids.some(id => !id)) return
            this.actionBusy = 'delete'; this.actionError = ''
            try {
                const response = await deleteAction(ids.length === 1 ? this.url.delete : this.url.deleteBatch, ids.length === 1 ? { id: ids[0] } : { ids: ids.join(',') })
                if (this.isDisposed) return
                if (!response || response.success !== true) throw new Error('删除未确认')
                await this.loadData()
                if (!this.isDisposed) this.$message.success('单元已删除')
            } catch (error) { if (!this.isDisposed) this.actionError = '未能确认删除成功，请刷新列表核对后重试，避免重复操作。' } finally { if (!this.isDisposed) this.actionBusy = '' }
        },
        handleImportExcel (info) {
            if (this.isDisposed || !info || !info.file) return
            const file = info.file
            if (file.status === 'uploading') { this.actionBusy = 'import'; this.actionError = ''; this.importReport = null; return }
            if (!['done', 'error'].includes(file.status)) return
            this.actionBusy = ''
            if (file.status === 'error' || !file.response || file.response.success !== true) { this.actionError = '导入未能完成，请核对文件格式、网络或访问权限后重试。'; return }
            if (file.response.code === 201) {
                const result = file.response.result || {}
                this.importReport = { message: '导入已处理，请核对导入明细中的失败记录。', url: this.resourceUrl(result.fileUrl ? window._CONFIG['domianURL'] + result.fileUrl : '') }
            } else this.$message.success('单元已导入')
            return this.loadData()
        },
        async handleExportXls (fileName) {
            if (this.loading || this.listError || this.actionBusy || this.isDisposed) return
            this.actionBusy = 'export'; this.actionError = ''
            try {
                const params = { ...this.appliedQuery }; Object.keys(params).forEach(key => { if (!params[key]) delete params[key] })
                if (this.selectedRowKeys.length) params.selections = this.selectedRowKeys.join(',')
                const data = await downFile(this.url.exportXlsUrl, params)
                const bytes = new Uint8Array(await new Blob([data]).arrayBuffer())
                if (this.isDisposed) return
                if (![208, 207, 17, 224, 161, 177, 26, 225].every((value, index) => bytes[index] === value)) throw new Error('导出文件无效')
                const url = URL.createObjectURL(new Blob([data], { type: 'application/vnd.ms-excel' })); const link = document.createElement('a'); link.href = url; link.download = (fileName || '课程单元') + '.xls'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
            } catch (error) { if (!this.isDisposed) this.actionError = '未能导出单元，请检查网络或访问权限后重试。' } finally { if (!this.isDisposed) this.actionBusy = '' }
        }
    }
}
</script>

<style lang="less" src="./course-workbench.less" scoped></style>
