<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { groupCraneModels } from './craneModels'
import type { Model, TransferOutcome, TransferScene } from './types'

import TransferPlot from './TransferPlot.vue'
import TransferResults from './TransferResults.vue'
import NumberEntry from './NumberEntry.vue'

const props = defineProps<{models: Model[]}>()
const form = reactive({
  length: 12, width: 3, height: 3, mass: 16, cg: [0,0,0], lugs: [[-5,0],[5,0]],
  start: [-11,0,90], auto_route: true, auto_stations: true, end: [11,0,90], bottom: null as number|null, plan_clearance: 0, factor: 1.1, gauge: 1.435,
  cranes: [-1,1].map(sign => ({modelKey: '', config: '', center: [0,sign*5.5], footprint_length: 10, footprint_width: 5, heading: 0, boom_buffer: 1,
    hook: null as number|null, hook_rating: null as number|null, rigging: 0.3, sling_height: null as number|null,
    radius_limit: null as number|null})),
  obstacles: [] as number[][],
})
const pick = ref(0), busy = ref(false), error = ref('')
const result = ref<TransferOutcome>()
const planned = computed(() => result.value?.status === 'planned' ? result.value : undefined)
const points = computed(() => [...form.lugs,form.cg])
const stages = ['吊物、吊点与重心', 'A 机工况', 'B 机工况', '转运与场地', '图纸与校核']
const step = ref(0), reached = ref(0)
const crane = computed(() => form.cranes[step.value-1])
const modelChoices = computed(() => groupCraneModels(props.models))
const selectedGroup = computed(() => modelChoices.value.find(group => group.key === crane.value?.modelKey))
const maxRating = computed(() => {
  const configs = selectedGroup.value?.configs ?? []
  return Math.max(0, ...configs.filter(({row}) => !crane.value.config || row.config === crane.value.config)
    .flatMap(({row}) => row.boom_ratings.map(rating => rating.max_rated_t)))
})
const editor = ref<HTMLFormElement>(), panel = ref<HTMLElement>()
const attempted = ref(false)
let revision = 0

