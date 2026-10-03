<template>
  <a-modal
    :visible="visible"
    title="作业批改"
    :width="900"
    :footer="null"
    :mask-closable="false"
    :closable="!saving"
    :keyboard="!saving"
    wrap-class-name="grading-dialog"
    @cancel="handleCancel">
    <div v-if="loading" class="grading-state" role="status"><a-spin /><p>正在读取作品与已有反馈…</p></div>
    <div v-else-if="loadError" class="grading-state" role="alert">
      <h3>暂时无法读取这份作业</h3><p>{{ loadError }}</p><button class="grade-button" type="button" @click="load">重新读取</button>
    </div>
    <form v-else-if="ready" class="grading-content" @submit.prevent="handleOk">
      <div class="grading-context">
        <p class="grading-eyebrow">{{ record.departId_dictText || '班级未标注' }} · {{ record.realname || record.username || '学生作品' }}</p>
        <h2>{{ record.workName || '未命名作品' }}</h2>
        <p>{{ record.workType_dictText || '作品' }}<span v-if="record.createTime"> · 提交于 {{ record.createTime }}</span></p>
        <button class="grade-link" type="button" @click="$emit('preview', record)">预览作品 <a-icon type="arrow-right" /></button>
      </div>
      <div class="grading-grid">
        <section class="grading-main">
          <teaching-work-correct-form v-model="feedback" :disabled="saving" />
          <p v-if="otherFeedback.length" class="grading-note">另有 {{ otherFeedback.length }} 条已有反馈，本次保存会保留。</p>
        </section>
        <aside class="grading-settings">
          <label for="grading-name">作品名称</label>
          <input id="grading-name" v-model="workName" :disabled="saving" maxlength="64" required>
          <label for="grading-status">保存后的状态</label>
          <select id="grading-status" v-model="workStatus" :disabled="saving" required>
            <option value="0">草稿</option><option value="1">待批改</option><option value="2">已批改</option><option value="3">公开展示</option><option value="4">精选作品</option>
          </select>
          <p class="grading-note">{{ statusHelp }}</p>
          <details class="grading-discussion">
            <summary>作品讨论 <span v-if="!commentsLoading && !commentsError">{{ comments.length }}</span></summary>
            <p v-if="commentsLoading" role="status">正在读取讨论…</p>
            <div v-else-if="commentsError" role="alert"><p>讨论暂时无法读取，评分保存会保留原讨论。</p><button type="button" class="grade-link" @click="loadComments">重试</button></div>
            <p v-else-if="!comments.length">还没有讨论。</p>
            <article v-for="(comment, index) in comments" :key="comment.id || index"><strong>{{ comment.nickname || comment.createBy || '参与者' }}</strong><p>{{ comment.comment }}</p><small>{{ comment.createTime }}</small></article>
          </details>
        </aside>
      </div>
      <p v-if="saveError" class="grading-error" role="alert">{{ saveError }}</p>
      <footer class="grading-footer"><p>{{ saving ? '正在保存，请稍候…' : '反馈保存后，学生可在作业中查看。' }}</p><div><button type="button" class="grade-button secondary" :disabled="saving" @click="handleCancel">取消</button><button type="submit" class="grade-button" :disabled="saving">{{ saving ? '保存中…' : '保存批改' }}</button></div></footer>
    </form>
  </a-modal>
