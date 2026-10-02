<template>
  <a-modal
    title="提交文件作业"
    :width="560"
    :visible="visible"
    :footer="null"
    :maskClosable="false"
    :closable="!submitting"
    :keyboard="!submitting"
    wrapClassName="assignment-submit-modal"
    @cancel="handleCancel">
    <form v-if="visible" class="assignment-submit" @submit.prevent="handleOk">
      <p class="assignment-intro">确认作业名称和文件，提交后交由老师批改。</p>
      <label for="assignment-name">作业名称</label>
      <input
        id="assignment-name"
        v-model="workInfo.workName"
        maxlength="64"
        :disabled="submitting"
        autocomplete="off"
        aria-describedby="assignment-name-help">
      <p id="assignment-name-help" class="assignment-help">最多 64 个字符。</p>
      <label for="assignment-file">作业文件</label>
      <div class="assignment-file-box">
        <template v-if="selectedFile">
          <p class="assignment-file-name">{{ selectedFile.name }}</p>
          <p class="assignment-help">{{ formatSize(selectedFile.size) }}</p>
          <p class="assignment-file-status" role="status">{{ uploadStatus }}</p>
          <button v-if="stage === 'error'" class="assignment-text-button" type="button" @click="retryUpload">重新上传</button>
          <button class="assignment-text-button" type="button" :disabled="submitting" @click="removeFile">移除文件</button>
        </template>
        <p v-else class="assignment-help">选择一份作业文件，最大 10 MB。</p>
        <button class="assignment-choose" type="button" :disabled="submitting || uploading" aria-describedby="assignment-file-help" @click="$refs.fileInput.click()">{{ selectedFile ? '更换文件' : '选择文件' }}</button>
        <input
          :key="version + '-' + inputVersion"
          ref="fileInput"
          id="assignment-file"
          type="file"
          hidden
          :disabled="submitting || uploading"
          aria-describedby="assignment-file-help"
          @change="selectFile">
      </div>
      <p id="assignment-file-help" class="assignment-help">上传完成后，还需要点击“提交作业”。</p>
      <p v-if="error" class="assignment-error" role="alert">{{ error }}</p>
      <p v-if="submitting" class="assignment-help" role="status">正在确认提交结果，请稍候。</p>
      <div class="assignment-actions">
        <button class="assignment-secondary" type="button" :disabled="submitting" @click="handleCancel">取消</button>
        <button class="assignment-primary" type="submit" :disabled="submitting || uploading">{{ submitting ? '正在提交…' : '提交作业' }}</button>
      </div>
    </form>
  </a-modal>
</template>
<script>
import { axios } from '@/utils/request'
import { createFileTask, uploadAssignmentFile } from './assignmentFileUpload'

