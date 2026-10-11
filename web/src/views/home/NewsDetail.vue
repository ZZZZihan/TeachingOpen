<template>
  <div class="cms" :aria-busy="String(loading)">
    <div v-if="loading" class="cms-state" role="status"><a-spin />正在加载资讯…</div>
    <div v-else-if="error" class="cms-state" role="alert">
      <p>资讯暂时无法加载，请重试。</p>
      <a-button @click="getCmsDetail">重新加载资讯</a-button>
    </div>
    <div v-else-if="!cmsInfo" class="cms-state" role="status">未找到这篇资讯，可能已下线。</div>
    <template v-else>
      <div class="cms-header">
        <h1>{{ cmsInfo.newsTitle }}</h1>
        <div class="cms-info">
          <span class="gap">本文发布于：{{ cmsInfo.createTime }}</span>
        </div>
      </div>
      <a-divider></a-divider>
      <div class="article-content" v-html="safeContent"></div>
    </template>
  </div>
</template>

<script>
import { getAction } from "@/api/manage";
import { sanitizeRichText } from '@/utils/richText'

export default {
  data() {
    return {
      cmsInfo: null,
      loading: false,
      error: false,
      requestId: 0,
    };
  },
  computed: {
    safeContent() { return sanitizeRichText(this.cmsInfo && this.cmsInfo.newsContent) }
  },
  watch: {
    '$route.query.id'() {
      this.getCmsDetail()
    },
  },
  created() {
    this.getCmsDetail()
  },
  beforeDestroy() {
    this.requestId += 1
  },
  methods:{
    getCmsDetail(){
      const requestId = ++this.requestId
      const id = this.$route.query.id
      this.cmsInfo = null
      this.error = false
      this.loading = false
      if (typeof id !== 'string' || !id.trim()) return
      this.loading = true
      return getAction('/teaching/teachingNews/newsDetail', { id }).then(res => {
        if (requestId !== this.requestId) return
        if (!res || !res.success) throw new Error('News detail unavailable')
        const article = res.result
        if (article == null || (typeof article === 'object' && !Array.isArray(article) && !Object.keys(article).length)) return
        if (typeof article !== 'object' || Array.isArray(article) || article.id !== id || typeof article.newsTitle !== 'string'
          || (article.newsContent != null && typeof article.newsContent !== 'string')) {
          throw new Error('Invalid news detail')
        }
        this.cmsInfo = article
      }).catch(() => {
        if (requestId === this.requestId) this.error = true
      }).finally(() => {
        if (requestId === this.requestId) this.loading = false
      })
    }
  }
};
</script>

<style scoped lang="less">
.cms{
  border-radius: 10px;
  background: white;
  padding: 20px 0;
  margin: 20px 0;
  box-shadow:#c5c0c0 0px 0px 10px;
  min-height: 80vh;
}
.cms-header {
  margin-top: 20px;
  text-align: center;
  h1{
    margin: 0 50px;
  }
  .cms-info {
    color: gray;
  }
}
.cms-state {
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 16px;
  padding: 60px 24px;
  text-align: center;
}

.gap {
  margin-left: 5px;
  margin-right: 20px;
  font-size: 14px;
}
.article-content {
  overflow: auto;
  padding: 20px 100px;
  /deep/img {
    max-width: 100%;
    height: auto;
  }
}
.extra-file{
  padding: 20px 100px;
}
</style>
