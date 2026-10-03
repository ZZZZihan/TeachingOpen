export default {
  props: ['value', 'disabled', 'dictCode', 'placeholder'], model: { prop: 'value', event: 'change' },
  computed: { options () { return this.dictCode === 'course_type' ? [['1', '合成课程性质 A'], ['2', '合成课程性质 B']] : [['synthetic-course-1', '合成课程 1'], ['synthetic-course-2', '合成课程 2']] } },
  template: '<select class="synthetic-select" :aria-label="placeholder || \'合成字典选择\'" :value="value || \'\'" :disabled="disabled" @change="$emit(\'change\', $event.target.value)"><option value="">全部</option><option v-for="item in options" :key="item[0]" :value="item[0]">{{item[1]}}</option></select>'
}
