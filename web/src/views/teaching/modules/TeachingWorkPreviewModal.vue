<template>
  <a-modal
    :visible="visible"
    :title="record.workName || '作品预览'"
    :width="1100"
    :footer="null"
    :destroy-on-close="true"
    wrap-class-name="teacher-preview-dialog"
    @cancel="close">
    <div v-if="frameHref" class="work-preview">
      <p class="preview-note">交互作品在独立预览区域运行。关闭窗口会停止并释放预览。</p>
      <iframe v-if="visible" :key="frameHref" :src="frameHref" :title="record.workName || '学生作品'" allowfullscreen />
    </div>
    <div v-else class="file-preview"><a-icon type="file-text" /><h3>{{ fileUrl ? '这份作品以文件提交' : '暂时无法预览这份作品' }}</h3><p>{{ fileUrl ? '在新窗口打开文件，或保存到本机查看。' : '作品文件缺失或地址不可用，请联系管理员核对资源。' }}</p><a v-if="fileUrl" :href="fileUrl" target="_blank" rel="noopener noreferrer">打开作品文件 <a-icon type="arrow-right" /></a></div>
  </a-modal>
</template>
<script>
export default {
    name: 'TeachingWorkPreviewModal',
    data () { return { visible: false, record: {}, frameHref: '', fileUrl: '' } },
    methods: {
        safeUrl (value) { try { if (!value || !String(value).trim()) return ''; const url = new URL(value, window.location.origin); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '' } catch (error) { return '' } },
        previewCode (record) {
            this.record = { ...record }; this.frameHref = ''; this.fileUrl = this.safeUrl(record.workFileKey_url)
            const type = String(record.workType); const params = new URLSearchParams()
            if (['1', '2'].includes(type) && record.id) { params.set('workId', record.id); this.frameHref = '/scratch3/player.html?' + params.toString() } else if (type === '3' && this.fileUrl) { params.set('queryEncoding', 'uri'); params.set('mode', 'look'); params.set('workFile', this.fileUrl); if (record.id) params.set('workId', record.id); this.frameHref = '/scratchjr/editor.html?' + params.toString() } else if (type === '4' && this.fileUrl) { params.set('queryEncoding', 'uri'); params.set('lang', 'turtle'); params.set('url', this.fileUrl); this.frameHref = '/python/player.html?' + params.toString() } else if (type === '10' && record.id) { params.set('lang', 'zh-hans'); params.set('workId', record.id); this.frameHref = '/blockly/index.html?' + params.toString() }
            this.visible = true
        },
        close () { this.visible = false; this.frameHref = ''; this.fileUrl = ''; this.record = {}; this.$emit('close') }
    }
}
</script>
<style>
.teacher-preview-dialog .ant-modal { max-width: calc(100vw - 32px); top: 40px; }
@media (max-width: 640px) {
  .teacher-preview-dialog .ant-modal { max-width: calc(100vw - 16px); top: 8px; margin: 0 auto; }
  .teacher-preview-dialog .ant-modal-body { padding: 20px 16px; }
}
</style>
<style scoped>
.work-preview iframe { display: block; width: 100%; height: min(70vh, 720px); border: 1px solid #e6e0e5; background: #faf7f9; }
.preview-note { font-size: 12px; color: #746b75; line-height: 1.8; }
.file-preview { padding: 50px 14px; text-align: center; color: #746b75; }
.file-preview > .anticon { font-size: 38px; color: #93668d; }
.file-preview h3 { margin: 20px 0 12px; color: #28252c; font-size: 20px; }
.file-preview p { font-size: 13px; line-height: 1.8; }
.file-preview a { display: inline-block; margin-top: 12px; color: #74256a; }
</style>
