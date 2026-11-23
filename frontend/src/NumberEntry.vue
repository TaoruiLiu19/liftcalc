<script setup lang="ts">
import { computed, ref } from 'vue'
const value=defineModel<number|null>({required:true})
const props=defineProps<{label:string; min?:number; max?:number; optional?:boolean; attempted?:boolean}>()
const touched=ref(false)
const problem=computed(()=>{
  const raw=value.value
  if(raw===null || String(raw)==='') return props.optional?'':'请填写此项'
  if(!Number.isFinite(raw)) return '请输入有效数字'
  if(props.min!==undefined && raw<props.min) return '最小值为 '+props.min
  if(props.max!==undefined && raw>props.max) return '最大值为 '+props.max
  return ''
})
const message=computed(()=>touched.value || props.attempted || (value.value!=null && String(value.value)!=='') ? problem.value : '')
</script>
<template><label class="number-entry">{{label}}
  <input type="number" step="any" :required="!optional" :min="min" :max="max" v-model.number="value" @blur="touched=true" :aria-invalid="!!message">
  <span v-if="message" class="field-error">{{message}}</span>
</label></template>
