<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { Model, TransferResult } from './types'
import SheetViewer from './SheetViewer.vue'

import TransferPlot from './TransferPlot.vue'
import RiggingHeight from './RiggingHeight.vue'
import { riggingRise, type RiggingMeasurement } from './riggingHeight'
import NumberEntry from './NumberEntry.vue'

const props = defineProps<{models: Model[]}>()
const form = reactive({
  length: 12, width: 3, height: 3, mass: 16, cg: [0,0,0], lugs: [[-5,0],[5,0]],
  start: [-11,0,90], auto_route: true, auto_stations: true, end: [11,0,90], bottom: 1, factor: 1.1, gauge: 1.435,
  cranes: [-1,1].map(sign => ({index: -1, boom: 0, center: [0,sign*5.5], footprint_length: 10, footprint_width: 5, heading: 0, boom_buffer: 1,
    hook: null as number|null, hook_rating: null as number|null, rigging: 0.3, sling: {datum:'top',value:null} as RiggingMeasurement,
    verified_height: null as number|null})),
  obstacles: [] as number[][],
})
const active = ref(0), pick = ref(0), busy = ref(false), error = ref('')
const result = ref<TransferResult>(), viewer = ref<InstanceType<typeof SheetViewer>>()
const points = computed(() => [...form.lugs,form.cg])
const stages = ['吊物与吊点', 'A 机工况', 'B 机工况', '转向与场地', '图纸与校核']
const step = ref(0), reached = ref(0)
const crane = computed(() => form.cranes[step.value-1])
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
  if (step.value===0 && (geometryError.value || form.cranes.some(c=>(riggingRise(c.sling,form.height) ?? 0)<=0))) return
  if (target === 4 && !result.value) { void calculate(); return }
  goto(target)
}
watch(form, () => { revision++; reached.value = Math.min(reached.value, step.value); result.value = undefined; error.value = '' }, {flush:'sync'})
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
const geometryError = computed(() => {
  const [[ax,ay],[bx,by]]=form.lugs, [gx,gy,gz]=form.cg
  for(const [i,p] of points.value.entries()){
    if(p.some(v=>!Number.isFinite(v)) || Math.abs(p[0])>form.length/2 || Math.abs(p[1])>form.width/2)
      return 'ABG'[i]+' 点坐标超出顶面或有空值，请选择该点修正坐标。'
  }
  if(Math.abs(gz)>=form.height/2) return 'G 点 Z 坐标须在吊物上下表面之间。'
  const dx=bx-ax,dy=by-ay,span=Math.hypot(dx,dy)
  if(span<1e-6) return 'A、B 吊点重合，请移动一个吊点。'
  const projection=(gx-ax)*dx+(gy-ay)*dy
  if(Math.abs((gx-ax)*dy-(gy-ay)*dx)>1e-8*span || projection<=0 || projection>=span**2)
    return '重心投影须位于 A、B 连线的两个端点之间。'
  return ''
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
    const offset = (form.width/2+c.footprint_width/2+.35)*sign*(i===0?-1:1)
    return {...c,center:[(ax+bx)/2+offset*nx,(ay+by)/2+offset*ny],heading:heading*180/Math.PI}
  })
})
const scene=computed(()=>({
  length:form.length,width:form.width,points:points.value,pick:pick.value,gauge:form.gauge,
  cranes:result.value ? form.cranes.map((c,i)=>({...c,...result.value!.stations[i]}))
    : previewStations.value,
  provisional:form.auto_stations && !result.value,
  poses:result.value?.poses ?? [form.start,form.end],obstacles:form.obstacles,
}))
const runs=computed(()=>{
  const out:{start:number;end:number;text:string;level:string;leg:number}[]=[]
  for(const s of result.value?.segments ?? []){
    const text=[...s.unsafe,...s.unknown].join('、') || '已核项满足'
    const last=out[out.length-1]
    if(last?.text===text && last.leg===s.leg) last.end=s.end
    else out.push({start:s.start,end:s.end,leg:s.leg,text,level:s.unsafe.length?'fail':s.unknown.length?'pending':'pass'})
  }
  return out
})
async function calculate() {
  const id=revision
  busy.value=true; error.value=''
  try {
    const cranes=form.cranes.map(({index,center,heading,sling,...c})=>{
      const m=props.models[index]
      return {...c,sling_height:riggingRise(sling,form.height), ...(form.auto_stations?{}:{center,heading}), verified_height:c.verified_height || null,model:m.model,brand:m.brand,config:m.config}
    })
    const data=await window.pywebview!.api.calculate({kind:'rail.transfer',transfer:{...form,cranes}})
    if(id===revision){result.value=data;active.value=0;goto(4)}
  } catch(e){if(id===revision) error.value=String(e)}
  finally {busy.value=false}
}
async function openSheet(i:number){
  active.value=i
  await nextTick()
  viewer.value?.open()
}
async function save(i:number){
  if(!result.value) return
  try {await window.pywebview!.api.export(result.value.drawings[i].id,'dxf')}
  catch(e){error.value=String(e)}
}
const sizeFields = {length:'长 / m', width:'宽 / m', height:'高 / m', mass:'质量 / t'} as const
const verdict=computed(()=>result.value?.segments.some(s=>s.unsafe.length)?'fail':result.value?.segments.some(s=>s.unknown.length)?'pending':'pass')
const craneFields=['boom_buffer','hook','hook_rating','rigging','verified_height'] as const
const craneLabels=['臂投影包络半宽 / m','主钩自重 / t','主钩额载 / t','本侧索具 / t','全段已核实可用钩高下限 / m（选填）']
</script>
<template>
<main class="transfer"><div class="workflow">
  <aside class="workflow-nav">
    <h2>双机上轨</h2>
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
        <div class="pair">
          <RiggingHeight v-for="(c,i) in form.cranes" :key="i" v-model="c.sling"
            :label="('AB'[i])+' 侧索具捆扎后高度'" :body-height="form.height" :attempted="attempted"/>
        </div>
        <div class="columns">
          <TransferPlot v-bind="scene" @place="place"/>
          <section class="block point-editor" :class="{invalid:geometryError}"><h3>选择编辑点</h3>
            <div class="point-tabs"><button v-for="(tag,i) in ['吊点 A','吊点 B','重心 G']" :key="tag" type="button" :aria-pressed="pick===i" @click="pick=i">{{tag}}</button></div>
            <div class="pair"><NumberEntry v-for="(_,k) in points[pick]" :key="pick+'-'+k" v-model="points[pick][k]" :label="'局部 '+ 'XYZ'[k]+' / m'" :min="-[form.length,form.width,form.height][k]/2" :max="[form.length,form.width,form.height][k]/2" :attempted="attempted"/></div>
            <label v-if="pick===2"><input type="checkbox" v-model="snap"> 点选时吸附至 AB 连线</label>
            <p class="muted">点击图中顶面定位，或输入坐标微调。Z 从形心向上量取。</p>
            <p v-if="geometryError" class="alert" role="alert">{{geometryError}}</p>
          </section>
        </div>
      </template>
      <template v-if="step===1 || step===2">
        <section class="block"><h3>车型与配置</h3><div class="pair">
          <label>车型及工况<select :value="crane.index" @change="selectModel(step-1,Number(($event.target as HTMLSelectElement).value))"><option v-for="(m,j) in models" :key="j" :value="j">{{m.brand}} {{m.model}} · {{m.config}}</option></select></label>
          <label>固定臂长 / m<select v-model.number="crane.boom"><option v-for="b in models[crane.index]?.booms" :key="b" :value="b">{{b}}</option></select></label>
        </div></section>
        <div class="columns" :key="step">
          <div class="stack"><TransferPlot v-bind="scene" site :focus="step-1"/>
            <section class="block"><h3>矩形占地包络</h3>
              <div class="pair">
                <NumberEntry v-model="crane.footprint_length" label="占地长 / m" :min=".000001" :attempted="attempted"/>
                <NumberEntry v-model="crane.footprint_width" label="占地宽 / m" :min=".000001" :attempted="attempted"/>
              </div>
              <p class="muted">以回转中心为中心，长宽须覆盖车体及展开支腿。初始尺寸为示例。自动站位须复核场地边界及地基。</p>
              <label><input type="checkbox" v-model="form.auto_stations"> 自动搜索两机站位（全程固定）</label>
              <div v-if="!form.auto_stations" class="three">
                <NumberEntry v-for="(_,k) in crane.center" :key="k" v-model="crane.center[k]" :label="'实测中心 '+'XY'[k]+' / m'" :attempted="attempted"/>
                <NumberEntry v-model="crane.heading" label="长轴航向 / °" :attempted="attempted"/>
              </div>
            </section></div>
          <section class="block"><h3>作业包络与吊具</h3><div class="pair">
            <NumberEntry v-for="(key,k) in craneFields" :key="key" v-model="crane[key]" :label="craneLabels[k]" :min="key==='rigging'?0:.000001" :optional="key==='verified_height'" :attempted="attempted"/>
          </div></section>
        </div>
      </template>
      <template v-if="step===3">
        <div class="columns"><div class="stack">
          <TransferPlot v-bind="scene" site :preview="!!result"/>
          <p class="muted">根据起吊、落位、占地及障碍搜索中间姿态；规划完成后可慢速预演。</p>
          <section class="block"><h3>场地禁入圆</h3>
            <div v-for="(o,i) in form.obstacles" :key="i" class="obstacle"><div class="three"><NumberEntry v-for="(_,k) in o" :key="k" v-model="o[k]" :label="['X / m','Y / m','半径 / m'][k]" :min="k===2?.000001:undefined" :attempted="attempted"/></div><button type="button" @click="form.obstacles.splice(i,1)">移除障碍 {{i+1}}</button></div>
            <button type="button" @click="form.obstacles.push([0,0,1])">＋ 添加障碍</button>
          </section></div>
          <div class="stack">
            <section v-for="(p,i) in [form.start,form.end]" :key="i" class="block"><h3>{{i?'对轨落位':'起吊位置'}}</h3><div class="three">
              <NumberEntry v-for="(_,k) in p" :key="k" v-model="p[k]" :label="['中心 X / m','中心 Y / m','航向 / °'][k]" :attempted="attempted"/>
            </div></section>
            <section class="block"><h3>转运条件</h3><div class="pair">
              <NumberEntry v-model="form.bottom" label="底面离地 / m" :min=".000001" :attempted="attempted"/>
              <NumberEntry v-model="form.factor" label="载荷放大系数" :min="1" :attempted="attempted"/>
              <NumberEntry v-model="form.gauge" label="目标轨距 / m" :min=".000001" :attempted="attempted"/>
            </div><p class="muted">按现场填写起止姿态；程序自动计算中间的平移与转角。</p></section>
          </div></div>
      </template>
      <p v-if="error" class="alert" role="alert">{{error}}</p>
      <div class="actions"><button v-if="step>0" type="button" :disabled="busy" @click="advance(step-1)">上一步</button>
        <button class="primary" :disabled="busy || ((step===1 || step===2) && !models.length)">{{step===3?(busy?'正在搜索与校核…':'自动规划并校核'):'下一步 →'}}</button>
      </div>
    </form>
    <div v-else-if="result" class="transfer-output"><h2 tabindex="-1">图纸与校核</h2>
      <div class="decision" :data-status="verdict"><strong>{{ {fail:'存在超限或禁入区相交',pending:'存在待核区间',pass:'所列校核项全段满足'}[verdict] }}</strong><span>A / B 计算总吊重　{{result.loads.map(x=>x.toFixed(2)).join(' / ')}} t</span></div>
      <p v-if="verdict!=='pass'" class="muted">以下为几何候选路径，仍有超限或待核项。</p>
      <div class="sheets">
        <section v-for="(d,i) in result.drawings" :key="d.id" class="block">
          <header><h3>{{i===0?'静力分析':'俯视转向轨迹'}}</h3><button @click="save(i)">导出 DXF</button></header>
          <div class="paper"><button class="sheet-open" :aria-label="i===0?'放大静力分析图':'放大轨迹图'" @click="openSheet(i)" v-html="d.svg"></button></div>
        </section>
      </div>
      <SheetViewer ref="viewer" :svg="result.drawings[active].svg"/>
      <div class="columns result-layout">
      <details class="block"><summary>自动规划的站位与调姿 · {{result.poses.length-1}} 段</summary>
        <TransferPlot v-bind="scene" site preview/>
        <p v-for="(c,i) in result.stations" :key="i">{{'AB'[i]}} 机中心 ({{c.center.map(x=>x.toFixed(2)).join(', ')}}) m · 长轴 {{c.heading.toFixed(1)}}°</p>
        <p v-for="(p,i) in result.poses" :key="i">P{{i}}　({{p.slice(0,2).map(x=>x.toFixed(2)).join(', ')}}) m · {{p[2].toFixed(1)}}°</p>
      </details>
        <div class="stack"><section v-for="(_,i) in form.cranes" :key="i" class="block"><h3>{{'AB'[i]}} 机校核</h3>
          <p>幅度包络　{{Math.min(...result.segments.map(s=>s.radii[i][0])).toFixed(2)}}–{{Math.max(...result.segments.map(s=>s.radii[i][1])).toFixed(2)}} m</p>
          <p>已覆盖档最高负荷率　{{result.segments.some(s=>s.ratios[i]!==null)?(100*Math.max(...result.segments.map(s=>s.ratios[i]??0))).toFixed(1)+'%':'无数据'}}</p></section>
          <details class="block"><summary>分段校核明细（{{runs.length}}）</summary><p v-for="r in runs" :key="r.start" :data-status="r.level">P{{r.leg-1}} → P{{r.leg}}　{{(100*r.start).toFixed(2)}}% – {{(100*r.end).toFixed(2)}}%　{{r.text}}</p></details></div></div>
      <p v-if="error" class="alert" role="alert">{{error}}</p>
      <p class="muted">校核范围为表档载荷、钩载、所填钩高及平面禁入区。臂间三维净空、索间干涉、回转扇区、不同步倾斜、地基与起落段需另行复核。</p>
      <button @click="advance(3)">返回转向与场地</button>
    </div>
  </section>
