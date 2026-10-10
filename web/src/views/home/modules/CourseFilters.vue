<template>
  <div class="course-filters">
    <h2 class="filters-title">筛选课程</h2>
    <form class="filter-form" aria-label="筛选课程" @submit.prevent="$emit('search', draftName.trim())">
      <div class="filter-field">
        <label for="course-category">课程分类</label>
        <select id="course-category" :value="courseCategory" :disabled="loadingOptions || !!optionErrors.category" @change="$emit('category', $event.target.value)">
          <option value="">全部分类</option>
          <option v-for="option in categoryOptions" :key="option.value" :value="option.value">{{ option.text }}</option>
        </select>
      </div>
      <div class="filter-field">
        <label for="course-type">课程性质</label>
        <select id="course-type" :value="courseType" :disabled="loadingOptions || !!optionErrors.type" @change="$emit('type', $event.target.value)">
          <option value="">全部性质</option>
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">{{ option.text }}</option>
        </select>
      </div>
      <div class="filter-field search-field">
        <label for="course-name">课程名称</label>
        <div class="search-input">
          <input id="course-name" v-model="draftName" type="search" placeholder="搜索感兴趣的课程" />
          <button class="search-button" type="submit"><a-icon type="search" /> 搜索</button>
        </div>
      </div>
      <button class="reset-button" type="button" @click="reset">重置筛选</button>
    </form>
    <div v-if="optionErrors.category || optionErrors.type" class="filter-error" role="status">
      部分筛选选项加载失败，仍可按名称搜索。
      <button type="button" :disabled="loadingOptions" @click="loadOptions">{{ loadingOptions ? '正在重试…' : '重试选项' }}</button>
    </div>
  </div>
</template>
<script>
import { ajaxGetDictItems } from '@/api/api'
export default {
    props: {
        courseCategory: { type: String, default: '' },
        courseType: { type: String, default: '' },
        courseName: { type: String, default: '' }
    },
    data () {
        return { draftName: this.courseName, categoryOptions: [], typeOptions: [], optionErrors: {}, loadingOptions: false, requestId: 0 }
    },
    watch: {
        courseName (value) { this.draftName = value }
    },
    created () { this.loadOptions() },
    beforeDestroy () { this.requestId += 1 },
    methods: {
        reset () {
            this.draftName = ''
            this.$emit('reset')
        },
        loadOptions () {
            if (this.loadingOptions) return
            const requestId = ++this.requestId
            this.loadingOptions = true
            return Promise.all(['category', 'type'].map(kind => {
                return ajaxGetDictItems('course_' + kind, null).then(response => {
                    if (requestId !== this.requestId) return
                    if (!response || !response.success || !Array.isArray(response.result) ||
                        response.result.some(item => !item || item.value == null || typeof item.text !== 'string')) {
                        throw new Error('Invalid course filter options')
                    }
                    this[kind + 'Options'] = response.result.map(item => ({ value: String(item.value), text: item.text }))
                    this.$set(this.optionErrors, kind, false)
                }).catch(() => {
                    if (requestId === this.requestId) this.$set(this.optionErrors, kind, true)
                })
            })).finally(() => {
                if (requestId === this.requestId) this.loadingOptions = false
            })
        }
    }
}
</script>
<style scoped lang="less">
.course-filters { padding: 0; }
.filters-title { color: #202c37; font-size: 15px; font-weight: 600; margin: 3px 0 26px; }
.filter-form { display: flex; flex-direction: column; gap: 24px; }
.filter-field { min-width: 0; width: 100%; }
.filter-field label { display: block; color: #5b6874; font-size: 12px; font-weight: 500; margin-bottom: 10px; }
.filter-field select, .filter-field input { width: 100%; min-width: 0; height: 42px; border: 1px solid #d8dfe5; border-radius: 4px; background: #fff; padding: 0 10px; color: #394754; font: inherit; font-size: 12px; }
.filter-field select:disabled { background: #f1f3f5; color: #7b879b; cursor: not-allowed; }
.search-input { display: flex; }
.search-input input { border-radius: 4px 0 0 4px; }
.search-button { flex-shrink: 0; height: 42px; padding: 0 12px; border: 1px solid #74256a; border-radius: 0 4px 4px 0; background: #74256a; color: #fff; cursor: pointer; font-size: 12px; }
.search-button:hover { background: #592052; }
.reset-button { align-self: flex-start; padding: 0 0 3px; border: 0; border-bottom: 1px solid #bdc5cc; background: transparent; color: #687684; cursor: pointer; white-space: nowrap; font-size: 12px; }
.reset-button:hover, .filter-error button:hover { color: #74256a; }
.filter-error { margin-top: 16px; color: #80561c; font-size: 12px; line-height: 1.8; }
.filter-error button { border: 0; background: transparent; color: #74256a; text-decoration: underline; cursor: pointer; }
input:focus-visible, select:focus-visible, button:focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
@media (max-width: 1000px) { .course-filters { padding-bottom: 26px; border-bottom: 1px solid #dfe4e9; } .filters-title { display: none; } .filter-form { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: end; } .search-field { grid-column: 1; } .reset-button { align-self: center; justify-self: start; margin-top: 24px; } }
@media (max-width: 600px) { .filter-form { gap: 18px 14px; } .search-field { grid-column: span 2; } .reset-button { margin-top: 0; } }
</style>
