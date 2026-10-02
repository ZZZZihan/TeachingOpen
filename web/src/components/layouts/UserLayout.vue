<template>
  <div id="userLayout" class="user-layout-wrapper">
    <header class="user-header"><router-link to="/index" class="brand"><img v-if="logoUrl && !logoFailed" :src="logoUrl" alt="" @error="logoFailed = true"><span v-else class="brand-symbol" aria-hidden="true">T<span>•</span></span><span>{{ brandName }}</span></router-link><router-link to="/courseList" class="header-link">探索课程 <span aria-hidden="true">↗</span></router-link></header>
    <main :class="['user-content', { 'compact-form': !widePage }]"><route-view /></main>
    <footer class="user-footer"><div v-if="config.footer" v-html="config.footer"></div><span v-else>{{ brandName }} · 学习与创作</span></footer>
  </div>
</template>

<script>
import RouteView from '@/components/layouts/RouteView'
import { getFileAccessHttpUrl } from '@/api/manage'
export default {
    name: 'UserLayout',
    components: { RouteView },
    data () { return { logoFailed: false } },
    computed: {
        config () { return this.$store.state.user.sysConfig || {} },
        brandName () { return this.config.brandName || 'TeachingOpen' },
        logoUrl () { return this.config.logo ? getFileAccessHttpUrl(this.config.logo) : '' },
        widePage () { return this.$route.name === 'login' }
    },
    watch: { logoUrl () { this.logoFailed = false } },
    mounted () { document.body.classList.add('userLayout') },
    beforeDestroy () { document.body.classList.remove('userLayout') }
}
</script>

<style lang="less" scoped>
.user-layout-wrapper { min-height: 100vh; background: #f5f6f7; color: #20252b; display: flex; flex-direction: column; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.user-header { height: 84px; padding: 0 max(32px, calc((100% - 1120px) / 2)); display: flex; align-items: center; justify-content: space-between; gap: 20px; background: #fff; border-bottom: 1px solid #e1e4e8; flex-shrink: 0; }
.brand { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 600; color: #20252b; min-width: 0; overflow-wrap: anywhere; line-height: 1.3; }
.brand img { width: 36px; height: 36px; object-fit: contain; }
.brand-symbol { font-size: 31px; font-weight: 700; letter-spacing: -4px; padding-right: 4px; flex-shrink: 0; }
.brand-symbol span { color: #c84a55; }
.header-link { flex-shrink: 0; color: #59646e; font-size: 13px; }
.header-link span { margin-left: 12px; }
a:focus-visible { outline: 2px solid #9b3844; outline-offset: 4px; }
.user-content { padding: 48px 32px 32px; flex: 1; }
.compact-form { width: 100%; max-width: 500px; margin: 48px auto 0; padding: 32px; background: #fff; flex: 0 0 auto; }
.compact-form /deep/ .main { width: 100%; min-width: 0; margin: 0; }
.user-footer { text-align: center; padding: 24px; margin-top: auto; color: #737b82; font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 680px) { .user-header { height: 68px; padding: 0 24px; } .brand { font-size: 17px; } .header-link { font-size: 12px; } .header-link span { display: none; } .user-content { padding: 0; } .compact-form { margin: 24px auto 0; padding: 24px; } .user-footer { padding: 24px 16px; } }
</style>
