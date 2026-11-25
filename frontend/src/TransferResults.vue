<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import SheetViewer from './SheetViewer.vue'
import TransferPlot from './TransferPlot.vue'
import type { TransferEvidence, TransferOutcome, TransferScene } from './types'

const props = defineProps<{outcome: TransferOutcome; scene: TransferScene; mass: number}>()
const emit = defineEmits<{back: []}>()
type Severity = 'fail' | 'pending'
type Issue = {
  id: string
  reason: string
  level: Severity
  start: number
  end: number
  firstLeg: number
  lastLeg: number
  evidence?: TransferEvidence
}
const labels = {fail: '不通过', pending: '待核', pass: '已核项全段满足'}
const plan = computed(() => props.outcome.status === 'planned' ? props.outcome : undefined)
const segments = computed(() => plan.value?.segments ?? [])
const issues = computed(() => {
  const all: Issue[] = []
  const previous = new Map<string, Issue>()
  for (const s of segments.value) {
    for (const level of ['fail', 'pending'] as const) {
      for (const reason of new Set(level === 'fail' ? s.unsafe : s.unknown)) {
        const key = level + reason
        const last = previous.get(key)
        const evidence = s.evidence?.[reason]
        if (last && last.end === s.start) {
          last.end = s.end
          last.lastLeg = s.leg
          if (!last.evidence || (last.evidence.progress === null && evidence?.progress != null)) last.evidence = evidence
        } else {
          const issue = {id: key + s.start, reason, level, start: s.start, end: s.end,
            firstLeg: s.leg, lastLeg: s.leg, evidence}
          previous.set(key, issue)
          all.push(issue)
        }
      }
    }
  }
  return all
})
const failures = computed(() => issues.value.filter(issue => issue.level === 'fail'))
const pending = computed(() => issues.value.filter(issue => issue.level === 'pending'))
const verdict = computed(() => failures.value.length ? 'fail' : pending.value.length ? 'pending' : 'pass')
const bands = computed(() => {
  const out: {start: number; end: number; level: keyof typeof labels}[] = []
  for (const s of segments.value) {
    const level = s.unsafe.length ? 'fail' : s.unknown.length ? 'pending' : 'pass'
    const last = out.at(-1)
    if (last?.level === level) last.end = s.end
    else out.push({start: s.start, end: s.end, level})
  }
  return out
})
const cranes = computed(() => ['A', 'B'].map((name, i) => {
  const ratios = segments.value.flatMap(s => s.ratios[i] == null ? [] : [s.ratios[i]!])
  return {name, peakRatio: ratios.length ? Math.max(...ratios) : null,
    maxRadius: Math.max(...segments.value.map(s => s.radii[i][1]))}
}))
const drawings = computed(() => [...(plan.value?.drawings ?? [])].sort(
  (a, b) => Number(b.kind === 'trajectory') - Number(a.kind === 'trajectory'),
))
const filter = ref<'all' | Severity>('all')
const pageSize = 20
const visibleCount = ref(pageSize)
const filtered = computed(() => filter.value === 'fail' ? failures.value : filter.value === 'pending' ? pending.value
  : [...failures.value, ...pending.value])
function setFilter(value: typeof filter.value) {
  filter.value = value
  visibleCount.value = pageSize
}
const plot = ref<InstanceType<typeof TransferPlot>>()
const selected = ref<Issue>()
function locate(issue: Issue) {
  selected.value = issue
  plot.value?.seek(issue.evidence?.progress ?? (issue.start + issue.end) / 2)
  if (window.matchMedia('(max-width: 1050px)').matches) {
    plot.value?.$el.scrollIntoView({block: 'nearest'})
  }
}
onMounted(() => {
  const first = failures.value[0] ?? pending.value[0]
  if (first) {
    selected.value = first
    plot.value?.seek(first.evidence?.progress ?? (first.start + first.end) / 2)
  }
})
const percent = (n: number) => (100*n).toFixed(2) + '%'
const interval = (start: number, end: number) => percent(start) + '–' + percent(end)
const down = (n: number) => (Math.floor(1000*n)/1000).toFixed(3)
const up = (n: number) => (Math.ceil(100*n)/100).toFixed(2)
const activeSheet = ref(''), exportError = ref('')
const viewer = ref<InstanceType<typeof SheetViewer>>()
async function openSheet(svg: string) {
  activeSheet.value = svg
  await nextTick()
  viewer.value?.open()
}
async function save(id: string) {
  exportError.value = ''
  try { await window.pywebview!.api.export(id, 'dxf') }
  catch (e) { exportError.value = String(e) }
}
</script>