function goto(target: number) {
  attempted.value = false
  step.value = target
  reached.value = Math.max(reached.value, target)
  error.value = ''
  nextTick(() => {
    panel.value?.scrollTo(0, 0)
    panel.value?.querySelector<HTMLElement>('h2')?.focus()
  })
}
function advance(target = step.value + 1) {
  if (busy.value || target === step.value) return
  if (target < step.value) { goto(target); return }
  attempted.value = true
  if (!editor.value?.checkValidity()) {
    editor.value?.querySelector<HTMLInputElement>('input:invalid')?.focus()
    return
  }
  if (step.value===0 && split.value.error) return
  if (target === 4 && !result.value) { void calculate(); return }
  goto(target)
}
watch(form, () => { revision++; reached.value = Math.min(reached.value, step.value); result.value = undefined; error.value = '' }, {flush:'sync'})
function selectModel(i:number, key:string) {
  const group = modelChoices.value.find(group => group.key === key)
  const c = form.cranes[i]
  if (!group || c.modelKey === key) return
  const model = group.configs[0].row
  const hook = model.main_hooks.find(h=>h.is_default)
  c.modelKey = key
  c.config = ''
  c.hook = hook?.mass_t ?? model.hook_main_t
  c.hook_rating = hook?.rated_t ?? null
}
watch(modelChoices, groups=>{
  const initial = groups.find(m=>m.brand==='徐工' && m.model==='QY70K-1') ?? groups[0]
  if (initial) form.cranes.forEach((c,i) => {
    if (!groups.some(group => group.key === c.modelKey)) selectModel(i,initial.key)
  })
},{immediate:true})
const split = computed(() => {
  const [[ax, ay], [bx, by]] = form.lugs
  const [gx, gy, gz] = form.cg
  if (![form.length, form.width, form.height, form.mass].every(v => Number.isFinite(v) && v > 0))
    return {error: '请填写大于零的吊物尺寸和质量。'}
  for (const [i, p] of points.value.entries()) {
    if (p.some(v => !Number.isFinite(v)) || Math.abs(p[0]) > form.length/2 || Math.abs(p[1]) > form.width/2)
      return {error: i === 2 ? '请检查重心 G 的坐标。重心水平投影须在吊物轮廓内。'
        : '请检查吊点 ' + 'AB'[i] + ' 的坐标。吊点须位于吊物顶面。'}
  }
  if (Math.abs(gz) >= form.height/2) return {error: 'G 点 Z 坐标须在吊物上下表面之间。'}
  const dx = bx - ax, dy = by - ay, span = Math.hypot(dx, dy)
  if (span < 1e-6) return {error: 'A、B 吊点重合，请移动一个吊点。'}
  if (Math.abs((gx-ax)*dy - (gy-ay)*dx) / span > 1e-8)
    return {error: '重心水平投影偏离两吊点连线，按两根竖向吊索无法维持所设水平姿态。'}
  const shareB = ((gx-ax)*dx + (gy-ay)*dy) / span**2
  if (shareB <= 0 || shareB >= 1)
    return {error: '重心水平投影须位于 A、B 两吊点之间，两侧吊索均须受拉。'}
  return {shares: [1 - shareB, shareB]}
})
const snap=ref(true)
function place(x:number,y:number){
  const p=points.value[pick.value]
  if(pick.value===2 && snap.value){
    const [a,b]=form.lugs,dx=b[0]-a[0],dy=b[1]-a[1],len=dx*dx+dy*dy
    if(len>0){
      const t=Math.max(0, Math.min(1, ((x-a[0])*dx+(y-a[1])*dy)/len))
      x=a[0]+t*dx; y=a[1]+t*dy
    }
  }
  p[0]=x; p[1]=y
}
// Before planning, show the footprint at a provisional corridor station.
const previewStations = computed(() => {
  if (!form.auto_stations) return form.cranes
  const [ax,ay,yaw] = form.start, [bx,by] = form.end
  const heading = Math.atan2(by-ay,bx-ax), nx = -Math.sin(heading), ny = Math.cos(heading)
  const angle = yaw*Math.PI/180-heading
  const [[x1,y1],[x2,y2]] = form.lugs
  const sign = (x2-x1)*Math.sin(angle)+(y2-y1)*Math.cos(angle)>=0 ? 1 : -1
  return form.cranes.map((c,i) => {
    const offset = (form.width/2+c.footprint_width/2+form.plan_clearance+.35)*sign*(i===0?-1:1)
    return {...c,center:[(ax+bx)/2+offset*nx,(ay+by)/2+offset*ny],heading:heading*180/Math.PI}
  })
})
const scene=computed<TransferScene>(() => {
  const plan = planned.value
  const failedSearch = step.value === 4 && result.value?.status === 'unplanned'
  return {
    length:form.length,width:form.width,points:points.value,pick:pick.value,gauge:form.gauge,
    cranes:plan ? form.cranes.map((c,i)=>({...c,...plan.stations[i]}))
      : failedSearch && form.auto_stations ? [] : previewStations.value,
    provisional:form.auto_stations && !plan && !failedSearch,
    poses:plan?.poses ?? [form.start,form.end],obstacles:form.obstacles,
  }
})
async function calculate() {
  const id=revision
  busy.value=true; error.value=''
  try {
    const cranes=form.cranes.map(({modelKey,config,center,heading,sling_height,...c})=>{
      const m=modelChoices.value.find(group => group.key === modelKey)
      if (!m) throw new Error('请选择两台起重机的机型。')
      return {...c,...(typeof sling_height==='number'?{sling_height}:{}), ...(form.auto_stations?{}:{center,heading}),
        radius_limit:c.radius_limit || null,model:m.model,brand:m.brand,config:config || null}
    })
    const {bottom, ...inputs}=form
    const data=await window.pywebview!.api.calculate({kind:'rail.transfer',
      transfer:{...inputs,...(typeof bottom==='number'?{bottom}:{}),cranes}})
    if(id===revision){result.value=data;goto(4)}
  } catch(e){if(id===revision) error.value=String(e)}
  finally {busy.value=false}
}
const sizeFields = {length:'长 / m', width:'宽 / m', height:'高 / m', mass:'质量 / t'} as const
const craneFields=['boom_buffer','hook','hook_rating','rigging'] as const
const craneLabels=['起重臂水平投影包络半宽 / m','主吊钩组质量 / t','主吊钩组额定起重量 / t','本侧吊具及索具质量 / t']
</script>
<template>
<main class="transfer"><div class="workflow">
  <aside class="workflow-nav">
    <h2>双机抬吊上轨</h2>
    <ol class="steps" aria-label="双机吊装步骤">
      <li v-for="(title,i) in stages" :key="title" :class="{active:step===i,done:i<reached}">
        <button type="button" :disabled="busy || i>reached" :aria-current="step===i?'step':undefined" @click="advance(i)"><b>{{i+1}}</b>{{title}}</button>
      </li>
    </ol>
  </aside>
  <section class="workflow-panel" ref="panel">
    <form v-if="step<4" ref="editor" novalidate @submit.prevent="advance()">
      <h2 tabindex="-1">{{stages[step]}}</h2>
      <template v-if="step===0">
        <section class="block"><h3>吊物尺寸与质量</h3>
          <div class="four"><NumberEntry v-for="(label,key) in sizeFields" :key="key" v-model="form[key]" :label="label" :min=".000001" :attempted="attempted"/></div>
        </section>
        <div class="columns">
          <TransferPlot v-bind="scene" @place="place"/>
          <section class="block point-editor" :class="{invalid:split.error}"><h3>选择编辑点</h3>
            <div class="point-tabs"><button v-for="(tag,i) in ['吊点 A','吊点 B','重心 G']" :key="tag" type="button" :aria-pressed="pick===i" @click="pick=i">{{tag}}</button></div>
            <div class="pair"><NumberEntry v-for="(_,k) in points[pick]" :key="pick+'-'+k" v-model="points[pick][k]" :label="'局部 '+ 'XYZ'[k]+' / m'" :min="-[form.length,form.width,form.height][k]/2" :max="[form.length,form.width,form.height][k]/2" :attempted="attempted"/></div>
            <label v-if="pick===2"><input type="checkbox" v-model="snap"> 点选时吸附至 AB 连线</label>
            <p class="muted">点击图中顶面定位，或输入坐标微调。Z 从形心向上量取。</p>
            <p v-if="split.error" class="alert" role="alert">{{split.error}}</p>
            <section v-else class="split-preview" aria-live="polite">
              <h3>吊物静力分配</h3>
              <dl><div v-for="(share,i) in split.shares" :key="i">
                <dt>{{'AB'[i]}} 机</dt>
                <dd>{{(form.mass * share).toFixed(2)}} t · {{(share * 100).toFixed(1)}}%</dd>
              </div></dl>
            </section>
          </section>
        </div>
      </template>
      <template v-if="step===1 || step===2">
        <section class="block"><h3>机型与工况</h3>
          <div class="crane-picker">
            <label>机型（标称最大起重量）
              <select :value="selectedGroup?.key" :disabled="!modelChoices.length" @change="selectModel(step-1,($event.target as HTMLSelectElement).value)">
                <option v-for="group in modelChoices" :key="group.key" :value="group.key">{{group.tonnage}} t · {{group.brand}} {{group.model}}</option>
              </select>
            </label>
            <label class="config-picker">起重性能表工况
              <select v-model="crane.config" :title="crane.config || '自动选择合适工况'" :disabled="!selectedGroup">
                <option value="">自动选择合适工况</option>
                <option v-for="config in selectedGroup?.configs" :key="config.index" :value="config.row.config">{{config.row.config}}</option>
              </select>
            </label>
          </div>
          <p class="muted rating">起重臂长度由软件按全程工作幅度和负荷率选取，每台起重机全程采用一组工况和臂长。</p>
          <p v-if="!crane.config" class="muted rating">自动工况从所选机型的已收录表档中筛选，采用前须核对配重、支腿状态及允许作业方位。</p>
          <p v-if="maxRating" class="muted rating">当前选表范围内的最大表列额定总起重量 <strong>{{maxRating}} t</strong>。</p>
        </section>
        <div class="columns" :key="step">
          <div class="stack"><TransferPlot v-bind="scene" site :focus="step-1"/>
            <section class="block"><h3>起重机占地包络</h3>
              <div class="pair">
                <NumberEntry v-model="crane.footprint_length" label="包络长度 / m" :min=".000001" :attempted="attempted"/>
                <NumberEntry v-model="crane.footprint_width" label="包络宽度 / m" :min=".000001" :attempted="attempted"/>
              </div>
              <p class="muted">矩形以起重机回转中心为中心，须包络车体及展开后的支腿。长轴方向角从场地 +X 轴逆时针量取。初始尺寸为示例。自动站位须复核场地边界及地基。</p>
              <label><input type="checkbox" v-model="form.auto_stations"> 自动搜索两机站位（全程固定）</label>
              <div v-if="!form.auto_stations" class="three">
                <NumberEntry v-for="(_,k) in crane.center" :key="k" v-model="crane.center[k]" :label="'回转中心 '+'XY'[k]+' / m'" :attempted="attempted"/>
                <NumberEntry v-model="crane.heading" label="占地包络长轴方向角 / °" :attempted="attempted"/>
              </div>
            </section></div>
          <section class="block"><h3>作业范围与吊索具</h3><div class="pair">
            <NumberEntry v-model="crane.radius_limit" label="允许最大工作幅度 / m（选填）" :min=".000001" optional :attempted="attempted"/>
            <NumberEntry v-for="(key,k) in craneFields" :key="key" v-model="crane[key]" :label="craneLabels[k]" :min="key==='rigging'?0:.000001" :attempted="attempted"/>
          </div></section>
        </div>
      </template>
      <template v-if="step===3">
        <div class="columns"><div class="stack">
          <TransferPlot v-bind="scene" site :preview="!!planned"/>
          <p class="muted">根据起吊、落位、占地及障碍搜索中间姿态；规划完成后可慢速预演。</p>
          <section class="block"><h3>场地障碍物（圆形禁入区）</h3>
            <div v-for="(o,i) in form.obstacles" :key="i" class="obstacle"><div class="three"><NumberEntry v-for="(_,k) in o" :key="k" v-model="o[k]" :label="['X / m','Y / m','半径 / m'][k]" :min="k===2?.000001:undefined" :attempted="attempted"/></div><button type="button" @click="form.obstacles.splice(i,1)">移除障碍物 {{i+1}}</button></div>
            <button type="button" @click="form.obstacles.push([0,0,1])">＋ 添加障碍物</button>
          </section></div>
          <div class="stack">
            <section v-for="(p,i) in [form.start,form.end]" :key="i" class="block"><h3>{{i?'轨道落位姿态':'起吊姿态'}}</h3><div class="three">
              <NumberEntry v-for="(_,k) in p" :key="k" v-model="p[k]" :label="['吊物形心 X / m','吊物形心 Y / m','吊物纵轴方向角 / °'][k]" :attempted="attempted"/>
            </div></section>
            <section class="block"><h3>转运条件</h3><div class="pair">
              <NumberEntry v-model="form.factor" label="载荷放大系数" :min="1" :attempted="attempted"/>
              <NumberEntry v-model="form.plan_clearance" label="要求的最小水平净距 / m" :min="0" :attempted="attempted"/>
              <NumberEntry v-model="form.gauge" label="目标轨距 / m" :min=".000001" :attempted="attempted"/>
            </div><p class="muted">吊物纵轴方向角从场地 +X 轴逆时针量取。载荷放大系数用于各机分担的吊物质量和本侧吊索具质量。</p></section>
            <details class="block">
              <summary>图纸示意尺寸（选填）</summary>
              <div class="pair">
                <NumberEntry v-model="form.bottom" label="图示吊物底面离地高度 / m" :min="0" optional :attempted="attempted"/>
                <NumberEntry v-for="(c,i) in form.cranes" :key="i" v-model="c.sling_height"
                  :label="'AB'[i]+' 机图示顶面至吊钩中心距离 / m'" :min=".000001" optional :attempted="attempted"/>
              </div>
              <p class="muted">这些尺寸只用于绘图。留空时，底面离地按 1 m，顶面至吊钩中心按 2 m 示意。</p>
            </details>
          </div></div>
      </template>
      <p v-if="error" class="alert" role="alert">{{error}}</p>
      <div class="actions"><button v-if="step>0" type="button" :disabled="busy" @click="advance(step-1)">上一步</button>
        <button class="primary" :disabled="busy || ((step===1 || step===2) && !models.length)">{{step===3?(busy?'正在搜索与校核…':'自动规划并校核'):'下一步 →'}}</button>
      </div>
    </form>
    <TransferResults v-else-if="result" :outcome="result" :scene="scene" :mass="form.mass" @back="advance(3)"/>
  </section>
