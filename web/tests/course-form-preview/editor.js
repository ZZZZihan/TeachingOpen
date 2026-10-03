export default {props:['value'],template:'<a-textarea :value="value" @input="$emit(\'input\',$event.target.value)" rows="3" />'}
