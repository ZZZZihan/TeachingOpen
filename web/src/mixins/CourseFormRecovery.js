import { httpAction } from '@/api/manage'

// Shared by the course and unit dialogs. Server writes are never retried automatically.
export default {
    data () {
        return { saveError: '', saveVersion: 0, initialModel: '', discardPromptOpen: false }
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
    },
    methods: {
        beginEdit (record) {
            if (this.confirmLoading) return false
            this.saveVersion += 1
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
            this.visible = false
            this.$emit('close')
        },
        handleCancel () {
            if (this.confirmLoading || !this.visible || this.discardPromptOpen) return
            if (!this.form.isFieldsTouched() && JSON.stringify(this.model) === this.initialModel) {
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
