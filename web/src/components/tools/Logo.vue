<template>
  <div class="logo">
    <router-link :to="{path:'/home'}" :aria-label="brandName" :title="brandName">
      <img v-if="logo && !logoFailed" :src="logo" :alt="brandName" @error="logoFailed = true">
      <span v-else class="logo-mark" aria-hidden="true">天工</span>
      <h1 v-if="showTitle">{{ brandName }}</h1>
    </router-link>
  </div>
</template>

<script>
import { mixin } from '@/utils/mixin.js'
import { getFileAccessHttpUrl } from '@/api/manage'
import { brandingFileUrl, platformBrandName } from '@/utils/platformBranding'
export default {
    name: 'Logo',
    mixins: [mixin],
    props: {
        showTitle: {
            type: Boolean,
            default: true,
            required: false
        }
    },
    data () {
        return {
            logoFailed: false
        }
    },
    computed: {
        brandName () {
            return platformBrandName(this.$store.state.user.sysConfig)
        },
        logo () {
            const config = this.$store.state.user.sysConfig || {}
            return brandingFileUrl(config, config.logo, getFileAccessHttpUrl)
        }
    },
    watch: {
        logo () {
            this.logoFailed = false
        }
    }
}
</script>
<style lang="less" scoped>
  /*缩小首页布 局顶部的高度*/
  @height: 59px;

  .logo a {
    display: flex;
    align-items: center;
    height: 100%;
    min-width: 0;
    padding-right: 12px;
  }

  .logo img, .logo-mark {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    object-fit: contain;
  }

  .logo-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid currentColor;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1;
  }

  .logo h1 {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    line-height: 20px;
    margin: 0 0 0 8px;
  }

  .sider {
    box-shadow: none !important;
    .logo {
      height: @height !important;
      line-height: @height !important;
      box-shadow: none !important;
      transition: background 300ms;

      a {
        color: white;
        &:hover {
          color: rgba(255, 255, 255, 0.8);
        }
      }
    }

    &.light .logo {
      background-color: @primary-color;
    }
  }
</style>
