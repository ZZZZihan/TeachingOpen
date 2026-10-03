<template>
  <header class="public-header">
    <CampusMasthead />
    <div class="header-inner">
      <router-link class="brand" to="/index" :aria-label="brandName + '首页'">
        <img v-if="logoUrl && !logoFailed" class="brand-logo" :src="logoUrl" alt="" @error="logoFailed = true" />
        <span v-else class="brand-mark" aria-hidden="true">天工</span>
        <span class="brand-name">{{ brandName }}</span>
      </router-link>
      <button
        class="menu-toggle"
        type="button"
        :aria-expanded="String(menuOpen)"
        aria-controls="public-navigation"
        :aria-label="menuOpen ? '收起导航' : '展开导航'"
        @click="menuOpen = !menuOpen">
        <a-icon :type="menuOpen ? 'close' : 'menu'" />
      </button>
      <nav id="public-navigation" :class="['header-nav', { 'is-open': menuOpen }]" aria-label="主要导航">
        <t-menu v-if="menus.length" class="configured-menu" :mode="compact ? 'inline' : 'horizontal'" :menu="menus" />
        <div v-else class="default-menu">
          <router-link to="/index" active-class="is-active">首页</router-link>
          <router-link to="/courseList" active-class="is-active">探索课程</router-link>
          <router-link to="/home" active-class="is-active">创作社区</router-link>
        </div>
      </nav>
      <div class="account-actions">
        <template v-if="isLoggedIn">
          <router-link class="account-link" to="/account/center" :title="accountName">
            <a-icon type="user" /> <span>{{ accountName }}</span>
          </router-link>
          <button class="logout-button" type="button" @click="handleLogout">退出</button>
        </template>
        <router-link v-else class="login-link" to="/user/login">登录学习 <a-icon type="arrow-right" /></router-link>
      </div>
    </div>
  </header>
</template>
<script>
import Vue from 'vue'
import CampusMasthead from '@/components/brand/CampusMasthead'
import { mapActions } from 'vuex'
import { ACCESS_TOKEN } from '@/store/mutation-types'
import TMenu from '@/components/menu/tmenu'
import { getFileAccessHttpUrl } from '@/api/manage'
export default {
    components: { TMenu, CampusMasthead },
    data () {
        return { menuOpen: false, compact: false, logoFailed: false, viewportQuery: null }
    },
    computed: {
        menus () { return this.$store.state.user.menuList || [] },
        sysConfig () { return this.$store.getters.sysConfig || {} },
        brandName () { return (this.sysConfig.brandName || '').trim() || '人工智能教学平台' },
        logoUrl () {
            const { logo, qiniuDomain } = this.sysConfig
            if (!logo) return ''
            return /^https?:\/\//.test(logo) ? logo : (qiniuDomain ? qiniuDomain.replace(/\/$/, '') + '/' + logo : getFileAccessHttpUrl(logo))
        },
        isLoggedIn () { return Boolean(this.$store.state.user.token || Vue.ls.get(ACCESS_TOKEN)) },
        accountName () {
            const info = this.$store.getters.userInfo || {}
            return info.realname || info.username || '个人空间'
        }
    },
    watch: {
        '$route.fullPath' () { this.menuOpen = false },
        logoUrl () { this.logoFailed = false }
    },
    mounted () {
        this.viewportQuery = window.matchMedia('(max-width: 900px)')
        this.updateViewport()
        this.viewportQuery.addListener(this.updateViewport)
    },
    beforeDestroy () {
        if (this.viewportQuery) this.viewportQuery.removeListener(this.updateViewport)
    },
    methods: {
        ...mapActions(['Logout']),
        updateViewport () { this.compact = this.viewportQuery.matches },
        handleLogout () {
            this.$confirm({
                title: '退出登录',
                content: '确定退出当前账号吗？',
                onOk: () => this.Logout({}).then(() => window.location.reload())
                    .catch(() => this.$message.error('退出失败，请稍后重试。'))
            })
        }
    }
}
</script>
<style scoped lang="less">
.public-header { background: #fff; border-bottom: 1px solid #e1e4e8; color: #20252b; }
.header-inner { max-width: 1280px; min-height: 70px; padding: 14px 40px; margin: auto; display: flex; align-items: center; gap: 48px; line-height: 1.5; }
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; color: #20252b; flex-shrink: 0; }
.brand-name { font-size: 18px; font-weight: 600; letter-spacing: .5px; max-width: 260px; overflow-wrap: anywhere; }
.brand-mark { display: inline-flex; align-items: center; color: #74256a; font-size: 12px; font-weight: 600; letter-spacing: 2px; padding-right: 13px; border-right: 1px solid #dbd1da; flex-shrink: 0; }
.brand-logo { max-width: 100px; max-height: 40px; object-fit: contain; }
.header-nav { flex: 1; min-width: 0; }
.default-menu { display: flex; gap: 32px; }
.default-menu a { color: #626d78; padding: 9px 0; border-bottom: 1px solid transparent; white-space: nowrap; font-size: 14px; }
.default-menu a:hover, .default-menu a.is-active { color: #20252b; border-color: #20252b; }
.configured-menu { border: 0; background: transparent; }
.configured-menu /deep/ .ant-menu-item > a, .configured-menu /deep/ .ant-menu-submenu-title > a { color: #45515e; }
.account-actions { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.account-link { color: #45515e; display: flex; align-items: center; gap: 6px; }
.account-link span { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.login-link { display: inline-flex; align-items: center; gap: 18px; padding: 10px 18px; border: 1px solid #74256a; border-radius: 3px; color: #74256a; font-size: 13px; white-space: nowrap; }
.login-link:hover { background: #f7f8fa; color: #592052; border-color: #74256a; }
.logout-button, .menu-toggle { border: 1px solid #e1e4e8; background: transparent; border-radius: 3px; padding: 8px 10px; color: #596775; cursor: pointer; }
.menu-toggle { display: none; }
a:focus-visible, button:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
@media (max-width: 1100px) { .header-inner { gap: 30px; } .brand-name { max-width: 210px; } .default-menu { gap: 24px; } }
@media (max-width: 900px) { .header-inner { gap: 12px; flex-wrap: wrap; padding: 18px 28px; min-height: 70px; } .brand { flex: 1; } .brand-name { font-size: 19px; max-width: 100%; } .menu-toggle { display: block; order: 3; width: 38px; height: 38px; } .account-actions { order: 2; } .header-nav { display: none; order: 4; flex-basis: 100%; } .header-nav.is-open { display: block; padding-top: 12px; border-top: 1px solid #e1e4e8; } .default-menu { flex-direction: column; gap: 2px; } .default-menu a { padding: 12px 0; } }
@media (max-width: 480px) { .header-inner { padding: 16px 22px; gap: 10px; } .brand { gap: 8px; } .brand-mark { display: none; } .brand-logo { max-width: 32px; max-height: 32px; } .brand-name { font-size: 17px; } .login-link { padding: 8px 10px; font-size: 12px; } .login-link .anticon { display: none; } .account-actions { gap: 6px; } .account-link span { max-width: 55px; } }
</style>
