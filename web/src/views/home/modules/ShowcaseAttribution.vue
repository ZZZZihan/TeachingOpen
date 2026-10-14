<template>
  <aside v-if="source" class="showcase-attribution" aria-label="作品来源与署名">
    <div class="source-heading">开放学习示例 · 来源与署名</div>
    <p><strong>原作者</strong> {{ source.author }}</p>
    <p class="source-links">
      <a :href="source.sourceUrl" target="_blank" rel="noopener noreferrer">查看原作 / 教程 ↗</a>
      <a :href="source.licenseUrl" target="_blank" rel="noopener noreferrer">{{ source.license }}</a>
    </p>
    <p class="adaptation">{{ source.adaptation }}</p>
  </aside>
</template>

<script>
import { getShowcaseAttribution } from '@/utils/showcaseAttribution'

export default {
    name: 'ShowcaseAttribution',
    props: {
        work: { type: Object, required: true }
    },
    computed: {
        source () {
            return getShowcaseAttribution(this.work)
        }
    }
}
</script>

<style scoped>
.showcase-attribution {
  margin: 8px 0 24px;
  padding: 18px 20px;
  border: 1px solid #dbe5f0;
  border-radius: 12px;
  background: #f5f9fd;
  color: #334155;
  overflow-wrap: anywhere;
}
.source-heading { margin-bottom: 12px; color: #0f4c81; font-weight: 600; }
.showcase-attribution p { margin: 8px 0; line-height: 1.7; }
.showcase-attribution strong { margin-right: 8px; }
.source-links { display: flex; flex-wrap: wrap; gap: 8px 24px; }
.source-links a { color: #155b97; text-decoration: underline; }
.adaptation { font-size: 13px; color: #59697e; }
</style>
