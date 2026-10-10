export default {props:['value'],template:'<a-input :value="value" @change="$emit(\'change\',$event.target.value)" />'}
