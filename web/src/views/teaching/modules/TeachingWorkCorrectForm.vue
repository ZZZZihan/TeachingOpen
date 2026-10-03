<template>
  <fieldset class="feedback-form" :disabled="disabled">
    <legend>评分与反馈</legend>
    <p id="grading-score-help" class="feedback-help">0–5 分，也可以只填写评语。评分不会自动代选。</p>
    <div class="score-options" role="radiogroup" aria-label="评分" aria-describedby="grading-score-help">
      <label v-for="number in 6" :key="number" :class="{ chosen: value.score === number - 1 }">
        <input type="radio" name="grading-score" :value="number - 1" :checked="value.score === number - 1" @change="change('score', number - 1)">
        <span>{{ number - 1 }}</span>
      </label>
      <button v-if="value.score !== null" type="button" class="clear-score" @click="change('score', null)">取消评分</button>
    </div>
    <label class="comment-label" for="grading-comment">评语</label>
    <textarea
      id="grading-comment"
      :value="value.comment"
      rows="5"
      maxlength="512"
      placeholder="说说完成得好的地方，以及下一步可以怎样改进。"
      @input="change('comment', $event.target.value)" />
    <p class="feedback-help">{{ value.comment.length }} / 512 字</p>
  </fieldset>
</template>
<script>
export default {
    name: 'TeachingWorkCorrectForm',
    props: {
        value: { type: Object, required: true },
        disabled: { type: Boolean, default: false }
    },
    methods: {
        change (key, value) { this.$emit('input', { ...this.value, [key]: value }) }
    }
}
</script>
<style scoped>
.feedback-form { border: 0; padding: 0; margin: 0; min-width: 0; }
legend { font-size: 18px; font-weight: 600; color: #28252c; margin-bottom: 8px; }
.feedback-help { color: #746b75; font-size: 13px; line-height: 1.7; }
.score-options { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 16px 0 24px; }
.score-options label { position: relative; margin: 0; cursor: pointer; }
.score-options input { position: absolute; width: 100%; height: 100%; opacity: 0; cursor: pointer; margin: 0; }
.score-options span { display: grid; place-items: center; width: 42px; height: 42px; border: 1px solid #d3c9d2; border-radius: 4px; font-size: 17px; color: #28252c; }
.chosen span { background: #74256a; color: white; border-color: #74256a; }
.score-options input:focus-visible + span { outline: 3px solid #74256a; outline-offset: 3px; }
.clear-score { background: transparent; border: 0; color: #675f69; text-decoration: underline; padding: 8px; cursor: pointer; }
.comment-label { display: block; color: #28252c; margin-bottom: 8px; font-weight: 600; }
textarea { resize: vertical; width: 100%; border: 1px solid #d3c9d2; border-radius: 4px; padding: 12px; color: #3d3740; line-height: 1.8; background: #fff; }
textarea:focus { outline: 2px solid #74256a; outline-offset: 2px; }
fieldset:disabled { opacity: .65; }
</style>