</div></main>
</template>
<style scoped>
.transfer{--line:#cbd9dc;--ink:#1b3741;--quiet:#506970;--plot:#f7faf9;--accent:#126d76;--wash:#a2cfc849;--warm:#a35718;--danger:#ad2a37;--danger-bg:#fff0ef;--tile:white;padding-bottom:12px}
:root[data-theme=dark] .transfer{--line:#44545c;--ink:#e1ebee;--quiet:#b3c3cb;--plot:#202d34;--accent:#83d3c8;--wash:#44766b52;--warm:#efb77e;--danger:#ffabb1;--danger-bg:#442932;--tile:#242e35}
.workflow{display:grid;grid-template-columns:clamp(145px,16vw,210px) minmax(0,1fr);gap:18px;flex:1;min-height:0}
.workflow-nav{align-self:start}.steps{flex-direction:column;gap:8px}.steps button{justify-content:flex-start;padding:10px}
.workflow-panel{min-width:0;overflow:auto}.workflow-panel form{padding:clamp(12px,2vw,24px);background:var(--tile);border:1px solid var(--line);border-radius:16px}
.workflow-panel h2{font-size:24px;letter-spacing:-.03em;margin:0 0 18px}.workflow-panel h2:focus{outline:0}
h3{font-size:15px;margin:0 0 10px}.block{padding:15px;border-radius:12px;border:1px solid var(--line);background:var(--tile);min-width:0}
.columns{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,1fr);gap:14px;margin-top:14px;align-items:start}
.stack{display:grid;gap:12px}.pair,.three,.four{display:grid;gap:6px 12px}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.crane-picker{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.8fr);column-gap:12px}
.config-picker select{text-overflow:ellipsis}
.rating{margin:6px 0 0}.rating strong{color:var(--ink)}
.point-tabs,.actions{display:flex;align-items:center;gap:8px}.point-tabs{margin-bottom:14px}
.point-tabs button[aria-pressed=true]{background:var(--accent);color:var(--tile);border-color:var(--accent)}
.actions{justify-content:flex-end;margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}.actions .primary{margin:0;width:auto;min-width:125px}
.alert,:deep(.field-error){color:var(--danger)}.alert{padding:12px;border-radius:8px}.alert{background:var(--danger-bg);border-left:3px solid var(--danger)}
.workflow-panel :deep(input[aria-invalid=true]){outline-color:var(--danger);border:1.5px solid var(--danger);background:var(--danger-bg)}:deep(.field-error){display:block;font-size:12px}
.split-preview{border-top:1px solid var(--line);padding-top:12px}
.split-preview dl{display:flex;flex-wrap:wrap;gap:8px 24px;margin:0}
.split-preview dt{color:var(--quiet)}.split-preview dd{margin:3px 0 0;font-weight:600;font-variant-numeric:tabular-nums}
.point-editor.invalid{border-color:var(--danger)}
.obstacle{padding-bottom:12px}.muted{color:var(--quiet)}
@media(max-width:920px){.columns{grid-template-columns:1fr}.four{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.workflow{display:flex;flex-direction:column;gap:8px}.workflow-nav{width:100%}.workflow-nav h2{display:none}.steps{flex-direction:row;flex-wrap:wrap}.steps li{flex:auto}.crane-picker{grid-template-columns:1fr}}
</style>