</template>
<script>
import { getAction, putAction } from '@/api/manage'
import TeachingWorkCorrectForm from './TeachingWorkCorrectForm.vue'
const root = '/teaching/teachingWork/'
export default {
    name: 'TeachingWorkModal',
    components: { TeachingWorkCorrectForm },
    data () {
        return { visible: false, loading: false, ready: false, saving: false, loadError: '', saveError: '', record: {}, workName: '', workStatus: '2', feedback: { score: null, comment: '' }, otherFeedback: [], comments: [], commentsLoading: false, commentsError: false, requestId: 0, commentRequestId: 0, initial: '', initialFeedback: '', feedbackRow: {} }
    },
    computed: {
        statusHelp () { return ['保留为草稿，尚未进入待批改队列。', '继续保留在待批改队列。', '标记为已批改，学生可以查看反馈。', '公开展示后，其他访问者可以查看作品。', '精选作品将公开展示。'][Number(this.workStatus)] || '请选择作品状态。' },
        dirty () { return this.ready && this.initial !== this.formSnapshot() }
    },
    beforeDestroy () { this.requestId++; this.commentRequestId++ },
    methods: {
        formSnapshot () { return JSON.stringify([this.workName, this.workStatus, this.feedback]) },
        edit (record) {
            if (this.saving) return
            this.record = { ...record }; this.visible = true; this.ready = false; this.saveError = ''; this.load()
        },
        async load () {
            const sequence = ++this.requestId
            this.ready = false; this.loading = true; this.loadError = ''; this.saveError = ''
            const id = this.record.id
            this.loadComments()
            try {
                const [work, correct] = await Promise.all([getAction(root + 'queryById', { id }), getAction(root + 'queryTeachingWorkCorrectByMainId', { id })])
                if (sequence !== this.requestId || !this.visible) return
                if (!work.success || !work.result || work.result.id !== id || !correct.success || !Array.isArray(correct.result) || correct.result.some(row => !row || typeof row !== 'object')) throw new Error('读取失败')
                this.record = { ...this.record, ...work.result }
                const first = correct.result[0] || {}
                const score = first.score === null || first.score === undefined || first.score === '' ? null : Number(first.score)
                if (score !== null && (!Number.isInteger(score) || score < 0 || score > 5)) throw new Error('原评分格式异常')
                this.feedback = { score, comment: first.comment || '' }
                this.feedbackRow = { ...first }; this.initialFeedback = JSON.stringify(this.feedback)
                this.otherFeedback = correct.result.slice(1).map(row => ({ ...row }))
                this.workName = this.record.workName || ''
                this.workStatus = String(this.record.workStatus) === '1' ? '2' : String(this.record.workStatus)
                this.initial = this.formSnapshot(); this.ready = true
            } catch (error) {
                if (sequence === this.requestId && this.visible) this.loadError = '请检查网络或访问权限后重试。原有评分未读取完整，暂不能保存。'
            } finally { if (sequence === this.requestId) this.loading = false }
        },
        async loadComments () {
            const sequence = ++this.commentRequestId; const id = this.record.id
            this.comments = []; this.commentsLoading = true; this.commentsError = false
            try {
                const response = await getAction(root + 'queryTeachingWorkCommentByMainId', { id })
                if (sequence !== this.commentRequestId || !this.visible) return
                if (!response.success || !Array.isArray(response.result) || response.result.some(row => !row || typeof row !== 'object')) throw new Error('讨论读取失败')
                this.comments = response.result
            } catch (error) { if (sequence === this.commentRequestId) this.commentsError = true } finally { if (sequence === this.commentRequestId) this.commentsLoading = false }
        },
        async handleOk () {
            if (!this.visible || !this.ready || this.loading || this.saving) return
            this.saveError = ''
            if (!this.workName.trim() || this.workName.trim().length > 64 || !['0', '1', '2', '3', '4'].includes(this.workStatus)) { this.saveError = '请填写 1–64 字的作品名称并选择保存后的状态。'; return }
            const score = this.feedback.score; const comment = this.feedback.comment.trim()
            if (comment.length > 512) { this.saveError = '评语最多 512 字，请精简后保存。'; return }
            if (score !== null && (!Number.isInteger(score) || score < 0 || score > 5)) { this.saveError = '评分应为 0–5 的整数。'; return }
            if (score === null && !comment && !this.otherFeedback.length && this.workStatus === '2') { this.saveError = '请填写评分或评语，再将作品标记为已批改。'; return }
            const body = { id: this.record.id, workName: this.workName.trim(), workStatus: this.workStatus }
            // Omit discussion entirely: a student may have posted after this dialog opened.
            if (JSON.stringify(this.feedback) !== this.initialFeedback) body.teachingWorkCorrectList = [...(score !== null || comment ? [{ ...this.feedbackRow, score, comment }] : []), ...this.otherFeedback]
            const sequence = this.requestId
            this.saving = true
            try {
                const response = await putAction(root + 'edit', body)
                if (sequence !== this.requestId || !this.visible) return
                if (!response.success) throw new Error('保存失败')
                this.saving = false; this.close(); this.$emit('ok'); this.$message.success('批改已保存')
            } catch (error) {
                if (sequence === this.requestId) this.saveError = '未能确认保存成功，填写内容已保留。请检查网络或访问权限后重试。'
            } finally { if (sequence === this.requestId) this.saving = false }
        },
        handleCancel () {
            if (this.saving) return
            if (this.dirty) this.$confirm({ title: '放弃尚未保存的批改？', content: '关闭后，本次填写的评分和评语将不会保存。', okText: '放弃修改', cancelText: '继续批改', onOk: () => this.close() })
            else this.close()
        },
        close () { this.visible = false; this.ready = false; this.requestId++; this.commentRequestId++; this.$emit('close') }
    }
}
</script>
<style>
.grading-dialog .ant-modal { max-width: calc(100vw - 32px); top: 40px; }
@media (max-width: 640px) {
  .grading-dialog .ant-modal { max-width: calc(100vw - 16px); top: 8px; margin: 0 auto; }
  .grading-dialog .ant-modal-body { padding: 20px 16px; }
}
</style>
<style scoped>
.grading-state { padding: 48px 16px; text-align: center; color: #746b75; }
.grading-context { border-bottom: 1px solid #e6e0e5; padding-bottom: 22px; margin-bottom: 26px; }
.grading-context h2 { color: #28252c; font-size: 25px; line-height: 1.45; margin: 6px 0 10px; overflow-wrap: anywhere; }
.grading-context p { color: #746b75; font-size: 13px; }
.grading-eyebrow { color: #74256a !important; letter-spacing: .03em; }
.grading-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 32px; }
.grading-settings { border-left: 1px solid #e6e0e5; padding-left: 28px; min-width: 0; }
.grading-settings label { display: block; font-weight: 600; color: #3d3740; margin-bottom: 8px; }
.grading-settings input, .grading-settings select { width: 100%; min-height: 40px; background: white; border: 1px solid #d3c9d2; border-radius: 4px; padding: 8px 10px; margin-bottom: 18px; color: #3d3740; }
.grading-note { font-size: 12px; line-height: 1.8; color: #746b75; }
.grading-discussion { margin-top: 22px; border-top: 1px solid #e6e0e5; padding-top: 18px; font-size: 13px; color: #675f69; }
.grading-discussion summary { cursor: pointer; font-weight: 600; color: #3d3740; }
.grading-discussion article { border-bottom: 1px solid #e6e0e5; padding: 16px 0; }
.grading-discussion p { white-space: pre-wrap; overflow-wrap: anywhere; margin: 10px 0; }
.grading-discussion small { color: #817582; }
.grading-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; border-top: 1px solid #e6e0e5; margin-top: 28px; padding-top: 20px; }
.grading-footer p { color: #746b75; font-size: 12px; margin: 0; }
.grading-footer > div { display: flex; gap: 10px; flex-shrink: 0; }
.grade-button { background: #74256a; color: white; border: 1px solid #74256a; border-radius: 4px; padding: 9px 18px; cursor: pointer; }
.grade-button.secondary { color: #3d3740; border-color: #d3c9d2; background: white; }
.grade-button:disabled { opacity: .6; cursor: wait; }
.grade-link { color: #74256a; border: 0; background: transparent; padding: 0; cursor: pointer; font-weight: 600; }
.grading-error { color: #a43c31; background: #fff3ef; padding: 12px; margin-top: 18px; }
.grading-content :focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
@media (max-width: 640px) { .grading-grid { grid-template-columns: 1fr; gap: 24px; } .grading-settings { border-left: 0; border-top: 1px solid #e6e0e5; padding: 24px 0 0; } .grading-footer { flex-direction: column; align-items: stretch; } .grading-footer > div { justify-content: flex-end; } .grading-context h2 { font-size: 22px; } }
</style>
