<template>
  <div class="banner">
    <div v-if="banner.length > 0" class="carousel">
      <a-carousel
        ref="carousel"
        :autoplay="banner.length > 1"
        :autoplaySpeed="5000"
        :speed="800"
        :dots="banner.length > 1"
        :infinite="banner.length > 1"
        :draggable="banner.length > 1"
        :pauseOnHover="false"
      >
        <div v-for="(b, i) in banner" :key="i">
          <a v-if="b.href" :href="b.href" target="_blank" rel="noopener noreferrer">
            <img :src="b.img" alt="" />
          </a>
          <img v-else :src="b.img" alt="" />
        </div>
      </a-carousel>
      <button v-if="banner.length > 1" type="button" class="carousel-arrow carousel-prev" aria-label="上一张" @click="$refs.carousel.prev()">
        <a-icon type="left" aria-hidden="true" />
      </button>
      <button v-if="banner.length > 1" type="button" class="carousel-arrow carousel-next" aria-label="下一张" @click="$refs.carousel.next()">
        <a-icon type="right" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<script>
import { getFileAccessHttpUrl } from '@/api/manage'
export default {
    name: 'Banner',
    components: {},
    data () {
        return {
            banner: [],
            sysConfig: {},
            loading: true
        }
    },
    created () {
    // 获取banner数据
        this.sysConfig = this.$store.getters.sysConfig

        if (this.sysConfig.banner) {
            var banners = this.sysConfig.banner.split(',')
            var bannerLinks = this.sysConfig.bannerLinks ? this.sysConfig.bannerLinks.split('\n') : []
            for (var i in banners) {
                var b = {}
                b.img = getFileAccessHttpUrl(banners[i])
                if (bannerLinks.length > i) {
                    b.href = bannerLinks[i]
                }
                this.banner.push(b)
            }
        }
    },
    methods: {}
}
</script>

<style lang="less" scoped>
.carousel {
  position: relative;
  height: 300px;
  border-radius: 20px;
  overflow: hidden;
  img {
    display: block;
    width: 100%;
    height: 300px;
  }
  .carousel-arrow {
    position: absolute;
    top: 50%;
    z-index: 1;
    transform: translateY(-50%);
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 50%;
    color: #fff;
    background: rgba(0, 0, 0, 0.25);
    font-size: 24px;
    cursor: pointer;
    &:focus-visible {
      outline: 2px solid #fff;
      outline-offset: -4px;
    }
  }
  .carousel-prev {
    left: 10px;
  }
  .carousel-next {
    right: 10px;
  }
  /deep/ .slick-dots {
    left: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    width: auto;
    height: auto;
    padding: 8px;
    border-radius: 12px;
    background: rgba(0, 0, 0, 0.5);
    transform: translateX(-50%);
  }
}
</style>
