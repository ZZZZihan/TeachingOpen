<template>
  <main class="learning-entry assignment-page">
    <header class="learning-heading">
      <div>
        <p class="learning-eyebrow">MY ASSIGNMENTS</p>
        <h1>任务与反馈</h1>
        <p class="learning-lead">查看班级作业，继续完成你的作品，也把老师的建议带进下一次尝试。</p>
      </div>
      <button class="learning-text-link refresh-button" :disabled="loading" @click="getList">{{ loading ? '正在更新…' : '刷新列表' }}</button>
    </header>

    <div class="assignment-toolbar">
      <div class="assignment-filters" role="group" aria-label="按提交状态筛选">
        <button v-for="filter in filters" :key="filter.value" :aria-pressed="queryParam.status === filter.value" @click="handleChangeStatus(filter.value)">{{ filter.label }}</button>
      </div>
      <p class="assignment-count" aria-live="polite">{{ loading ? '正在读取作业' : listError ? '列表尚未更新' : '共 ' + datasource.length + ' 项作业' }}</p>
    </div>

    <section v-if="loading" class="learning-state" role="status" aria-label="正在加载作业">
      <span class="loading-line" aria-hidden="true"></span><h2>正在读取班级作业</h2><p>任务要求和老师的反馈会显示在这里。</p>
    </section>
    <section v-else-if="listError" class="learning-state" role="alert">
      <p class="learning-eyebrow">暂时无法读取</p><h2>作业列表没有加载成功</h2><p>请检查网络后重试。已保存的作品不会因为刷新失败而丢失。</p>
      <button class="learning-button" @click="getList">重新加载</button>
    </section>
    <section v-else-if="!datasource.length" class="learning-state">
      <p class="learning-eyebrow">{{ queryParam.status === 'true' ? '等待你的第一份作品' : '当前列表为空' }}</p>
      <h2>{{ emptyTitle }}</h2><p>{{ emptyDescription }}</p>
      <button v-if="queryParam.status !== ''" class="learning-button" @click="handleChangeStatus('')">查看全部作业</button>
    </section>

    <section v-else aria-label="班级作业列表" class="assignment-list">
      <article v-for="(work, index) in visibleWorks" :key="rowKey(work, index)" class="assignment-item">
        <div class="assignment-main">
          <div class="assignment-overview">
            <div class="assignment-cover" aria-hidden="true">
              <img v-if="coverUrl(work)" :src="coverUrl(work)" alt="" @error="coverFailed(work)" />
              <span v-else>{{ typeLabel(work) }}</span>
            </div>
            <div class="assignment-heading">
              <p class="assignment-type">{{ typeLabel(work) }}</p>
              <h2>{{ work.workName || '未命名作业' }}</h2>
              <p class="assignment-meta"><span>{{ work.departName || '班级名称暂缺' }}</span><span>发布教师 · {{ work.createBy_dictText || '暂未提供' }}</span></p>
            </div>
          </div>
          <div class="assignment-requirement">
            <p class="section-label">任务要求</p>
            <p class="assignment-description">{{ description(work) || '老师暂未填写作业说明，请查看作业资料或向老师确认要求。' }}</p>
          </div>
          <section v-if="hasFeedback(work)" class="assignment-feedback" aria-label="教师反馈">
            <div class="feedback-heading"><h3>教师反馈</h3><p v-if="hasScore(work)" class="feedback-score"><span>评分</span><strong>{{ work.score }}</strong><span>/ 5</span></p></div>
            <p class="feedback-comment">{{ work.comment || '老师暂未留下文字评语。' }}</p>
          </section>
        </div>
        <aside class="assignment-actions" :aria-label="(work.workName || '作业') + '的状态与操作'">
          <p class="assignment-status" :class="'status-' + statusInfo(work).tone"><span aria-hidden="true"></span>{{ statusInfo(work).label }}</p>
          <p class="assignment-status-help">{{ statusInfo(work).help }}</p>
          <button v-if="canEdit(work)" class="learning-button" @click="toAdditionalWork(work, false)">{{ primaryLabel(work) }}<span aria-hidden="true">↗</span></button>
          <a v-if="submittedUrl(work)" class="assignment-link" :href="submittedUrl(work)" target="_blank" rel="noopener noreferrer">打开我的作品文件 <span aria-hidden="true">↗</span></a>
          <p v-else-if="work.mineWorkId" class="file-unavailable">作品文件暂不可用</p>
          <button v-if="work.workDocumentUrl" class="assignment-link" @click="openWorkFile(work, index)">打开作业资料 <span aria-hidden="true">↗</span></button>
          <button v-if="canEdit(work) && work.mineWorkId" class="assignment-link reset-link" @click="toAdditionalWork(work, true)">重新开始</button>
          <p v-if="actionError === rowKey(work, index)" role="alert" class="assignment-action-error">资料暂时无法打开，请刷新后重试，或联系老师确认链接。</p>
        </aside>
      </article>
      <nav v-if="totalPages > 1" class="assignment-pagination" aria-label="作业列表分页">
        <button :disabled="page === 1" @click="changePage(page - 1)">上一页</button>
        <p aria-live="polite">第 {{ page }} / {{ totalPages }} 页</p>
        <button :disabled="page === totalPages" @click="changePage(page + 1)">下一页</button>
      </nav>
    </section>
    <TeachingWorkSubmitModal ref="submitModal" @ok="getList" />
  </main>
