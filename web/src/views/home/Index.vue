<template>
  <div class="boxBackground">
    <div class="boxContent" v-html="sysConfig._homeHtml"></div>
  </div>
</template>
<script>
export default {
    computed: {
        sysConfig () { return this.$store.getters.sysConfig || {} }
    }
}
</script>
<style scoped lang="less">
.boxContent { overflow-wrap: anywhere; }
.boxContent /deep/ img { max-width: 100%; height: auto; }
</style>
