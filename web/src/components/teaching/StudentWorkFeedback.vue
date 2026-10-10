<template>
  <section class="student-work-feedback" aria-label="教师反馈">
    <p :class="['feedback-score', { 'score-missing': feedback.score === null }]"><span>评分</span><strong>{{ feedback.scoreLabel }}</strong></p>
    <p v-if="feedback.comment" class="feedback-summary">{{ feedback.summary }}</p>
    <p v-else class="feedback-empty">暂无评语</p>
    <button
      v-if="feedback.comment"
      ref="trigger"
      class="feedback-open"
      type="button"
      aria-haspopup="dialog"
      :aria-label="'查看' + feedback.workName + '的完整教师评语'"
      @click="openFeedback">查看完整评语 <span aria-hidden="true">↗</span></button>
    <a-modal
      :visible="visible"
      :title="detail ? detail.workName + ' · 教师反馈' : '教师反馈'"
      :width="640"
      :footer="null"
      :destroyOnClose="true"
      :afterClose="afterFeedbackClose"
      wrapClassName="student-feedback-dialog"
      @cancel="closeFeedback">
      <template v-if="detail">
        <p class="feedback-detail-score">评分：<strong>{{ detail.scoreLabel }}</strong></p>
        <h3 class="feedback-detail-heading">教师评语</h3>
        <div class="feedback-comment-region" tabindex="0" role="region" aria-label="教师评语全文，可上下滚动"><p class="feedback-full-comment">{{ detail.comment || '暂无评语' }}</p></div>
        <button class="feedback-close" type="button" @click="closeFeedback">关闭反馈</button>
      </template>
    </a-modal>
  </section>
</template>

<script>
import { studentWorkFeedback } from '@/utils/studentWorkFeedback'

export default {
    name: 'StudentWorkFeedback',
    props: { work: { type: Object, required: true } },
    data () { return { visible: false, detail: null, returnFocus: false, disposed: false } },
    computed: { feedback () { return studentWorkFeedback(this.work) } },
    watch: { work: { deep: true, handler () { this.visible = false; this.detail = null; this.returnFocus = false } } },
    beforeDestroy () { this.disposed = true; this.visible = false; this.detail = null; this.returnFocus = false },
    methods: {
        openFeedback () {
            if (this.disposed || this.visible || !this.feedback.comment) return
            this.detail = { ...this.feedback }
            this.returnFocus = true
            this.visible = true
        },
        closeFeedback () { this.visible = false },
        afterFeedbackClose () {
            if (this.visible) return
            this.detail = null
            if (!this.disposed && this.returnFocus && this.$refs.trigger && this.$refs.trigger.isConnected) this.$refs.trigger.focus()
            this.returnFocus = false
        }
    }
}
</script>

<style scoped>
.student-work-feedback { text-align: left; min-width: 0; color: #20252b; }
.feedback-score { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin: 0 0 8px; font-size: 13px; }
.feedback-score > span { color: #737b82; }
.feedback-score strong { color: #146fc2; font-weight: 600; }
.feedback-score.score-missing strong { color: #59646e; font-weight: 400; }
.feedback-summary { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; max-height: 5.4em; font-size: 13px; line-height: 1.8; margin: 0 0 9px; }
.feedback-empty { color: #737b82; font-size: 12px; margin: 0; }
.feedback-open { background: none; border: 0; padding: 2px 0; color: #146fc2; font: inherit; font-size: 12px; cursor: pointer; text-align: left; min-height: 44px; display: inline-flex; align-items: center; }
.feedback-open span { margin-left: 5px; }
.feedback-open:focus-visible, .feedback-close:focus-visible { outline: 2px solid #146fc2; outline-offset: 3px; }
.feedback-detail-score { color: #59646e; font-size: 14px; margin: 0 0 22px; }
.feedback-detail-score strong { color: #146fc2; }
.feedback-detail-heading { color: #20252b; font-size: 14px; font-weight: 600; margin: 0 0 10px; }
.feedback-comment-region { max-height: min(45vh, 360px); overflow-y: auto; margin-bottom: 24px; padding: 3px; }
.feedback-comment-region:focus-visible { outline: 2px solid #146fc2; outline-offset: 2px; }
.feedback-full-comment { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; font-size: 14px; line-height: 1.9; margin: 0; }
.feedback-close { min-height: 44px; border: 1px solid #146fc2; border-radius: 3px; background: #146fc2; color: #fff; padding: 8px 20px; font: inherit; font-size: 14px; cursor: pointer; }
</style>
<style>
.student-feedback-dialog .ant-modal { max-width: calc(100vw - 32px); margin: 0 auto; padding-bottom: 24px; }
.student-feedback-dialog .ant-modal-title { padding-right: 16px; overflow-wrap: anywhere; word-break: break-word; line-height: 1.7; color: #20252b; }
.student-feedback-dialog .ant-modal-body { max-height: calc(100vh - 190px); overflow-y: auto; }
@media (max-width: 600px) { .student-feedback-dialog .ant-modal { top: 24px; } .student-feedback-dialog .ant-modal-header, .student-feedback-dialog .ant-modal-body { padding: 20px; } .student-feedback-dialog .ant-modal-body { max-height: calc(100vh - 140px); } }
</style>
