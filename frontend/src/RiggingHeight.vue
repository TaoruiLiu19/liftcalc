<script setup lang="ts">
import { computed, ref } from 'vue'
import { riggingRise, type HeightDatum, type RiggingMeasurement } from './riggingHeight'

const measurement = defineModel<RiggingMeasurement>({required:true})
const props = defineProps<{ label:string; bodyHeight:number; estimate?:boolean; attempted?:boolean }>()
const touched = ref(false)
const rise = computed(() => riggingRise(measurement.value,props.bodyHeight))
const error = computed(() => {
  if (measurement.value.datum === 'estimate') return ''
  if (rise.value === null) return touched.value || props.attempted ? '请填写实测高度。' : ''
  if (rise.value <= 0) return measurement.value.datum === 'bottom'
    ? '总高度须大于吊物高度。' : '捆扎后索具高度须大于零。'
  return ''
})
function changeDatum(event:Event) {
  const datum = (event.target as HTMLSelectElement).value as HeightDatum
  const value = rise.value !== null && rise.value > 0 && datum !== 'estimate'
    ? rise.value + (datum === 'bottom' ? props.bodyHeight : 0) : null
  measurement.value = {datum,value}
  touched.value = false
}
function measure(event:Event) {
  const n = (event.target as HTMLInputElement).valueAsNumber
  measurement.value = {...measurement.value,value:Number.isFinite(n) ? n : null}
}
</script>
<template>
<fieldset class="rigging-height"><legend>{{label}}</legend>
  <label>测量基准<select :value="measurement.datum" @change="changeDatum">
    <option value="top">吊物顶面至钩中心</option><option value="bottom">吊物底面至钩中心</option>
    <option v-if="estimate" value="estimate">按吊点几何估算</option>
  </select></label>
  <label v-if="measurement.datum!=='estimate'">{{measurement.datum==='bottom'?'捆扎后总高度':'捆扎后索具净高'}} / m
    <input type="number" step="any" required :value="measurement.value" :aria-invalid="!!error"
      :min="measurement.datum==='bottom'?bodyHeight:0" @input="measure" @blur="touched=true">
  </label>
  <p v-if="error" class="height-error" role="alert">{{error}}</p>
  <p v-else-if="rise!==null && rise>0" class="muted">索具净高 {{rise.toFixed(2)}} m · 吊物底至钩中心 {{(bodyHeight+rise).toFixed(2)}} m</p>
  <p v-else class="muted">{{measurement.datum==='estimate'?'按最短索与水平面成 60° 估算。':'填写索具受力拉紧后的竖向距离。'}}</p>
</fieldset>
</template>
<style scoped>
.rigging-height{min-width:0;margin:10px 0;padding:10px 14px;border:1px solid var(--line,#819199);border-radius:8px}
legend{font-weight:600}.rigging-height p{margin:6px 0 0}.height-error{color:var(--danger,#c23545)}input[aria-invalid=true]{border-color:var(--danger,#c23545)}
</style>
