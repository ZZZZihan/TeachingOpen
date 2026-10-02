<template>
  <j-modal
    :visible="visible"
    :title="unit.unitName || '课程学习'"
    :width="1040"
    :footer="null"
    :maskClosable="false"
    wrapClassName="learning-reader-modal"
    switchFullscreen
    @cancel="handleCancel">
    <div v-if="visible" class="unit-reader">
      <div class="reader-main">
        <nav v-if="tabs.length" class="reader-tabs" aria-label="单元内容">
          <button v-for="tab in tabs" :key="tab.key" type="button" :aria-pressed="String(activeTab === tab.key)" @click="selectTab(tab.key)">{{ tab.label }}</button>
        </nav>
        <section v-if="activeTab === 'video'" class="reader-media" aria-label="课程视频">
          <template v-if="Number(unit.courseVideoSource) === 3">
            <div :key="mediaVersion" class="reader-rich" v-html="unit.courseVideo"></div>
            <button class="reader-reload" type="button" @click="retryMedia">嵌入内容未显示？重新加载</button>
          </template>
          <template v-else>
            <video
              v-if="videoUrl && videoState !== 'error'"
              :key="mediaVersion"
              ref="video"
              :src="videoUrl"
              :data-media-version="mediaVersion"
              :aria-label="unit.unitName + '课程视频'"
              controls
              playsinline
              preload="metadata"
              @loadedmetadata="setVideoState($event, 'ready')"
              @error="setVideoState($event, 'error')"></video>
            <p v-if="videoUrl && videoState === 'loading'" class="reader-status" role="status">正在加载视频，可使用播放器开始观看。</p>
            <div v-if="!videoUrl || videoState === 'error'" class="reader-message" role="alert"><h3>视频暂时无法播放</h3><p>{{ videoUrl ? '请检查网络后重试。若仍无法播放，可能是资源已失效或当前浏览器不支持此格式。' : '这节课还没有有效的视频地址，请联系老师。' }}</p><button v-if="videoUrl" class="reader-primary" type="button" @click="retryMedia">重新加载视频</button></div>
          </template>
        </section>
        <section v-else-if="activeTab === 'case'" class="reader-media" aria-label="课程案例">
          <template v-if="caseUrl">
            <div class="reader-case-shell" :class="{ 'reader-case-tall': Number(unit.courseWorkType) > 2 }">
              <iframe
                :key="mediaVersion"
                ref="caseFrame"
                class="reader-case"
                :src="caseUrl"
                :title="unit.unitName + '课程案例'"
                allowfullscreen
                @load="handleScratchInit"></iframe>
            </div>
            <button class="reader-reload" type="button" @click="retryMedia">案例未正常显示？重新加载</button>
          </template>
          <div v-else class="reader-message"><h3>案例暂时无法打开</h3><p>请联系老师确认案例类型与文件地址。</p></div>
        </section>
        <section v-else-if="activeTab === 'content'" class="reader-rich reader-content" aria-label="课程内容" v-html="unit.mediaContent"></section>
        <div v-else class="reader-message"><h3>本单元暂无视频或在线内容</h3><p>可以先阅读课程说明，查看已提供的资料与练习。</p></div>
        <section class="reader-description" aria-labelledby="unit-description-title"><p class="reader-eyebrow">ABOUT THIS LESSON</p><h2 id="unit-description-title">课程说明</h2><div v-if="unit.unitIntro" class="reader-rich" v-html="String(unit.unitIntro).replace(/\n/g, '<br>')"></div><p v-else class="reader-muted">老师尚未添加这节课的说明。</p></section>
        <p v-if="logFailed" class="reader-record-note" role="status">本次学习记录暂未同步，仍可继续查看课程内容。</p>
      </div>
      <aside class="reader-sidebar" aria-label="学习资料与练习">
        <section v-if="unit.courseWork_url" class="reader-practice"><p class="reader-eyebrow">PRACTICE</p><h2>把想法付诸实践</h2><p>打开本节课的练习，在动手中巩固所学。</p><a v-if="workUrl" class="reader-primary" :href="workUrl" target="_blank" rel="noopener noreferrer">开始练习 <span aria-hidden="true">↗</span></a><p v-else class="reader-muted">练习地址尚未配置，请联系老师。</p></section>
        <section class="reader-resources"><h2>学习资料</h2><p v-if="!resources.length" class="reader-muted">本单元暂未提供附加资料。</p><ul v-else><li v-for="resource in resources" :key="resource.key"><span class="reader-resource-kind">{{ resource.kind }}</span><a v-if="resource.url" :href="resource.url" target="_blank" rel="noopener noreferrer">{{ resource.name }} <span aria-hidden="true">↗</span></a><p v-else>{{ resource.name }}<br><span class="reader-muted">地址不可用，请联系老师。</span></p></li></ul><p v-if="resources.length" class="reader-resource-help">资料在新标签页打开。无法查看时，请联系老师确认文件与访问权限。</p></section>
      </aside>
    </div>
  </j-modal>
