export default {
  data: () => ({ visible: false, title: '', entry: '', disableSubmit: false }),
  methods: { add () { this.entry = '合成新增入口'; this.visible = true }, edit (row) { this.entry = '合成编辑入口 ' + row.id; this.visible = true }, open (code) { this.entry = '合成字典入口 ' + code; this.visible = true } },
  template: '<a-modal v-model="visible" :title="title || \'合成维护入口\'" :footer="null"><p>{{entry}}</p><p>此处是入口替代组件，实际维护表单不属于本次列表合成检查。</p><a-button @click="visible=false">关闭合成入口</a-button></a-modal>'
}
