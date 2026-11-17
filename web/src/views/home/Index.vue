<template>
  <div class="boxBackground">
    <div class="boxContent" v-html="sysConfig._homeHtml"></div>
    <RegistrationEntry class="home-registration" />
  </div>
</template>
<script>
import RegistrationEntry from './modules/RegistrationEntry'
export default {
    components: { RegistrationEntry },
    computed: {
        sysConfig () { return this.$store.getters.sysConfig || {} }
    }
}
</script>
<style scoped lang="less">
.boxContent { overflow-wrap: anywhere; }
.boxContent /deep/ img { max-width: 100%; height: auto; }
.home-registration { margin-top: 38px; padding: 30px 36px; border: 1px solid #e4d9c2; border-radius: 8px; background: #fff3d9; }
@media (max-width: 700px) { .home-registration { padding: 26px 22px; } }
</style>
