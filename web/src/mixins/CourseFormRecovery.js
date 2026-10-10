import { httpAction } from '@/api/manage'

// Shared by the course and unit dialogs. Server writes are never retried automatically.
export default {
    data () {
        return { saveError: '', saveVersion: 0, uploadSession: 0, uploadStates: {}, initialModel: '', discardPromptOpen: false }
    },
    computed: {
        uploadsReady () {
            return Object.keys(this.uploadStates).every(field => this.uploadStates[field] === 'ready')
        }
    },
    watch: {
        saveError (message) {
            if (!message) return
            this.$nextTick(() => {
                const alert = this.$refs.saveAlert
                if (this.visible && alert && alert.$el) {
                    alert.$el.scrollIntoView({ block: 'nearest' })
                    alert.$el.focus()
                }
            })
        }
    },
    beforeDestroy () {
        this.saveVersion += 1
        this.uploadSession += 1
    },
    methods: {
        onUploadState (field, status) {
            if (!this.visible || !status || status.session !== this.uploadSession) return
            this.$set(this.uploadStates, field, status.state)
        },
        beginEdit (record) {
            if (this.confirmLoading) return false
            this.saveVersion += 1
            this.uploadSession += 1
            this.uploadStates = {}
            this.saveError = ''
            this.form.resetFields()
            this.model = Object.assign({}, record)
            this.initialModel = JSON.stringify(this.model)
            this.visible = true
            return true
        },
        close () {
            if (this.confirmLoading) return
            this.saveVersion += 1
            this.uploadSession += 1
            this.uploadStates = {}
            if (this.$refs.mapEditor && this.$refs.mapEditor.close) this.$refs.mapEditor.close()
            this.visible = false
            this.$emit('close')
        },
        handleCancel () {
            if (this.confirmLoading || !this.visible || this.discardPromptOpen) return
            if (this.uploadsReady && !this.form.isFieldsTouched() && JSON.stringify(this.model) === this.initialModel) {
                this.close()
                return
            }
            const version = this.saveVersion
            this.discardPromptOpen = true
            this.$confirm({
                title: '放弃未保存的修改？',
                content: '关闭后，本次填写但尚未保存的内容将丢失。',
                okText: '放弃修改',
                cancelText: '继续编辑',
                onOk: () => {
                    this.discardPromptOpen = false
                    if (version === this.saveVersion) this.close()
                },
                onCancel: () => { this.discardPromptOpen = false }
            })
        },
        handleOk () {
            if (!this.visible || this.confirmLoading || this.discardPromptOpen) return
            if (!this.uploadsReady) {
                this.saveError = '附件尚未准备好，请等待上传和登记完成，或重试、移除失败文件后保存。'
                return
            }
            const version = ++this.saveVersion
            this.confirmLoading = true
            this.saveError = ''
            // Lock before validation too: asynchronous validators must not enqueue two writes.
            this.form.validateFields(async (err, values) => {
                if (version !== this.saveVersion || !this.visible) return
                if (err) {
                    this.confirmLoading = false
                    return
                }
                if (!this.uploadsReady) {
                    this.confirmLoading = false
                    this.saveError = '附件尚未准备好，请完成上传后保存。'
                    return
                }
                const payload = Object.assign({}, this.model, values)
                try {
                    const result = await httpAction(payload.id ? this.url.edit : this.url.add, payload, payload.id ? 'put' : 'post')
                    if (version !== this.saveVersion || !this.visible) return
                    if (!result || result.success !== true) {
                        this.saveError = '保存未成功，填写内容已保留。请检查填写内容和当前账号权限后重试。'
                        return
                    }
                    this.confirmLoading = false
                    this.$message.success('保存成功')
                    this.close()
                    this.$emit('ok')
                } catch (error) {
                    if (version === this.saveVersion && this.visible) {
                        this.saveError = '未能确认保存结果，填写内容已保留。请先核对列表中的记录，再决定是否重试，避免重复新建。'
                    }
                } finally {
                    if (version === this.saveVersion) this.confirmLoading = false
                }
            })
        }
    }
}