export default {
    name: 'TeachingWorkSubmitModal',
    data () {
        return { visible: false, workInfo: {}, selectedFile: null, fileRecord: null, task: null, stage: 'idle', submitting: false, error: '', version: 0, inputVersion: 0 }
    },
    computed: {
        uploading () { return this.stage === 'uploading' || this.stage === 'registering' },
        uploadStatus () { return { uploading: '正在上传文件…', registering: '正在确认文件记录…', ready: '文件已准备好，待提交', error: '上传未完成，请重试或重新选择文件' }[this.stage] || '' }
    },
    deactivated () { this.dispose() },
    beforeDestroy () { this.dispose() },
    methods: {
        open (info) {
            if (this.submitting) return false
            this.dispose()
            // Copy only the intended assignment; no previous file, ID or title survives.
            this.workInfo = { id: info.id || '', additionalId: info.additionalId || '', departId: info.departId || '', courseId: info.courseId || '', workName: info.workName || '', workType: String(info.workType == null ? 0 : info.workType) }
            this.visible = true
            return true
        },
        dispose () {
            this.version += 1
            if (this.task) this.task.cancel('Assignment dialog changed')
            this.task = null
            this.visible = false
            this.workInfo = {}
            this.selectedFile = null
            this.fileRecord = null
            this.stage = 'idle'
            this.submitting = false
            this.error = ''
        },
        formatSize (size) { return size < 1024 * 1024 ? Math.max(1, Math.ceil(size / 1024)) + ' KB' : (size / (1024 * 1024)).toFixed(1) + ' MB' },
        selectFile (event) {
            if (!this.visible || this.submitting || this.uploading) return
            const file = event.target.files && event.target.files[0]
            if (!file) return
            this.removeFile()
            if (!file.size || file.size > 10 * 1024 * 1024) { this.error = '请选择非空且不超过 10 MB 的文件。'; return }
            this.selectedFile = file
            this.retryUpload()
        },
        async retryUpload () {
            if (!this.visible || !this.selectedFile || this.submitting || this.uploading) return
            this.error = ''
            this.fileRecord = null
            const version = ++this.version
            const task = createFileTask()
            this.task = task
            this.stage = 'uploading'
            try {
                const record = await uploadAssignmentFile(this.selectedFile, this.$store.getters.sysConfig || {}, task, stage => {
                    if (this.visible && version === this.version) this.stage = stage
                })
                if (!this.visible || version !== this.version) return
                this.fileRecord = record
                this.stage = 'ready'
            } catch (error) {
                if (!this.visible || version !== this.version) return
                this.stage = 'error'
                this.error = '文件尚未准备好。请检查网络后重试；若仍失败，请联系老师或管理员。'
            } finally {
                if (version === this.version) this.task = null
            }
        },
        removeFile () {
            if (this.submitting) return
            this.version += 1
            if (this.task) this.task.cancel('Assignment file removed')
            this.task = null
            this.selectedFile = null
            this.fileRecord = null
            this.stage = 'idle'
            this.error = ''
            this.inputVersion += 1
        },
        async handleOk () {
            if (!this.visible || this.submitting || this.uploading) return
            this.error = ''
            const name = String(this.workInfo.workName || '').trim()
            if (!name || name.length > 64) { this.error = '请填写 1 至 64 个字符的作业名称。'; return }
            if (this.stage !== 'ready' || !this.fileRecord || !this.fileRecord.id) { this.error = '请先选择并完成上传一份作业文件。'; return }
            const version = this.version
            this.submitting = true
            try {
                const result = await axios({ url: '/teaching/teachingWork/submit', method: 'post', data: { ...this.workInfo, workName: name, workFile: this.fileRecord.id, workStatus: 1 }, localError: true })
                if (!this.visible || version !== this.version) return
                if (!result || !result.success || !result.result || !result.result.id) { this.error = '提交未完成，文件已保留。请稍后重试。'; return }
                this.dispose()
                this.$message.success('作业已提交，等待老师批改。')
                this.$emit('ok', result.result)
            } catch (error) {
                if (this.visible && version === this.version) this.error = '未能确认提交结果。文件已保留，可先返回作业列表确认状态，再重试。'
            } finally {
                if (version === this.version) this.submitting = false
            }
        },
        handleCancel () { if (!this.submitting) this.dispose() }
    }
}
</script>
<style lang="less">
.assignment-submit-modal {
  .ant-modal { max-width: calc(100vw - 32px); top: 64px; }
  .ant-modal-content { border-radius: 5px; overflow: hidden; }
  .ant-modal-header { padding: 24px 28px 18px; border-bottom: 1px solid #e0e6e9; }
  .ant-modal-title { color: #172d38; font-size: 20px; font-weight: 600; }
  .ant-modal-body { padding: 24px 28px 28px; }
  .assignment-submit { color: #172d38; }
  .assignment-intro { color: #637680; line-height: 1.8; margin-bottom: 26px; }
  .assignment-submit label { display: block; margin: 0 0 10px; font-weight: 600; }
  .assignment-submit input:not([type=file]) { width: 100%; padding: 10px 12px; border: 1px solid #b9c7ce; border-radius: 3px; background: #fff; color: #172d38; font: inherit; }
  .assignment-help { color: #687b86; font-size: 12px; line-height: 1.8; margin: 8px 0 20px; }
  .assignment-file-box { padding: 20px; background: #f5f7f7; border: 1px solid #dce4e8; border-radius: 3px; }
  .assignment-file-box .assignment-help { margin: 4px 0 14px; }
  .assignment-file-name { font-weight: 600; overflow-wrap: anywhere; margin: 0; }
  .assignment-file-status { margin: 0 0 12px; font-size: 12px; }
  .assignment-choose { display: block; padding: 9px 12px; background: #fff; border: 1px solid #b9c7ce; border-radius: 3px; color: #294652; cursor: pointer; font: inherit; font-size: 12px; }
  .assignment-error { border-left: 3px solid #b63e4b; background: #fff4f3; color: #923440; padding: 12px 14px; line-height: 1.8; font-size: 13px; }
  .assignment-actions { display: flex; justify-content: flex-end; gap: 12px; border-top: 1px solid #e0e6e9; padding-top: 22px; margin-top: 26px; }
  .assignment-primary, .assignment-secondary { min-height: 42px; padding: 10px 20px; border: 1px solid #b63e4b; border-radius: 3px; background: #b63e4b; color: #fff; font: inherit; cursor: pointer; }
  .assignment-secondary { border-color: #c7d1d6; background: #fff; color: #344f5e; }
  .assignment-text-button { padding: 0; margin: 0 16px 16px 0; border: 0; background: transparent; color: #a73542; cursor: pointer; font: inherit; font-size: 12px; }
  .assignment-submit :disabled { opacity: .55; cursor: not-allowed; }
  .assignment-submit button:focus-visible, .assignment-submit input:focus-visible { outline: 2px solid #b63e4b; outline-offset: 3px; }
  @media (max-width: 480px) { .ant-modal { top: 20px; max-width: calc(100vw - 16px); } .ant-modal-header { padding: 22px 20px 18px; } .ant-modal-body { padding: 20px; } .assignment-file-box { padding: 16px; } }
}
</style>
