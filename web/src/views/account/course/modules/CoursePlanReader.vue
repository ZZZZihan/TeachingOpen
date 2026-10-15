<template>
  <section class="course-plan-reader" :aria-label="title" :aria-busy="String(status === 'loading')">
    <p v-if="status === 'loading'" class="reader-status" role="status">正在加载教案…</p>
    <div v-else-if="status === 'error'" class="reader-message" role="alert"><h3>教案暂时无法显示</h3><p>{{ error }}</p><button class="reader-primary" type="button" @click="load">重新加载教案</button></div>
    <p v-else-if="!document || !document.content" class="reader-muted">这份教案还没有正文，请联系老师补充。</p>
    <article v-else-if="document.type === 'html'" class="plan-document reader-rich" v-html="document.content"></article>
    <pre v-else-if="document.type === 'text'" class="plan-text">{{ document.content }}</pre>
    <iframe v-else-if="document.type === 'pdf'" class="plan-pdf" :src="objectUrl" :title="title"></iframe>
    <img v-else-if="document.type === 'image'" class="plan-image" :src="objectUrl" :alt="title">
  </section>
</template>
<script>
import { loadCoursePlan } from '@/utils/coursePlan'

export default {
    name: 'CoursePlanReader',
    props: {
        url: { type: String, default: '' },
        title: { type: String, default: '课程教案' }
    },
    data () {
        return { status: 'loading', error: '', document: null, objectUrl: '', requestVersion: 0, controller: null, timeout: null }
    },
    watch: { url: { immediate: true, handler () { this.load() } } },
    beforeDestroy () { this.dispose() },
    methods: {
        clear () {
            if (this.objectUrl) URL.revokeObjectURL(this.objectUrl)
            this.objectUrl = ''
            this.document = null
        },
        dispose () {
            this.requestVersion += 1
            if (this.controller) this.controller.abort()
            this.controller = null
            clearTimeout(this.timeout)
            this.timeout = null
            this.clear()
        },
        async load () {
            this.dispose()
            const version = this.requestVersion
            this.status = 'loading'
            this.error = ''
            this.controller = new AbortController()
            this.timeout = setTimeout(() => {
                if (version !== this.requestVersion) return
                this.dispose()
                this.status = 'error'
                this.error = '教案加载超时，请检查网络后重试。'
            }, 20000)
            try {
                const result = await loadCoursePlan(this.url, { signal: this.controller.signal })
                if (version !== this.requestVersion) return
                this.document = result
                if (['pdf', 'image'].includes(result.type)) this.objectUrl = URL.createObjectURL(result.content)
                this.status = 'ready'
            } catch (error) {
                if (version !== this.requestVersion) return
                this.status = 'error'
                this.error = error instanceof TypeError ? '教案加载失败，请检查网络或联系老师确认文件可访问后重试。' : error.message || '教案加载失败，请稍后重试。'
            } finally {
                if (version === this.requestVersion) { clearTimeout(this.timeout); this.timeout = null }
            }
        }
    }
}
</script>
<style lang="less">
.learning-reader-modal {
  .course-plan-reader { min-height: 160px; }
  .plan-document { color: #344f5e; font-size: 15px; }
  .plan-document h1 { font-size: 24px; line-height: 1.5; }
  .plan-document h2 { font-size: 20px; margin: 26px 0 14px; }
  .plan-document h3 { font-size: 17px; margin: 22px 0 12px; }
  .plan-document pre, .plan-text { padding: 16px; border-radius: 4px; background: #f5f7f7; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; }
  .plan-document code { font-size: 13px; }
  .plan-document table { border-collapse: collapse; width: 100%; margin: 16px 0; }
  .plan-document th, .plan-document td { border: 1px solid #dce3e6; padding: 8px 10px; min-width: 80px; }
  .plan-document th { background: #f5f7f7; }
  .plan-document blockquote { border-left: 3px solid #b63e4b; padding-left: 16px; color: #637680; }
  .plan-pdf { width: 100%; height: 65vh; min-height: 400px; border: 1px solid #e0e6e9; }
  .plan-image { display: block; max-width: 100%; height: auto; margin: auto; }
}
</style>
