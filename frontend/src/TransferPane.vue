<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { Model, TransferResult } from './types'
import SheetViewer from './SheetViewer.vue'

const props = defineProps<{models: Model[]}>()
const form = reactive({
  length: 12, width: 3, height: 3, mass: 16, cg: [0,0,0], lugs: [[-5,0],[5,0]],
  start: [-8,0,78], end: [8,0,90], bottom: 1, factor: 1.1, gauge: 1.435,
  cranes: [-1,1].map(sign => ({index: -1, boom: 0, center: [0,sign*14], exclusion: 3, boom_buffer: 1,
    hook: null as number|null, hook_rating: null as number|null, rigging: 0.3, sling_height: 2,
    verified_height: null as number|null})),
  obstacles: [] as number[][],
})
const active = ref(0), pick = ref(0), busy = ref(false), error = ref('')
const result = ref<TransferResult>(), viewer = ref<InstanceType<typeof SheetViewer>>()
const points = computed(() => [...form.lugs,form.cg])
let revision = 0
watch(form, () => { revision++; result.value = undefined; error.value = '' }, {flush:'sync'})
function selectModel(i:number, index:number) {
  const c = form.cranes[i], model = props.models[index]
  if (!model) return
  c.index = index
  c.boom = model.booms.includes(25.98) ? 25.98 : model.booms[0]
  const hook = model.main_hooks.find(h=>h.is_default)
  c.hook = hook?.mass_t ?? model.hook_main_t
  c.hook_rating = hook?.rated_t ?? null
}
watch(()=>props.models, models=>{
  const idx = models.findIndex(m=>m.model==='QY70K-1' && m.booms.includes(25.98))
  if (models.length) for(let i=0;i<2;i++) selectModel(i,Math.max(idx,0))
},{immediate:true})
function place(e:MouseEvent) {
  const svg=e.currentTarget as SVGSVGElement, matrix=svg.getScreenCTM()
  if(!matrix) return
  const pos=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse())
  const p=points.value[pick.value]
  p[0]=Number(Math.max(-form.length/2,Math.min(form.length/2,pos.x)).toFixed(3))
  p[1]=Number(Math.max(-form.width/2,Math.min(form.width/2,-pos.y)).toFixed(3))
}
const runs=computed(()=>{
  const out:{start:number;end:number;text:string}[]=[]
  for(const s of result.value?.segments ?? []){
    const text=[...s.unsafe,...s.unknown].join('、') || '已核项满足'
    const last=out[out.length-1]
    if(last?.text===text) last.end=s.end
    else out.push({start:s.start,end:s.end,text})
  }
  return out
})
async function calculate() {
  const id=revision
  busy.value=true; error.value=''
  try {
    const cranes=form.cranes.map(({index,...c})=>{
      const m=props.models[index]
      return {...c, verified_height:c.verified_height || null,model:m.model,brand:m.brand,config:m.config}
    })
    const data=await window.pywebview!.api.calculate({kind:'rail.transfer',transfer:{...form,cranes}})
    if(id===revision){result.value=data;active.value=0}
  } catch(e){if(id===revision) error.value=String(e)}
  finally {busy.value=false}
}
async function save(){
  if(!result.value) return
  try {await window.pywebview!.api.export(result.value.drawings[active.value].id,'dxf')}
  catch(e){error.value=String(e)}
}
const numeric=['length','width','height','mass','bottom','factor','gauge'] as const
const labels=['长 / m','宽 / m','高 / m','质量 / t','转运时底面离地 / m','吊物与索具放大系数','目标轨距 / m']
const craneFields=['exclusion','boom_buffer','hook','hook_rating','rigging','sling_height','verified_height'] as const
const craneLabels=['平面禁入半径 / m','臂投影包络半宽 / m','主钩自重 / t','主钩额载 / t','本侧索具 / t','吊点至钩高差 / m','全段已核实可用钩高下限 / m（选填）']
</script>
<template>
<main><div class="workspace">
<div class="inspector"><form @submit.prevent="calculate">
<h2>双机上轨</h2>
<p class="hint">水平刚体、两根竖向合力线。场地 X 向右、Y 向上，航向自 +X 逆时针为正。</p>
<div class="pair"><label v-for="(key,i) in numeric" :key="key">{{labels[i]}}<input required type="number" step="any" min="0.000001" v-model.number="form[key]"></label></div>
<fieldset><legend>在吊物顶面选择吊点与重心</legend>
<select v-model.number="pick"><option v-for="(tag,i) in ['吊点 A','吊点 B','重心 G']" :key="tag" :value="i">{{tag}}</option></select>
<svg v-if="form.length>0 && form.width>0" class="pick" :viewBox="[-form.length/2,-form.width/2,form.length,form.width].join(' ')" @click="place">
<rect :x="-form.length/2" :y="-form.width/2" :width="form.length" :height="form.width" fill="#dceae9"/>
<line :x1="form.lugs[0][0]" :y1="-form.lugs[0][1]" :x2="form.lugs[1][0]" :y2="-form.lugs[1][1]" stroke="#59838a" :stroke-width="form.length/160"/>
<g v-for="(p,i) in points" :key="i"><circle :cx="p[0]" :cy="-p[1]" :r="form.length/70" :fill="i===2?'#b55530':'#126478'"/><text :x="p[0]" :y="-p[1]-form.length/40" :font-size="form.length/22" text-anchor="middle" fill="#173747">{{'ABG'[i]}}</text></g></svg>
<div class="pair"><label v-for="(v,k) in points[pick]" :key="k">局部 {{'xyz'[k]}} / m<input required type="number" step="any" v-model.number="points[pick][k]"></label></div>
<p class="hint">原点在形心，x 沿车长。A、B 位于顶面。点图或输入坐标。</p></fieldset>
<fieldset v-for="(c,i) in form.cranes" :key="i"><legend>{{'AB'[i]}} 机站位与固定配置</legend>
<select :value="c.index" @change="selectModel(i,Number(($event.target as HTMLSelectElement).value))"><option v-for="(m,j) in models" :key="j" :value="j">{{m.brand}} {{m.model}} · {{m.config}}</option></select>
<label>固定臂长 / m<select v-model.number="c.boom"><option v-for="b in models[c.index]?.booms" :key="b" :value="b">{{b}}</option></select></label>
<div class="pair"><label v-for="(_,k) in c.center" :key="k">回转中心 {{'XY'[k]}} / m<input required type="number" step="any" v-model.number="c.center[k]"></label>
<label v-for="(key,k) in craneFields" :key="key">{{craneLabels[k]}}<input type="number" step="any" min="0" :required="key!=='verified_height'" v-model.number="c[key]"></label></div>
</fieldset>
<fieldset><legend>起吊与对轨姿态</legend><div v-for="(p,i) in [form.start,form.end]" :key="i"><strong>{{i?'落位':'起吊'}}</strong><div class="pair"><label v-for="(_,k) in p" :key="k">{{['中心 X / m','中心 Y / m','航向 / °'][k]}}<input required type="number" step="any" v-model.number="p[k]"></label></div></div>
<p class="hint">转运段中心直线移动，航向按输入角差连续旋转，底面高度固定。</p></fieldset>
<fieldset><legend>场地禁入圆</legend><div v-for="(o,i) in form.obstacles" :key="i"><div class="pair"><label v-for="(_,k) in o" :key="k">{{['X / m','Y / m','半径 / m'][k]}}<input required type="number" step="any" v-model.number="o[k]"></label></div><button type="button" @click="form.obstacles.splice(i,1)">移除</button></div><button type="button" @click="form.obstacles.push([0,0,1])">添加障碍</button></fieldset>
<button class="primary" :disabled="busy || !models.length">生成图纸并校核转运段</button><p role="alert">{{error}}</p>
</form></div>
<section class="transfer-output"><h2>双机吊装图纸</h2>
<template v-if="result"><nav><button v-for="(t,i) in ['静力分析','俯视转向轨迹']" :class="{active:active===i}" :key="t" @click="active=i">{{t}}</button><button @click="save">导出本图 DXF</button></nav>
<div class="paper"><button class="sheet-open" title="放大图纸" @click="viewer?.open()" v-html="result.drawings[active].svg"></button></div>
<SheetViewer ref="viewer" :svg="result.drawings[active].svg"/>
<h3>转运区间校核</h3>
<p>{{result.segments.some(s=>s.unsafe.length)?'存在超限或禁入区相交':result.segments.some(s=>s.unknown.length)?'存在待核区间':'所列校核项全段满足'}} · A / B 计算总吊重 {{result.loads.map(x=>x.toFixed(2)).join(' / ')}} t</p>
<p v-for="(c,i) in form.cranes" :key="i">{{'AB'[i]}} 机 · 幅度包络 {{Math.min(...result.segments.map(s=>s.radii[i][0])).toFixed(2)}}–{{Math.max(...result.segments.map(s=>s.radii[i][1])).toFixed(2)}} m · 已覆盖表档最高负荷率 {{result.segments.some(s=>s.ratios[i]!==null) ? (100*Math.max(...result.segments.map(s=>s.ratios[i]??0))).toFixed(1)+'%' : '无数据'}}</p>
<p v-for="r in runs" :key="r.start">{{(100*r.start).toFixed(2)}}% – {{(100*r.end).toFixed(2)}}%　{{r.text}}</p></template>
<p v-else>设置吊点、重心、两机站位与起止姿态后生成两张图纸。</p>
<p class="hint">只校核固定配置的表档载荷、钩载、所填钩高及吊物、臂投影对禁入圆的平面净距。臂间三维净空、索间干涉、回转作业扇区、不同步倾斜、支腿地基及起落段需另行复核。</p>
</section></div></main>
</template>
<style scoped>
.pick{width:100%;height:110px;cursor:crosshair}.transfer-output{overflow:auto;padding:1rem}.transfer-output .paper{height:clamp(240px,48vh,560px)}fieldset{margin-block:12px}fieldset select{max-width:100%}
</style>