</template>
<script>
import { getFileAccessHttpUrl, getAction, getFilePrevew } from '@/api/manage'
export default {
    name: 'UnitViewModal',
    data () {
        return { visible: false, unit: {}, activeTab: '', videoState: 'loading', mediaVersion: 0, viewVersion: 0, logFailed: false, frameClickTarget: null }
    },
    computed: {
        tabs () {
            return [{ key: 'video', label: '视频', show: this.unit.courseVideo }, { key: 'case', label: '案例', show: this.unit.courseCase }, { key: 'content', label: '课程内容', show: this.unit.mediaContent }].filter(tab => tab.show)
        },
        videoUrl () { return this.safeUrl(Number(this.unit.courseVideoSource) === 1 ? this.unit.courseVideo_url : this.unit.courseVideo) },
        caseUrl () {
            const url = this.safeUrl(this.getFileAccessHttpUrl(this.unit.courseCase))
            if (!url) return ''
            switch (Number(this.unit.courseWorkType)) {
            case 1: case 2: return this.withQuery('/scratch3/player.html', { workUrl: url })
            case 3: return this.withQuery('/scratchjr/editor.html', { mode: 'edit', workFile: url })
            case 4: return this.withQuery('/python/player.html', { lang: 'turtle', url })
            default: return ''
            }
        },
        workUrl () {
            if (!this.unit.courseWork_url || !this.unit.id) return ''
            const file = this.safeUrl(this.getFileAccessHttpUrl(this.unit.courseWork) || this.unit.courseWork_url)
            switch (Number(this.unit.courseWorkType)) {
            case 1: case 2: return this.withQuery('/scratch3/index.html', { scene: 'course', unitId: this.unit.id })
            case 3: return file ? this.withQuery('/scratchjr/editor.html', { scene: 'course', mode: 'edit', unitId: this.unit.id, workFile: file }) : ''
            case 4: return file ? this.withQuery('/python/index.html', { scene: 'course', lang: 'turtle', unitId: this.unit.id, url: file }) : ''
            default: return this.safeUrl(this.getFileAccessHttpUrl(this.unit.mediaPath) || this.unit.courseWork_url)
            }
        },
        resources () {
            const items = []
            for (const [field, kind] of [['coursePpt', '课程资料'], ['coursePlan', '课程教案']]) {
                String(this.unit[field] || '').split(',').map(value => value.trim()).filter(Boolean).forEach((value, index) => {
                    let url = ''
                    try {
                        const path = value.split(/[?#]/)[0]
                        url = /\.sb3$/i.test(path) ? this.withQuery('/scratch3/index.html', { scene: 'create', workFile: value }) : this.safeUrl(getFilePrevew(value))
                    } catch (error) { /* A broken preview configuration must not prevent reading the lesson. */ }
                    items.push({ key: field + '-' + index, kind, name: kind + ' ' + (index + 1), url })
                })
            }
            return items
        }
    },
    mounted () {
        document.addEventListener('scratchFullScreen', this.handleScratchFullscreen)
        document.addEventListener('scratchUnFullScreen', this.handleScratchExit)
        document.addEventListener('scratchInit', this.handleScratchInit)
    },
    deactivated () { this.handleCancel() },
    beforeDestroy () {
        this.handleCancel()
        document.removeEventListener('scratchFullScreen', this.handleScratchFullscreen)
        document.removeEventListener('scratchUnFullScreen', this.handleScratchExit)
        document.removeEventListener('scratchInit', this.handleScratchInit)
    },
    methods: {
        getFileAccessHttpUrl,
        safeUrl (value) {
            if (typeof value !== 'string' || !value.trim()) return ''
            try {
                const url = new URL(value, window.location.origin)
                return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
            } catch (error) { return '' }
        },
        withQuery (path, params) { return path + '?' + new URLSearchParams({ ...params, queryEncoding: 'uri' }).toString() },
        setVideoState (event, state) {
            if (event.target && event.target.dataset.mediaVersion === String(this.mediaVersion)) this.videoState = state
        },
        view (unit) {
            this.stopMedia()
            this.unit = unit
            this.activeTab = this.tabs.length ? this.tabs[0].key : ''
            this.visible = true
            this.logFailed = false
            this.videoState = 'loading'
            this.mediaVersion += 1
            const version = ++this.viewVersion
            getAction('/teaching/teachingDepartDayLog/unitViewLog', { unitId: unit.id }).then(res => {
                if (version === this.viewVersion && this.visible && !res.success) this.logFailed = true
            }).catch(() => {
                if (version === this.viewVersion && this.visible) this.logFailed = true
            })
        },
        selectTab (key) {
            if (this.activeTab === key) return
            this.stopMedia()
            this.activeTab = key
            this.videoState = 'loading'
            this.mediaVersion += 1
        },
        retryMedia () { this.stopMedia(); this.videoState = 'loading'; this.mediaVersion += 1 },
        handleCancel () {
            this.stopMedia()
            this.visible = false
            this.unit = {}
            this.activeTab = ''
            this.viewVersion += 1
        },
        stopMedia () {
            if (this.$refs.video) {
                this.$refs.video.pause()
                this.$refs.video.removeAttribute('src')
                this.$refs.video.load()
            }
            this.detachFrameClick()
            this.handleScratchExit()
            if (this.$refs.caseFrame) this.$refs.caseFrame.src = 'about:blank'
        },
        detachFrameClick () {
            if (this.frameClickTarget) this.frameClickTarget.removeEventListener('click', this.focusCase)
            this.frameClickTarget = null
        },
        focusCase () { if (this.$refs.caseFrame) this.$refs.caseFrame.focus() },
        handleScratchInit () {
            if (!this.visible || this.activeTab !== 'case' || !this.$refs.caseFrame) return
            this.detachFrameClick()
            try {
                const doc = this.$refs.caseFrame.contentDocument
                const target = doc && doc.getElementById('scratch')
                if (target) { this.frameClickTarget = target; target.addEventListener('click', this.focusCase) }
            } catch (error) { /* Cross-origin case pages do not expose their document. */ }
        },
        handleScratchFullscreen () {
            const frame = this.$refs.caseFrame
            if (!this.visible || this.activeTab !== 'case' || !frame) return
            const request = frame.requestFullscreen || frame.webkitRequestFullscreen
            if (request) { const result = request.call(frame); if (result && result.catch) result.catch(() => {}) }
        },
        handleScratchExit () {
            const current = document.fullscreenElement || document.webkitFullscreenElement
            if (!current || current !== this.$refs.caseFrame) return
            const exit = document.exitFullscreen || document.webkitExitFullscreen
            if (exit) { const result = exit.call(document); if (result && result.catch) result.catch(() => {}) }
        }
    }
}
</script>
<style lang="less">
.learning-reader-modal {
  .ant-modal { top: 36px; max-width: calc(100vw - 32px); }
  .ant-modal-content { border-radius: 5px; overflow: hidden; }
  .ant-modal-header { padding: 22px 28px; border-bottom: 1px solid #e0e6e9; }
  .ant-modal-title { color: #172d38; font-size: 20px; font-weight: 600; line-height: 1.5; }
  .ant-modal-body { padding: 0; }
  .unit-reader { display: grid; grid-template-columns: minmax(0, 1fr) 264px; color: #172d38; }
  .reader-main { padding: 0 28px 28px; min-width: 0; }
  .reader-tabs { display: flex; gap: 24px; border-bottom: 1px solid #e0e6e9; margin-bottom: 24px; }
  .reader-tabs button { padding: 20px 0 16px; border: 0; border-bottom: 2px solid transparent; background: none; color: #637680; font: inherit; cursor: pointer; }
  .reader-tabs button[aria-pressed='true'] { color: #a73542; border-bottom-color: #b63e4b; font-weight: 600; }
  .reader-media video { display: block; width: 100%; max-height: 520px; aspect-ratio: 16/9; background: #152730; }
  .reader-case-shell { position: relative; width: 100%; aspect-ratio: 4/3; padding-top: 48px; box-sizing: content-box; }
  .reader-case-tall { min-height: 500px; }
  .reader-case { position: absolute; inset: 0; display: block; width: 100%; height: 100%; border: 0; background: #f5f7f7; }
  .reader-rich { color: #465e6a; line-height: 1.9; overflow-wrap: anywhere; overflow-x: auto; }
  .reader-rich img, .reader-rich video, .reader-rich iframe { max-width: 100%; }
  .reader-rich img { height: auto; }
  .reader-rich p:last-child { margin-bottom: 0; }
  .reader-content { padding: 4px 0 12px; }
  .reader-description { margin-top: 28px; padding-top: 24px; border-top: 1px solid #e0e6e9; }
  .reader-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: 1.1px; color: #86545e; margin: 0 0 10px; }
  h2 { color: #172d38; font-size: 18px; font-weight: 600; margin: 0 0 14px; }
  .reader-muted { color: #687b86; font-size: 13px; line-height: 1.9; }
  .reader-sidebar { background: #f5f7f7; border-left: 1px solid #e0e6e9; padding: 28px 24px; min-width: 0; }
  .reader-practice { padding-bottom: 28px; margin-bottom: 26px; border-bottom: 1px solid #dce3e6; }
  .reader-practice > p:not(.reader-eyebrow) { color: #627680; font-size: 13px; line-height: 1.9; margin-bottom: 20px; }
  .reader-primary { display: inline-flex; gap: 24px; justify-content: center; align-items: center; border: 1px solid #b63e4b; border-radius: 3px; background: #b63e4b; color: #fff; padding: 11px 18px; min-height: 44px; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
  .reader-primary:hover { background: #9d3340; color: #fff; }
  .reader-resources ul { list-style: none; padding: 0; margin: 0; }
  .reader-resources li { padding: 14px 0; border-bottom: 1px solid #e0e6e9; overflow-wrap: anywhere; }
  .reader-resources li a { display: block; color: #344f5e; font-size: 13px; }
  .reader-resource-kind { display: block; color: #6c7e87; font-size: 10px; margin-bottom: 6px; }
  .reader-resource-help, .reader-record-note { margin: 20px 0 0; color: #687b86; font-size: 11px; line-height: 1.8; }
  .reader-reload { display: block; border: 0; padding: 12px 0 0; background: transparent; color: #657983; font: inherit; font-size: 11px; cursor: pointer; }
  .reader-message { text-align: center; background: #f5f7f7; padding: 36px 24px; color: #637680; font-size: 13px; line-height: 1.9; }
  .reader-message h3 { color: #172d38; font-size: 18px; margin-bottom: 10px; }
  .reader-status { color: #687b86; font-size: 12px; margin: 12px 0 0; }
  .unit-reader a:focus-visible, .unit-reader button:focus-visible { outline: 2px solid #b63e4b; outline-offset: 4px; }
  @media (max-width: 760px) { .unit-reader { grid-template-columns: minmax(0, 1fr); } .reader-sidebar { border-left: 0; border-top: 1px solid #e0e6e9; } .reader-practice { margin-bottom: 20px; padding-bottom: 20px; } }
  @media (max-width: 480px) { .ant-modal { top: 12px; max-width: calc(100vw - 16px); } .ant-modal-header { padding: 18px; } .ant-modal-title { font-size: 17px; } .reader-main { padding: 0 18px 24px; } .reader-tabs { gap: 22px; margin-bottom: 18px; } .reader-sidebar { padding: 24px 18px; } }
}
</style>