</div></main>
</template>
<style scoped>
.transfer{--line:#cbd9dc;--ink:#1b3741;--quiet:#506970;--plot:#f7faf9;--accent:#126d76;--wash:#a2cfc849;--warm:#a35718;--danger:#ad2a37;--danger-bg:#fff0ef;--tile:white;padding-bottom:12px}
:root[data-theme=dark] .transfer{--line:#44545c;--ink:#e1ebee;--quiet:#b3c3cb;--plot:#202d34;--accent:#83d3c8;--wash:#44766b52;--warm:#efb77e;--danger:#ffabb1;--danger-bg:#442932;--tile:#242e35}
.workflow{display:grid;grid-template-columns:clamp(145px,16vw,210px) minmax(0,1fr);gap:18px;flex:1;min-height:0}
.workflow-nav{align-self:start}.steps{flex-direction:column;gap:8px}.steps button{justify-content:flex-start;padding:10px}
.workflow-panel{min-width:0;overflow:auto}.workflow-panel form,.transfer-output{padding:clamp(12px,2vw,24px);background:var(--tile);border:1px solid var(--line);border-radius:16px}
.workflow-panel h2{font-size:24px;letter-spacing:-.03em;margin:0 0 18px}.workflow-panel h2:focus{outline:0}
h3{font-size:15px;margin:0 0 10px}.block{padding:15px;border-radius:12px;border:1px solid var(--line);background:var(--tile);min-width:0}
.columns{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,1fr);gap:14px;margin-top:14px;align-items:start}
.stack{display:grid;gap:12px}.pair,.three,.four{display:grid;gap:6px 12px}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.point-tabs,.actions,.decision{display:flex;align-items:center;gap:8px}.point-tabs{margin-bottom:14px}
.point-tabs button[aria-pressed=true]{background:var(--accent);color:var(--tile);border-color:var(--accent)}
.actions{justify-content:flex-end;margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}.actions .primary{margin:0;width:auto;min-width:125px}
.alert,[data-status=fail],:deep(.field-error){color:var(--danger)}.alert,.decision{padding:12px;border-radius:8px}.alert,.decision[data-status=fail]{background:var(--danger-bg);border-left:3px solid var(--danger)}
.workflow-panel :deep(input[aria-invalid=true]){outline-color:var(--danger);border:1.5px solid var(--danger);background:var(--danger-bg)}:deep(.field-error){display:block;font-size:12px}
.point-editor.invalid{border-color:var(--danger)}
.decision{justify-content:space-between;background:var(--wash);flex-wrap:wrap}.decision[data-status=pending],[data-status=pending]{color:var(--warm)}
.sheets{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:12px;margin-top:12px}.sheets .block{padding:10px}.sheets header{display:flex;align-items:center;justify-content:space-between}.sheets h3{margin:0}.sheets .paper{height:auto;aspect-ratio:420/297;padding:2px}.sheets .sheet-open{display:block}.result-layout{grid-template-columns:minmax(0,1.7fr) minmax(230px,1fr)}.paper{height:clamp(250px,49vh,580px);margin-top:12px}
.pose-tools{display:flex;gap:8px;margin-top:8px}.obstacle{padding-bottom:12px}.transfer-output nav{flex-wrap:wrap}.muted{color:var(--quiet)}
@media(max-width:920px){.columns{grid-template-columns:1fr}.four{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.workflow{display:flex;flex-direction:column;gap:8px}.workflow-nav{width:100%}.workflow-nav h2{display:none}.steps{flex-direction:row;flex-wrap:wrap}.steps li{flex:auto}}
</style>
