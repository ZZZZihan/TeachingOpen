<template>
  <div class="j-editor" :class="{ 'j-editor-fullscreen': fullscreen }">
    <div class="j-editor-toolbar" role="toolbar" aria-label="正文编辑工具">
      <button
        v-for="button in buttons"
        :key="button.command"
        type="button"
        :disabled="!active || disabled || uploading"
        @mousedown.prevent
        @click="run(button.command)">{{ button.label }}</button>
      <select aria-label="段落格式" :disabled="!active || disabled" @change="format($event.target.value)"><option value="paragraph">正文</option><option value="h1">标题 1</option><option value="h2">标题 2</option><option value="h3">标题 3</option><option value="h4">标题 4</option><option value="h5">标题 5</option><option value="h6">标题 6</option><option value="blockquote">引用</option></select>
      <label>文字颜色<input type="color" aria-label="文字颜色" :disabled="!active || disabled" @input="color('setColor', $event.target.value)"></label>
      <label>背景颜色<input type="color" aria-label="背景颜色" :disabled="!active || disabled" @input="color('setBackgroundColor', $event.target.value)"></label>
      <button
        v-for="item in inserts"
        :key="item.type"
        type="button"
        :disabled="!active || disabled || uploading"
        @mousedown.prevent
        @click="openDialog(item.type)">{{ item.label }}</button>
      <select aria-label="表格操作" :disabled="!active || disabled" value="" @change="table($event)"><option value="">表格</option><option value="insertTable">插入 3 × 3 表格</option><option value="addRowAfter">添加行</option><option value="addColumnAfter">添加列</option><option value="deleteRow">删除行</option><option value="deleteColumn">删除列</option><option value="mergeCells">合并单元格</option><option value="splitCell">拆分单元格</option><option value="deleteTable">删除表格</option></select>
      <button type="button" :disabled="!active" @click="preview = !preview">{{ preview ? '继续编辑' : '预览' }}</button>
      <button type="button" :disabled="!active" @click="fullscreen = !fullscreen">{{ fullscreen ? '退出全屏' : '全屏' }}</button>
    </div>
    <div v-show="!preview" ref="surface" class="j-editor-surface" :style="{ minHeight: height + 'px' }" @click="onClick"></div>
    <div v-if="preview" class="j-editor-preview" :style="{ minHeight: height + 'px' }" v-html="previewHtml"></div>
    <div class="j-editor-status" aria-live="polite">{{ uploading ? '正在上传…' : wordCount + ' 字' }}<span v-if="error" role="alert"> · {{ error }}</span></div>
    <a-modal
      :visible="Boolean(dialog)"
      :title="dialogTitle"
      :width="760"
      :confirmLoading="uploading"
      :okButtonProps="{ props: { disabled: !active || disabled || uploading } }"
      @ok="applyDialog"
      @cancel="closeDialog">
      <template v-if="dialog === 'source'"><p>保留安全的正文、图片、视频和表格格式，保存时自动移除可执行代码。</p><textarea v-model="draft" aria-label="HTML 源码" class="j-editor-source" rows="14"></textarea></template>
      <template v-else-if="dialog === 'codeSample'"><label>代码语言<select v-model="language" aria-label="代码语言"><option v-for="item in languages" :key="item" :value="item">{{ item }}</option></select></label><textarea v-model="draft" aria-label="代码示例" class="j-editor-source" rows="10"></textarea></template>
      <template v-else><label>{{ dialog === 'link' ? '链接地址' : '媒体地址' }}<a-input v-model="draft" :disabled="uploading" placeholder="输入地址" /></label><label v-if="dialog === 'image'">图片说明<a-input v-model="description" /></label><label v-if="dialog !== 'link'" class="j-editor-upload">上传{{ dialog === 'image' ? '图片' : '视频' }}<input :key="fileInputKey" type="file" :accept="dialog === 'image' ? 'image/png,image/jpeg,image/gif,image/webp' : 'video/*'" :disabled="!active || disabled || uploading" @change="uploadFile"></label></template>
      <p v-if="error" role="alert" class="j-editor-error">{{ error }}</p>
    </a-modal>
  </div>
</template>