</template>

<script>
import { getAction, getFilePrevew } from '@/api/manage'
import TeachingWorkSubmitModal from '@/views/teaching/modules/TeachingWorkSubmitModal'

export default {
    components: { TeachingWorkSubmitModal },
    data () {
        return {
            datasource: [],
            page: 1,
            pageSize: 8,
            loading: true,
            listError: false,
            listVersion: 0,
            actionError: '',
            brokenCovers: {},
            queryParam: { status: 'false' },
            filters: [{ value: 'false', label: '未提交' }, { value: 'true', label: '已提交' }, { value: '', label: '全部作业' }]
        }
    },
    computed: {
        totalPages () { return Math.max(1, Math.ceil(this.datasource.length / this.pageSize)) },
        visibleWorks () { return this.datasource.slice((this.page - 1) * this.pageSize, this.page * this.pageSize) },
        emptyTitle () { return this.queryParam.status === 'false' ? '没有待提交的作业' : this.queryParam.status === 'true' ? '还没有已提交的作业' : '暂时没有班级作业' },
        emptyDescription () { return this.queryParam.status === 'false' ? '可以切换到全部作业，回顾已经提交的作品和反馈。' : this.queryParam.status === 'true' ? '完成并提交作业后，可以在这里查看提交状态和老师的反馈。' : '老师发布给你所在班级的作业会出现在这里。' }
    },
    created () { this.getList() },
    beforeDestroy () { this.listVersion += 1 },
    methods: {
        getList () {
            const version = ++this.listVersion
            this.loading = true
            this.listError = false
            this.datasource = []
            this.page = 1
            this.actionError = ''
            this.brokenCovers = {}
            return getAction('/teaching/teachingWork/mineAdditionalWork', { submit: this.queryParam.status }).then((res) => {
                if (version !== this.listVersion) return
                if (!res || !res.success || !Array.isArray(res.result) || res.result.some(row => !row || typeof row !== 'object' || Array.isArray(row))) throw new Error('Invalid assignment list')
                this.datasource = res.result
            }).catch(() => {
                if (version === this.listVersion) this.listError = true
            }).finally(() => {
                if (version === this.listVersion) this.loading = false
            })
        },
        handleChangeStatus (value) {
            if (!this.filters.some(filter => filter.value === value) || value === this.queryParam.status) return
            this.queryParam.status = value
            this.getList()
        },
        changePage (page) { if (page >= 1 && page <= this.totalPages) this.page = page },
        rowKey (work, index = 0) { return [work.additionalWorkId || index, work.mineWorkId || '', work.departId || ''].join(':') },
        description (work) {
            return String(work.workDesc || '').replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '').replace(/<br\s*\/?\s*>|<\/(p|div|li)>/gi, '\n').replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').trim()
        },
        typeLabel (work) { return work.codeType_dictText || ({ 0: '文件作业', 1: 'Scratch', 2: 'Scratch', 3: 'ScratchJr', 4: 'Python', 10: '积木编程' })[work.codeType] || '班级作业' },
        statusInfo (work) {
            if (!work.mineWorkId) return { label: '未开始', tone: 'neutral', help: '阅读任务要求，开始完成作业。' }
            return ({
                0: { label: '已保存草稿', tone: 'neutral', help: '作品已保存，还没有提交。' },
                1: { label: '已提交 · 待批改', tone: 'pending', help: '老师批改后，反馈会显示在这里。' },
                2: { label: '已批改', tone: 'reviewed', help: '回顾老师的反馈，看看下一步可以改进什么。' },
                3: { label: '已公开展示', tone: 'reviewed', help: '作品已公开，可以在这里回顾文件与反馈。' },
                4: { label: '精选作品', tone: 'reviewed', help: '作品已入选精选，可以在这里回顾文件与反馈。' }
            })[work.mineWorkStatus] || { label: '状态待确认', tone: 'neutral', help: '请刷新列表后再操作。' }
        },
        canEdit (work) { return Boolean(work.additionalWorkId && work.departId && (!work.mineWorkId || ['0', '1'].includes(String(work.mineWorkStatus)))) },
        primaryLabel (work) { return !work.mineWorkId ? '开始作业' : Number(work.mineWorkStatus) === 0 ? '继续完成' : '修改提交' },
        hasScore (work) { return work.score !== null && work.score !== undefined && String(work.score).trim() !== '' && Number.isFinite(Number(work.score)) },
        hasFeedback (work) { return this.hasScore(work) || Boolean(work.comment && String(work.comment).trim()) || Boolean(work.mineWorkId && [2, 3, 4].includes(Number(work.mineWorkStatus))) },
        safeUrl (value) {
            if (typeof value !== 'string' || !value.trim()) return ''
            try { const url = new URL(value, window.location.origin); return ['http:', 'https:'].includes(url.protocol) ? url.href : '' } catch (error) { return '' }
        },
        submittedUrl (work) { return work.mineWorkId ? this.safeUrl(work.mineWorkUrl_url || work.mineWorkUrl) : '' },
        coverUrl (work) { return !this.brokenCovers[this.rowKey(work)] ? this.safeUrl(work.workCover_url) : '' },
        coverFailed (work) { this.$set(this.brokenCovers, this.rowKey(work), true) },
        openWorkFile (work, index = 0) {
            this.actionError = ''
            try {
                const value = work.workDocumentUrl
                const office = /\.(pptx?|docx?|xlsx?)$/i.test(String(value).split(/[?#]/)[0]) || /^aess?:/.test(value)
                const url = this.safeUrl(office ? getFilePrevew(value) : value)
                if (!url) throw new Error('Unavailable resource')
                window.open(url, '_blank', 'noopener,noreferrer')
            } catch (error) { this.actionError = this.rowKey(work, index) }
        },
        toAdditionalWork (item, reset) {
            if (!this.canEdit(item)) return
            var workUrl
            switch (item.codeType) {
            case 1:
            case 2: {
                const params = new URLSearchParams({ queryEncoding: 'uri',
                    scene: 'additional',
                    additionalId: item.additionalWorkId,
                    departId: item.departId,
                    workId: item.mineWorkId || '',
                    workName: !reset && item.mineWorkName ? item.mineWorkName : item.workName,
                    workFile: (reset ? item.workUrl_url : item.mineWorkUrl_url || item.mineWorkUrl || item.workUrl_url) || '',
                    resetTemplate: reset ? '1' : '' })
                window.open('/scratch3/index.html?' + params.toString(), '_blank', 'noopener,noreferrer')
                return
            }
            case 3:
                workUrl = '/scratchjr/editor.html?scene=additional&mode=edit&additionalId=' +
            item.additionalWorkId +
            '&departId=' +
            item.departId +
            '&workName=' +
            item.workName
                break
            case 4: {
                const params = new URLSearchParams({ queryEncoding: 'uri',
                    scene: 'additional',
                    lang: 'turtle',
                    additionalId: item.additionalWorkId,
                    departId: item.departId,
                    workId: item.mineWorkId || '',
                    workName: !reset && item.mineWorkName ? item.mineWorkName : item.workName,
                    workFile: (reset ? item.workUrl_url : item.mineWorkUrl_url || item.mineWorkUrl || item.workUrl_url) || '',
                    resetTemplate: reset ? '1' : '' })
                window.open('/python/index.html?' + params.toString(), '_blank', 'noopener,noreferrer')
                return
            }
            default:
                // workUrl = item.workUrl_url
                this.$refs.submitModal.open({
                    id: item.mineWorkId || '',
                    workName: !reset && item.mineWorkName ? item.mineWorkName : item.workName,
                    additionalId: item.additionalWorkId,
                    departId: item.departId,
                    workType: 0
                })
                return
            }

            if (!reset && item.mineWorkUrl) {
                workUrl += '&workFile=' + item.mineWorkUrl
            } else {
                workUrl += '&workFile=' + item.workUrl_url
            }
            window.open(workUrl, '_blank', 'noopener,noreferrer')
        }
    }
}
</script>

<style lang="less" scoped>
@import './styles/learning-entry.less';
.assignment-page { max-width: 1200px; }
.refresh-button { min-height: 44px; text-decoration: underline; text-underline-offset: 5px; }
.refresh-button:disabled { cursor: wait; color: #7c878e; }
.assignment-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 28px; }
.assignment-filters { display: flex; gap: 26px; }
.assignment-filters button { border: 0; border-bottom: 2px solid transparent; padding: 10px 0; background: none; color: #62727c; cursor: pointer; font: inherit; font-size: 14px; }
.assignment-filters button[aria-pressed='true'] { color: #172d38; border-color: #b63e4b; font-weight: 600; }
.assignment-count { margin: 0; color: #62727c; font-size: 12px; flex-shrink: 0; }
.assignment-list { border-top: 1px solid #dce2e5; }
.assignment-item { display: grid; grid-template-columns: minmax(0, 1fr) 192px; gap: 40px; padding: 34px 0; border-bottom: 1px solid #dce2e5; }
.assignment-main, .assignment-heading { min-width: 0; }
.assignment-overview { display: flex; align-items: flex-start; gap: 20px; }
.assignment-cover { width: 100px; height: 84px; flex-shrink: 0; background: #eef2f2; display: flex; align-items: center; justify-content: center; border: 1px solid #e2e8e7; color: #60736f; font-size: 12px; overflow: hidden; text-align: center; padding: 8px; }
.assignment-cover img { width: calc(100% + 16px); height: calc(100% + 16px); object-fit: cover; max-width: none; }
.assignment-type { margin: 0 0 7px; color: #87505c; font-size: 11px; letter-spacing: .5px; }
.assignment-heading h2 { font-size: 22px; line-height: 1.55; letter-spacing: -.25px; font-weight: 600; margin: 0 0 10px; color: #172d38; overflow-wrap: anywhere; }
.assignment-meta { display: flex; flex-wrap: wrap; column-gap: 18px; row-gap: 4px; color: #697982; font-size: 12px; line-height: 1.8; margin: 0; overflow-wrap: anywhere; }
.assignment-requirement { margin-top: 24px; }
.section-label { color: #172d38; font-size: 12px; font-weight: 600; margin: 0 0 8px; }
.assignment-description, .feedback-comment { color: #596d78; font-size: 14px; line-height: 1.95; white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }
.assignment-feedback { margin-top: 24px; padding: 20px 24px; background: #f2f6f4; border-left: 2px solid #699181; }
.feedback-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.feedback-heading h3 { color: #2d5648; font-size: 13px; font-weight: 600; margin: 0; }
.feedback-score { display: flex; align-items: baseline; gap: 8px; color: #526c62; font-size: 12px; margin: 0; }
.feedback-score strong { font-size: 24px; line-height: 1; font-weight: 500; color: #2d5648; }
.feedback-comment { color: #456153; }
.assignment-actions { min-width: 0; padding-top: 3px; }
.assignment-status { display: flex; align-items: center; gap: 8px; color: #536974; font-size: 13px; font-weight: 600; margin: 0 0 10px; }
.assignment-status > span { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.status-pending { color: #85602d; }.status-reviewed { color: #2d6a52; }
.assignment-status-help { color: #6c7b83; font-size: 12px; line-height: 1.85; margin: 0 0 20px; }
.assignment-actions .learning-button { width: 100%; justify-content: space-between; }
.assignment-link { display: flex; justify-content: space-between; width: 100%; background: none; border: 0; border-bottom: 1px solid #e5e9eb; border-radius: 0; padding: 12px 0; margin-top: 2px; color: #536974; font: inherit; font-size: 12px; cursor: pointer; text-decoration: none; text-align: left; }
.assignment-link:hover { color: #a73542; }.reset-link { border-bottom: 0; color: #76848b; }
.file-unavailable, .assignment-action-error { font-size: 12px; color: #7b6b57; line-height: 1.8; margin: 14px 0 0; }.assignment-action-error { color: #a73542; }
.assignment-pagination { display: flex; align-items: center; justify-content: center; gap: 24px; padding-top: 28px; }.assignment-pagination p { margin: 0; font-size: 12px; color: #62727c; }
.assignment-pagination button { min-height: 40px; padding: 8px 14px; background: #fff; border: 1px solid #dce2e5; color: #172d38; font: inherit; font-size: 12px; cursor: pointer; }.assignment-pagination button:disabled { opacity: .45; cursor: default; }
.learning-state h2 { font-size: 21px; color: #172d38; margin: 14px 0 12px; }.learning-state p { line-height: 1.9; }.loading-line { display: block; width: 32px; height: 2px; background: #b63e4b; margin: 0 auto 24px; }
@media (max-width: 800px) { .assignment-item { gap: 28px; grid-template-columns: minmax(0, 1fr) 170px; }.assignment-cover { width: 74px; height: 70px; }.assignment-overview { gap: 14px; }.assignment-heading h2 { font-size: 20px; } }
@media (max-width: 600px) { .assignment-toolbar { align-items: flex-start; flex-direction: column; gap: 12px; margin-bottom: 22px; }.assignment-item { grid-template-columns: minmax(0, 1fr); gap: 24px; padding: 26px 0; }.assignment-actions { border-top: 1px solid #e7ebed; padding-top: 20px; }.assignment-status-help { margin-bottom: 14px; }.assignment-actions .learning-button { width: auto; min-width: 170px; }.assignment-feedback { padding: 18px; }.assignment-requirement { margin-top: 20px; }.assignment-filters { gap: 24px; }.assignment-link { max-width: 100%; } }
</style>
