<template>
  <div class="boxBackground">
    <div class="boxContent" v-html="sysConfig._homeHtml"></div>
    <PublicUserDirectory>
      <RegistrationEntry slot="registration-entry" />
    </PublicUserDirectory>
  </div>
</template>
<script>
import PublicUserDirectory from './modules/PublicUserDirectory'
import RegistrationEntry from './modules/RegistrationEntry'
export default {
    components: { PublicUserDirectory, RegistrationEntry },
    computed: {
        sysConfig () { return this.$store.getters.sysConfig || {} }
    }
}
</script>
<style scoped lang="less">
.boxContent { overflow-wrap: anywhere; }
.boxContent /deep/ img { max-width: 100%; height: auto; }
</style>