<template>
<section class="transfer-output">
  <header class="results-heading">
    <h2 tabindex="-1">双机抬吊上轨校核结果</h2>
    <button type="button" @click="emit('back')">返回转运与场地</button>
  </header>

  <template v-if="plan">
    <div class="decision" :data-status="verdict">
      <strong>{{labels[verdict]}}</strong>
      <span v-if="issues.length">{{failures.length}} 处不通过 · {{pending.length}} 处待核</span>
      <span v-else>{{plan.poses.length-1}} 段路径 · {{segments.length}} 个校核区间</span>
    </div>
    <div class="metrics">
      <section v-for="(crane,i) in cranes" :key="crane.name" class="metric">
        <h3>{{crane.name}} 机计算总起重量</h3>
        <div class="metric-value">{{plan.loads[i].toFixed(2)}} <small>t</small></div>
        <p>分担的吊物质量 {{(mass * plan.shares[i]).toFixed(2)}} t（{{(plan.shares[i] * 100).toFixed(1)}}%）</p>
        <p>工作幅度上界 {{up(crane.maxRadius)}} m</p>
        <p>涉及表列工况的最高负荷率
          <b :data-status="crane.peakRatio != null && crane.peakRatio > plan.load_limit ? 'fail' : undefined">
            {{crane.peakRatio == null ? '无数据' : (100*crane.peakRatio).toFixed(1)+'%'}}
          </b> · 上限 {{(100*plan.load_limit).toFixed(0)}}%
        </p>
      </section>
      <section class="metric">
        <h3>全程水平净距下界</h3>
        <div class="metric-value">{{down(plan.clearance.lower_m)}} <small>m</small></div>
        <p>要求至少 {{plan.required_clearance.toFixed(3)}} m</p>
        <p>{{plan.clearance.pair}}</p>
        <p>P{{plan.clearance.leg-1}} → P{{plan.clearance.leg}} · {{interval(plan.clearance.start, plan.clearance.end)}}</p>
      </section>
    </div>
    <div class="inspection">
      <section class="route">
        <h3>轨迹回放</h3>
        <div class="progress-track" aria-hidden="true">
          <span v-for="b in bands" :key="b.start" :data-status="b.level" :style="{flex: b.end-b.start}"></span>
        </div>
        <div class="progress-key"><span>P0 · 起吊</span><span>P{{plan.poses.length-1}} · 落位</span></div>
        <div class="progress-legend"><span data-status="pass">已核项满足</span>
          <span v-if="failures.length" data-status="fail">不通过</span><span v-if="pending.length" data-status="pending">待核</span>
        </div>
        <p v-if="selected" class="located" :data-status="selected.level" aria-live="polite">
          已定位 {{selected.reason}} · {{percent(selected.evidence?.progress ?? (selected.start+selected.end)/2)}}
          {{selected.evidence?.progress == null ? '（区间中点）' : ''}}
        </p>
        <TransferPlot ref="plot" v-bind="scene" site preview :critical-progress="(plan.clearance.start+plan.clearance.end)/2"/>
      </section>
      <section class="review">
        <h3>不通过与待核明细</h3>
        <template v-if="issues.length">
          <div class="filters" role="group" aria-label="按校核状态筛选">
            <button type="button" :aria-pressed="filter==='all'" @click="setFilter('all')">全部 {{issues.length}}</button>
            <button type="button" :aria-pressed="filter==='fail'" @click="setFilter('fail')">不通过 {{failures.length}}</button>
            <button type="button" :aria-pressed="filter==='pending'" @click="setFilter('pending')">待核 {{pending.length}}</button>
          </div>
          <ul v-if="filtered.length" class="issues">
            <li v-for="issue in filtered.slice(0, visibleCount)" :key="issue.id">
              <button type="button" class="issue" :data-status="issue.level"
                :aria-pressed="selected?.id===issue.id" @click="locate(issue)">
                <span class="issue-heading"><strong>{{issue.reason}}</strong><span>{{labels[issue.level]}}</span></span>
                <span class="where">P{{issue.firstLeg-1}} → P{{issue.lastLeg}} · {{interval(issue.start, issue.end)}}</span>
                <span v-if="issue.evidence?.progress != null" class="where">记录位置 {{percent(issue.evidence.progress)}}</span>
                <span v-if="issue.evidence">{{issue.evidence.text}}</span>
                <span class="jump">定位到回放 →</span>
              </button>
            </li>
          </ul>
          <p v-else class="quiet">当前筛选没有记录。</p>
          <button v-if="filtered.length > visibleCount" type="button" @click="visibleCount += pageSize">显示更多（还有 {{filtered.length-visibleCount}} 条）</button>
        </template>
        <p v-else class="quiet">各校核区间均满足本次计算的承载、工作幅度和水平净距要求。</p>
      </section>
    </div>
    <details class="metric stations">
      <summary>起重机站位与吊物姿态</summary>
      <p v-for="(c,i) in plan.stations" :key="i">{{'AB'[i]}} 机回转中心（{{c.center.map(x=>x.toFixed(2)).join(', ')}}）m · 占地包络长轴方向角 {{c.heading.toFixed(1)}}°</p>
      <p v-for="(p,i) in plan.poses" :key="i">P{{i}}　（{{p.slice(0,2).map(x=>x.toFixed(2)).join(', ')}}）m · 吊物纵轴方向角 {{p[2].toFixed(1)}}°</p>
    </details>
    <h3 class="drawings-heading">图纸</h3>
    <div class="sheets">
      <section v-for="d in drawings" :key="d.id" class="metric" :class="{trajectory:d.kind==='trajectory'}">
        <header><h4>{{d.title}}</h4><button type="button" @click="save(d.id)">导出 DXF</button></header>
        <div class="paper"><button type="button" class="sheet-open" :aria-label="'放大'+d.title" @click="openSheet(d.svg)" v-html="d.svg"></button></div>
      </section>
    </div>
    <SheetViewer ref="viewer" :svg="activeSheet"/>
    <p v-if="exportError" data-status="fail" role="alert">{{exportError}}</p>
    <p class="quiet">双机校核范围为起重性能表负荷率、主吊钩组承载、工作幅度和水平净距。图纸中的吊钩与离地高度仅用于示意。起升高度、起重臂间三维净距、吊索干涉、允许作业区域、双机不同步引起的倾斜、地基承载力及起升与下放过程需另行校核。</p>
  </template>

  <template v-else-if="outcome.status==='unplanned'">
    <div class="decision" data-status="fail"><strong>本次搜索未生成可用轨迹</strong><span>{{outcome.summary}}</span></div>
    <div class="inspection">
      <section class="route"><h3>起吊与落位</h3><TransferPlot v-bind="scene" site/></section>
      <section v-if="outcome.reasons.length" class="review"><h3>搜索时记录的阻碍</h3>
        <ul class="search-reasons"><li v-for="reason in outcome.reasons" :key="reason">{{reason}}</li></ul>
      </section>
    </div>
  </template>