<script>
import Vue from 'vue'
import { Editor, Node, Extension, mergeAttributes } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { TableKit } from '@tiptap/extension-table'
import { TextStyle, Color, BackgroundColor } from '@tiptap/extension-text-style'
import TextAlign from '@tiptap/extension-text-align'
import { SYS_CONFIG } from '@/store/mutation-types'
import { uploadAction, getAction, postAction, getFileAccessHttpUrl } from '@/api/manage'
import { getVmParentByName } from '@/utils/util'
import { sanitizeRichText, safeMediaUrl } from '@/utils/richText'

const Video = Node.create({
    name: 'video',
    group: 'block',
    atom: true,
    addAttributes () {
        return { src: { default: null, parseHTML: element => element.getAttribute('src') || (element.querySelector('source') && element.querySelector('source').getAttribute('src')) }, poster: { default: null }, width: { default: null }, height: { default: null } }
    },
    parseHTML () { return [{ tag: 'video' }] },
    renderHTML ({ HTMLAttributes }) { return ['video', mergeAttributes(HTMLAttributes, { controls: '', preload: 'metadata' })] }
})
const Presentation = Extension.create({
    name: 'presentation',
    addGlobalAttributes () {
        return [{ types: ['paragraph', 'heading', 'blockquote', 'listItem', 'table', 'tableCell', 'tableHeader', 'image', 'video'],
            attributes: {
                style: { default: null, parseHTML: element => element.getAttribute('style') }, width: { default: null, parseHTML: element => element.getAttribute('width') }, height: { default: null, parseHTML: element => element.getAttribute('height') }
            } }]
    }
})
export default {
    name: 'JEditor',
    props: {
        value: { type: String, required: false },
        triggerChange: { type: Boolean, default: false },
        disabled: { type: Boolean, default: false },
        active: { type: Boolean, default: true },
        session: { type: [String, Number], default: 0 },
        height: { type: Number, default: 300 },
        plugins: { type: [String, Array], default: '' },
        toolbar: { type: [String, Array], default: '' },
        uploadTarget: { type: String, default: () => (Vue.ls && Vue.ls.get(SYS_CONFIG) || {}).uploadType || 'local' }
    },
    data () {
        return {
            myValue: sanitizeRichText(this.value),
            fullscreen: false,
            preview: false,
            dialog: '',
            draft: '',
            description: '',
            language: 'javascript',
            languages: ['markup', 'javascript', 'css', 'php', 'ruby', 'python', 'java', 'c', 'csharp', 'cpp'],
            uploading: false,
            error: '',
            fileInputKey: 0,
            inserts: [{ type: 'link', label: '链接' }, { type: 'image', label: '图片' }, { type: 'video', label: '视频' }, { type: 'codeSample', label: '代码示例' }, { type: 'source', label: 'HTML 源码' }],
            buttons: [
                { label: '撤销', command: 'undo' }, { label: '重做', command: 'redo' }, { label: '粗体', command: 'toggleBold' }, { label: '斜体', command: 'toggleItalic' }, { label: '下划线', command: 'toggleUnderline' }, { label: '行内代码', command: 'toggleCode' },
                { label: '左对齐', command: 'left' }, { label: '居中', command: 'center' }, { label: '右对齐', command: 'right' }, { label: '两端对齐', command: 'justify' }, { label: '无序列表', command: 'toggleBulletList' }, { label: '有序列表', command: 'toggleOrderedList' },
                { label: '缩进', command: 'indent' }, { label: '减少缩进', command: 'outdent' }, { label: '分隔线', command: 'setHorizontalRule' }, { label: '取消链接', command: 'unsetLink' }, { label: '清除格式', command: 'removeFormat' }
            ]
        }
    },
    computed: {
        previewHtml () { return sanitizeRichText(this.myValue) },
        wordCount () { const node = document.createElement('div'); node.innerHTML = this.previewHtml; return (node.textContent || '').replace(/\s/g, '').length },
        dialogTitle () { return { source: '编辑 HTML 源码', codeSample: '插入代码示例', link: '插入链接', image: '插入图片', video: '插入视频' }[this.dialog] || '' },
        editor: { cache: false, get () { return this._editor } }
    },
    watch: {
        value (value) { const clean = sanitizeRichText(value); if (clean !== this.myValue) { this.resetTransient(); this.myValue = clean; if (this._editorInitialized) this.recreateEditor() } },
        disabled (value) { if (value) this.resetTransient(); if (this._editor) this._editor.setEditable(!value && this.active, false) },
        active (value) { if (!value) this.resetTransient(); if (this._editor) this._editor.setEditable(value && !this.disabled, false) },
        session () { this.resetTransient(); if (this._editorInitialized) this.recreateEditor() },
        fullscreen (value) {
            if (value && this.active) {
                this._fullscreenAnchor = document.createComment('editor')
                this.$el.parentNode.insertBefore(this._fullscreenAnchor, this.$el)
                document.body.appendChild(this.$el)
            } else this.restorePosition()
        }
    },
    mounted () { this._uploadGeneration = 0; this._editorGeneration = 0; this._editorInitialized = true; this.createEditor(); this.initATabsChangeAutoReload(); this._escape = event => { if (event.key === 'Escape') this.fullscreen = false }; window.addEventListener('keydown', this._escape) },
    beforeDestroy () { this._uploadGeneration++; this.restorePosition(); if (this._editor) this._editor.destroy(); if (this._tabs) this._tabs.$off('change', this._tabChange); window.removeEventListener('keydown', this._escape) },
    methods: {
        resetTransient () {
            this.closeDialog()
            this.draft = ''; this.description = ''; this.preview = false; this.fullscreen = false
            this.restorePosition()
        },
        restorePosition () {
            if (this._fullscreenAnchor && this._fullscreenAnchor.parentNode) {
                this._fullscreenAnchor.parentNode.insertBefore(this.$el, this._fullscreenAnchor)
                this._fullscreenAnchor.parentNode.removeChild(this._fullscreenAnchor)
                this._fullscreenAnchor = null
            }
        },
        createEditor () {
            this._editor = new Editor({ element: this.$refs.surface,
                editable: this.active && !this.disabled,
                content: this.myValue,
                extensions: [StarterKit.configure({ link: { openOnClick: false, defaultProtocol: 'https' } }), Image.configure({ allowBase64: true }), TableKit.configure({ table: { resizable: true } }), TextStyle, Color, BackgroundColor, TextAlign.configure({ types: ['heading', 'paragraph'] }), Video, Presentation],
                editorProps: { attributes: { 'aria-label': '正文编辑区', role: 'textbox', 'aria-multiline': 'true' }, transformPastedHTML: html => sanitizeRichText(html) },
                onUpdate: ({ editor }) => this.publish(sanitizeRichText(editor.getHTML())) })
        },
        publish (html) { this.myValue = html; this.$emit(this.triggerChange ? 'change' : 'input', html) },
        run (command) {
            if (!this._editor || this.disabled || !this.active) return
            const chain = this._editor.chain().focus()
            if (['left', 'center', 'right', 'justify'].includes(command)) chain.setTextAlign(command).run()
            else if (command === 'removeFormat') chain.unsetAllMarks().clearNodes().run()
            else if (command === 'indent' || command === 'outdent') {
                if (this._editor.isActive('listItem')) chain[command === 'indent' ? 'sinkListItem' : 'liftListItem']('listItem').run()
                else { const match = (this._editor.getAttributes('paragraph').style || '').match(/margin-left:(\d+)/); const current = parseInt(match && match[1] || '0', 10); chain.updateAttributes('paragraph', { style: 'margin-left:' + Math.max(0, current + (command === 'indent' ? 32 : -32)) + 'px;' }).run() }
            } else if (chain[command]) chain[command]().run()
        },
        format (value) { if (!this._editor || this.disabled || !this.active) return; const chain = this._editor.chain().focus(); if (/^h[1-6]$/.test(value)) chain.setHeading({ level: Number(value.slice(1)) }).run(); else if (value === 'blockquote') chain.toggleBlockquote().run(); else chain.setParagraph().run() },
        color (command, value) { if (this._editor && !this.disabled && this.active) this._editor.chain().focus()[command](value).run() },
        table (event) { const command = event.target.value; event.target.value = ''; if (this._editor && !this.disabled && this.active && command) this._editor.chain().focus()[command](command === 'insertTable' ? { rows: 3, cols: 3, withHeaderRow: true } : undefined).run() },
        openDialog (type) { if (this.disabled || !this.active) return; this.dialog = type; this.error = ''; this.description = ''; this.fileInputKey++; this.draft = type === 'source' ? this.myValue : type === 'link' ? this._editor.getAttributes('link').href || '' : '' },
        closeDialog () { this._uploadGeneration++; this.dialog = ''; this.uploading = false; this.error = '' },
        applyDialog () {
            if (!this._editor || this.disabled || !this.active || this.uploading) return
            const chain = this._editor.chain().focus()
            if (this.dialog === 'source') this._editor.commands.setContent(sanitizeRichText(this.draft))
            else if (this.dialog === 'codeSample') chain.insertContent({ type: 'codeBlock', attrs: { language: this.language }, content: this.draft ? [{ type: 'text', text: this.draft }] : [] }).run()
            else {
                let url = this.draft.trim()
                if (this.dialog === 'link') {
                    if (!url) { chain.unsetLink().run(); this.closeDialog(); return }
                    if (!safeMediaUrl(url) && !/^mailto:[^\s]+$/i.test(url) && !/^#[^\s]*$/.test(url)) { this.error = '请输入有效的 http、https、邮件或页面内链接'; return }
                    chain.extendMarkRange('link').setLink({ href: url, target: '_blank' }).run()
                } else { url = safeMediaUrl(url, this.dialog === 'image'); if (!url) { this.error = '请输入有效的图片或视频地址'; return }; if (this.dialog === 'image') chain.setImage({ src: url, alt: this.description }).run(); else chain.insertContent({ type: 'video', attrs: { src: url } }).run() }
            }
            this.closeDialog()
        },
        async uploadFile (event) {
            const file = event.target.files && event.target.files[0]
            if (!file || this.disabled || !this.active || this.uploading) return
            const image = this.dialog === 'image'; const generation = ++this._uploadGeneration
            this.error = ''; this.uploading = true
            try {
                if (image && !/^image\/(png|jpeg|gif|webp)$/i.test(file.type)) throw Error('仅支持 PNG、JPEG、GIF 或 WebP 图片')
                if (!image && !/^video\//.test(file.type)) throw Error('请选择视频文件')
                const url = await this.uploadMedia(file, image)
                if (generation !== this._uploadGeneration || !this.active || this._isDestroyed) return
                if (!safeMediaUrl(url, image)) throw Error('服务器未返回有效的媒体地址')
                this.draft = url
            } catch (error) { if (generation === this._uploadGeneration && !this._isDestroyed) this.error = error.message || '上传失败，请重试' } finally { if (generation === this._uploadGeneration && !this._isDestroyed) { this.uploading = false; this.fileInputKey++ } }
        },
        async uploadMedia (file, image) {
            const data = new FormData(); const config = this.$store.getters.sysConfig || {}
            if (this.uploadTarget === 'database') { if (!image) throw Error('视频文件不支持上传至数据库'); return this.readDataUrl(file) }
            if (this.uploadTarget === 'qiniu') {
                const token = await getAction('/common/qiniu/getToken', {})
                if (!token.success || !token.keyPrefix || !token.result) throw Error(token.message || '获取上传凭证失败')
                const key = token.keyPrefix + Date.now() + '-' + Math.random().toString(16).slice(2) + '-' + file.name
                data.append('file', file, file.name); data.append('token', token.result); data.append('key', key)
                const result = await uploadAction('https://upload-' + config.qiniuArea + '.qiniup.com', data)
                if (!result.key) throw Error(result.message || '上传失败，请重试')
                return this.getDownloadUrl(result.key)
            }
            if (this.uploadTarget !== 'local') throw Error('当前存储暂不支持编辑器上传')
            data.append('file', file, file.name); data.append('biz', 'jeditor')
            const result = await uploadAction(this.getUploadAction(), data)
            if (!result.success) throw Error(result.message || '上传失败，请重试')
            if (result.message === 'local') { if (!image) throw Error('视频文件不支持上传至数据库'); return this.readDataUrl(file) }
            return getFileAccessHttpUrl(result.message)
        },
        readDataUrl (file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(Error('读取图片失败')); reader.readAsDataURL(file) }) },
        getDownloadUrl (key) { const config = this.$store.getters.sysConfig || {}; return (this.uploadTarget === 'qiniu' ? config.qiniuDomain : config.staticDomain || window._CONFIG.staticDomainURL || window._CONFIG.domianURL + '/sys/common/static').replace(/\/$/, '') + '/' + key },
        getUploadAction () { return this.uploadTarget === 'qiniu' ? 'https://upload-' + this.$store.getters.sysConfig.qiniuArea + '.qiniup.com' : window._CONFIG.domianURL + '/sys/common/upload' },
        saveToDB (fileName, filePath, fileLocation, fileTag) { return postAction('/system/sysFile/add', { fileName, filePath, fileLocation, fileTag }) },
        delFromBD (filePath) { return getAction('/system/sysFile/deleteByPath', { filePath }) },
        recreateEditor () {
            // Undo history belongs to one editing record, independently of media uploads.
            const generation = ++this._editorGeneration
            if (this._editor) { this._editor.destroy(); this._editor = null }
            this.$nextTick(() => { if (!this._isDestroyed && generation === this._editorGeneration) this.createEditor() })
        },
        reload () { this.resetTransient(); this.recreateEditor() },
        clear () { if (this._editor) this._editor.commands.clearContent(); else this.publish('') },
        onClick (event) { this.$emit('onClick', event, this._editor) },
        initATabsChangeAutoReload () { const tabs = getVmParentByName(this, 'ATabs'); const pane = getVmParentByName(this, 'ATabPane'); if (tabs && pane) { this._tabs = tabs; this._tabChange = key => { if (pane.$vnode.key === key) this.reload(); else this.resetTransient() }; tabs.$on('change', this._tabChange) } }
    }
}
</script>
<style scoped>
.j-editor { border: 1px solid #d9d9d9; border-radius: 4px; background: white; }
.j-editor-toolbar { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; padding: 8px; background: #fafafa; border-bottom: 1px solid #ddd; }
.j-editor-toolbar button, .j-editor-toolbar select { padding: 3px 7px; border: 1px solid #ccc; border-radius: 3px; background: white; color: #333; cursor: pointer; }
.j-editor-toolbar button:disabled { opacity: .5; cursor: default; }
.j-editor-toolbar label { display: inline-flex; gap: 3px; align-items: center; font-size: 12px; }
.j-editor-toolbar input[type=color] { width: 28px; height: 26px; border: 0; padding: 0; }
.j-editor-surface, .j-editor-preview { padding: 12px; overflow: auto; }
.j-editor-surface /deep/ .tiptap { min-height: inherit; outline: none; overflow-wrap: anywhere; }
.j-editor-surface /deep/ table, .j-editor-preview /deep/ table { border-collapse: collapse; width: 100%; table-layout: fixed; }
.j-editor-surface /deep/ td, .j-editor-surface /deep/ th, .j-editor-preview /deep/ td, .j-editor-preview /deep/ th { border: 1px solid #bbb; padding: 6px; min-width: 30px; position: relative; }
.j-editor-surface /deep/ .selectedCell { background: #dceefe; }
.j-editor-surface /deep/ img, .j-editor-surface /deep/ video, .j-editor-preview /deep/ img, .j-editor-preview /deep/ video { max-width: 100%; }
.j-editor-surface /deep/ pre, .j-editor-preview /deep/ pre { padding: 12px; background: #f2f3f5; white-space: pre-wrap; }
.j-editor-status { padding: 4px 12px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }
.j-editor-error { color: #c00; margin-top: 12px; }
.j-editor-source { width: 100%; font-family: monospace; margin-top: 12px; }
.j-editor-upload { display: block; margin-top: 16px; }
.j-editor-fullscreen { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; }
.j-editor-fullscreen .j-editor-surface, .j-editor-fullscreen .j-editor-preview { flex: 1; }
</style>
