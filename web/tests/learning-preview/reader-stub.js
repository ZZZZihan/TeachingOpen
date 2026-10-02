export const JeecgListMixin = {}
export default {
  data () { return { visible: false, unit: {} } },
  methods: { view (unit) { this.unit = unit; this.visible = true }, handleCancel () { this.visible = false } },
  template: '<div v-if="visible" class="preview-reader" role="dialog" aria-label="学习入口检查"><p>学习弹窗已收到单元：{{ unit.unitName }}</p><p>预览只验证入口，未运行播放器或编辑器。</p><button @click="handleCancel">关闭预览弹窗</button></div>'
}
