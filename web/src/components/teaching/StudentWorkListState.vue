<template>
  <div v-if="loading || error || empty" class="student-list-state">
    <div v-if="loading" role="status" aria-live="polite" data-testid="work-list-loading">
      <a-icon type="loading" aria-hidden="true" /><h3>正在读取作品</h3>
      <p>{{ keepQuery ? '请稍候，本次查询条件和页码已保留。' : '请稍候，正在获取你的作品。' }}</p>
    </div>
    <div v-else-if="error" role="alert" data-testid="work-list-error">
      <h3>作品列表暂不可用</h3><p>{{ error }}</p>
      <p v-if="keepQuery">重试将使用刚才已发送的查询条件和页码。</p>
      <button type="button" class="student-list-retry" data-testid="work-list-retry" @click="$emit('retry')">重新加载</button>
    </div>
    <div v-else role="status" aria-live="polite" data-testid="work-list-empty">
      <h3>{{ emptyPage ? '当前页暂无作品' : keepQuery ? '没有符合当前查询的作品' : '还没有作品' }}</h3>
      <p>{{ emptyPage ? '可以切换页码，或修改条件后重新查询。' : keepQuery ? '可以修改查询条件后再查询。' : '创作并保存作品后，会在这里显示。' }}</p>
    </div>
  </div>
</template>

<script>
export default {
    name: 'StudentWorkListState',
    props: { loading: Boolean, error: { type: String, default: '' }, empty: Boolean, emptyPage: Boolean, keepQuery: Boolean }
}
</script>

<style scoped>
.student-list-state { min-width: 0; padding: 32px 20px; text-align: center; border: 1px solid #e1e4e8; border-radius: 3px; background: #fafafb; color: #59646e; overflow-wrap: anywhere; }
.student-list-state h3 { margin: 10px 0 8px; color: #20252b; font-size: 16px; font-weight: 500; }
.student-list-state p { font-size: 13px; line-height: 1.8; margin: 0 0 8px; }
.student-list-state .anticon { color: #146fc2; font-size: 22px; }
.student-list-retry { min-height: 44px; margin-top: 12px; padding: 8px 20px; border: 1px solid #146fc2; border-radius: 3px; background: #146fc2; color: #fff; font: inherit; font-size: 14px; cursor: pointer; }
.student-list-retry:focus-visible { outline: 2px solid #146fc2; outline-offset: 3px; }
@media (max-width: 600px) { .student-list-state { padding: 24px 16px; } }
</style>