</section>
</template>

<style scoped>
.transfer-output{padding:clamp(12px,2vw,24px);background:var(--tile);border:1px solid var(--line);border-radius:16px}
.results-heading,.sheets header,.issue-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}
.results-heading,.sheets header{padding:0;border:0;background:none}
.results-heading{margin-bottom:16px;flex-wrap:wrap}.results-heading h2{font-size:24px;letter-spacing:-.03em;margin:0;outline:0}
h3{font-size:15px;margin:0 0 10px}h4{font-size:14px;margin:0}
.decision{display:flex;flex-wrap:wrap;align-items:center;gap:7px 16px;padding:13px 16px;border-radius:10px;border-inline-start:4px solid currentColor;background:var(--wash);color:var(--accent)}
.decision strong{font-size:17px}.decision span{font-size:13px}.decision[data-status=fail]{background:var(--danger-bg)}
[data-status=fail]{color:var(--danger)}[data-status=pending]{color:var(--warm)}
.metrics,.inspection,.sheets{display:grid;gap:12px;margin-top:14px}.metrics{grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr))}
.metric,.review,.route{padding:13px;border:1px solid var(--line);border-radius:12px;min-width:0}
.metric-value{font-size:26px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}.metric-value small{font-size:13px}
.metric p,.quiet{font-size:13px;color:var(--quiet)}.metric p{margin:6px 0 0}
.inspection{grid-template-columns:minmax(0,1.55fr) minmax(290px,1fr);align-items:start}
.progress-track{height:7px;border-radius:6px;overflow:hidden;display:flex;background:var(--wash)}
.progress-track span{background:var(--accent)}.progress-track [data-status=fail]{background:var(--danger)}.progress-track [data-status=pending]{background:var(--warm)}
.progress-key{display:flex;justify-content:space-between;font-size:12px;color:var(--quiet);margin:5px 0 10px}
.progress-legend{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:12px;margin-bottom:8px}
.progress-legend [data-status=pass]{color:var(--accent)}.progress-legend span::before{content:'';display:inline-block;height:7px;width:7px;margin-right:5px;background:currentColor;border-radius:50%}
.located{font-size:13px;margin:8px 0}
.filters{display:flex;gap:6px;flex-wrap:wrap}.filters button{font-size:12px}.filters [aria-pressed=true]{border-color:var(--accent);color:var(--accent);background:var(--wash)}
.issues{list-style:none;padding:0;margin:10px 0;display:grid;gap:8px;max-height:460px;overflow:auto}
.issue{display:grid;gap:5px;text-align:left;width:100%;min-width:0;padding:10px;border-inline-start:3px solid var(--issue-tone);background:var(--tile);font-size:13px;line-height:1.45}
.issue[data-status=fail]{--issue-tone:var(--danger)}.issue[data-status=pending]{--issue-tone:var(--warm)}
.issue[aria-pressed=true]{background:var(--wash);box-shadow:inset 0 0 0 1px currentColor}
.issue-heading span{color:var(--issue-tone);font-size:11px;white-space:nowrap}.issue > span:not(.issue-heading){color:var(--ink)}
.issue > .where{font-variant-numeric:tabular-nums}.issue > .jump{font-size:12px;color:var(--accent)}
.search-reasons{padding-inline-start:19px;margin:0;display:grid;gap:10px}
.stations{margin-top:14px}.drawings-heading{margin:18px 0 0}.sheets{grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))}
.sheets .trajectory{grid-column:1/-1}.sheets .paper{margin-top:9px;height:auto;aspect-ratio:420/297;padding:2px}
.sheets .trajectory .paper{aspect-ratio:auto;height:clamp(250px,56vh,740px)}.sheets .sheet-open{display:block}
@media(max-width:1050px){.inspection{grid-template-columns:1fr}.issues{max-height:330px}}
</style>
