<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
import Load3D from './Load3D.vue'
import SheetViewer from './SheetViewer.vue'
import type { Snapshot, Model } from './types'
const CadPane = defineAsyncComponent(() => import('./CadPane.vue'))
const theme = ref('light')
watch(theme, value => { document.documentElement.dataset.theme = value }, { immediate: true })
const sheetViewer = ref<InstanceType<typeof SheetViewer>>()
const models = ref<Model[]>([]),
  snapshot = ref<Snapshot | null>(null),
  busy = ref(false),
  notice = ref(''),
  tab = ref('sheet'),
  usedCad = ref(false),
  step = ref(1)
const form = reactive({
  model: 'QY70K-1',
  config: '',
  radiusMode: '最远幅度',
  radius: '10',
  payload: '10',
  hook: '',
  hookChoice: '',
  rigging: '0.3',
  limit: '0.90',
  factor: '1.1',
  length: '6',
  depth: '3',
  loadHeight: '2.5',
  clearance: '1',
  slingHeight: '3.5',
  lugInset: '0',
  cgX: '0',
  cgY: '0',
  cgZ: '0',
})
const choices = computed(() => [...new Set(models.value.map((m) => m.model))]),
  configs = computed(() => models.value.filter((m) => m.model === form.model))
const cap = computed(() => snapshot.value?.cap)
const load = computed(() => snapshot.value?.load)
const activeModel = computed(() => configs.value[0])
const hookOptions = computed(() => activeModel.value?.main_hooks ?? [])
const legacyHook = computed(() => activeModel.value?.hook_main_t)
const customHook = computed(() => !hookOptions.value.length || form.hookChoice === 'manual')
const needsHookMass = computed(() => !!hookOptions.value.length || !legacyHook.value)
const halfLength = computed(() => +form.length / 2)
const halfDepth = computed(() => +form.depth / 2)
const halfHeight = computed(() => +form.loadHeight / 2)
const cg = computed(() => ({ x: +form.cgX || 0, y: +form.cgY || 0, z: +form.cgZ || 0 }))
const geometryReady = computed(
  () => +form.length > 0 && +form.depth > 0 && +form.loadHeight > 0 && +form.payload > 0,
)
const cgInside = computed(
  () =>
    Math.abs(cg.value.x) <= halfLength.value + 1e-9 &&
    Math.abs(cg.value.y) <= halfDepth.value + 1e-9 &&
    Math.abs(cg.value.z) <= halfHeight.value + 1e-9,
)
const geometryIssue = computed(() => {
  if (!geometryReady.value) return '请填写吊物长、宽、高和重量，数值均须大于零。'
  if (!cgInside.value) return '重心超出吊物轮廓，请检查坐标。'
  const inset = +form.lugInset
  if (inset < 0 || inset >= Math.min(halfLength.value, halfDepth.value))
    return '吊点内缩须小于长、宽中较小尺寸的一半，且不能为负。'
  if (Math.abs(cg.value.x) >= halfLength.value - inset || Math.abs(cg.value.y) >= halfDepth.value - inset)
    return '重心水平投影须在四个吊点围成的区域内，请检查重心和吊点内缩。'
  if (form.slingHeight !== '' && +form.slingHeight <= 0) return '请填写正的吊索高度，或留空自动推算。'
  if (form.clearance === '' || +form.clearance < 0) return '请填写非负的吊物底净空。'
  return ''
})
const previewSlingHeight = computed(() => form.slingHeight === ''
  ? Math.hypot(halfLength.value - +form.lugInset - Math.abs(cg.value.x),
               halfDepth.value - +form.lugInset - Math.abs(cg.value.y)) * Math.sqrt(3)
  : +form.slingHeight)
const showResult = computed(() => step.value === 2 && snapshot.value !== null)
const cgFromCentroid = computed(() => Math.hypot(cg.value.x, cg.value.y))
let revision = 0
function showCad() {
  usedCad.value = true
  tab.value = 'cad'
}
watch(
  form,
  () => {
    revision++
    snapshot.value = null
    if (step.value === 2) notice.value = '输入已改变，请重新计算。'
  },
  { flush: 'sync' },
)
watch(
  activeModel,
  () => {
    form.config = ''
    form.hook = ''
    const preset = hookOptions.value.find((hook) => hook.is_default)
    form.hookChoice = preset ? String(preset.mass_t) : ''
  },
  { flush: 'sync' },
)
function goStep(next: number) {
  if (next === 2 && geometryIssue.value) {
    notice.value = geometryIssue.value
    return
  }
  notice.value = ''
  step.value = next
}
async function calculate() {
  const id = revision
  busy.value = true
  notice.value = ''
  try {
    if (geometryIssue.value) {
      notice.value = geometryIssue.value
      step.value = 1
      return
    }
    const mass = customHook.value ? form.hook : form.hookChoice
    if ((mass === '' && needsHookMass.value) || (mass !== '' && !(Number(mass) > 0))) {
      notice.value = customHook.value ? '请按实车铭牌填写吊钩自重（吨）。' : '请选择实车主钩。'
      return
    }
    const data = await window.pywebview!.api.calculate({
      kind: 'crane.capability',
      mode: 'single',
      crane: { model: form.model, brand: configs.value[0]?.brand || '徐工' },
      config: form.config || null,
      payload: +form.payload,
      ...(mass === '' ? {} : { hook_mass: Number(mass) }),
      rigging: +form.rigging,
      limit: +form.limit,
      dynamic_factor: +form.factor,
      target_radius: form.radiusMode === '指定幅度' ? +form.radius : null,
      clearance_m: +form.clearance,
      load: {
        length_m: +form.length,
        width_m: +form.depth,
        height_m: +form.loadHeight,
        lug_inset_m: +form.lugInset || 0,
        sling_height_m: +form.slingHeight > 0 ? +form.slingHeight : null,
        cg: cg.value,
      },
    })
    if (id === revision) {
      snapshot.value = data
      tab.value = 'sheet'
    }
  } catch (e) {
    notice.value = String(e)
    snapshot.value = null
  } finally {
    busy.value = false
  }
}
async function init() {
  try {
    models.value = await window.pywebview!.api.models()
  } catch (e) {
    notice.value = String(e)
  }
}
onMounted(() => {
  if (window.pywebview?.api) void init()
  else window.addEventListener('pywebviewready', init, { once: true })
})
async function save(fmt: string) {
  if (!snapshot.value) return
  try {
    if (await window.pywebview!.api.export(snapshot.value.id, fmt))
      notice.value = '已导出 ' + fmt.toUpperCase()
  } catch (e) {
    notice.value = String(e)
  }
}
</script>
<template>
  <header>
    <b>Liftcalc</b><span class="divider"></span><span>吊装复核工作台</span
    ><small>● 本机离线</small>
    <select class="theme-select" aria-label="界面主题" v-model="theme"><option value="light">浅色</option><option value="dark">深色</option></select>
  </header>
  <main>
    <div class="workspace">
      <div class="inspector">
        <ol class="steps" aria-label="计算步骤">
          <li v-for="item in [{ n: 1, t: '吊物与重心' }, { n: 2, t: '车型与工况' }]" :key="item.n"
              :class="{ active: step === item.n, done: step > item.n }">
            <button type="button" @click="goStep(item.n)"><b>{{ item.n }}</b>{{ item.t }}</button>
          </li>
        </ol>

        <form v-if="step === 1" @submit.prevent="goStep(2)">
          <h2>吊物尺寸与重量</h2>
          <div class="pair">
            <label>长（沿幅度）/ m<input required type="number" step="any" min=".01" v-model="form.length" /></label>
            <label>宽（垂直立面）/ m<input required type="number" step="any" min=".01" v-model="form.depth" /></label>
            <label>高 / m<input required type="number" step="any" min=".01" v-model="form.loadHeight" /></label>
            <label>吊物重量 / t<input required type="number" step="any" min=".001" v-model="form.payload" /></label>
          </div>
          <p class="hint">
            原点在吊物形心。x 沿长度指向远离吊车的一侧，y 沿宽度，z 竖直向上。
          </p>
          <fieldset class="cg-field">
            <legend>重心坐标（相对形心）</legend>
            <div class="pair">
              <label>ex / m<input type="number" step="any" :min="-halfLength" :max="halfLength" v-model="form.cgX" /></label>
              <label>ey / m<input type="number" step="any" :min="-halfDepth" :max="halfDepth" v-model="form.cgY" /></label>
              <label>ez / m<input type="number" step="any" :min="-halfHeight" :max="halfHeight" v-model="form.cgZ" /></label>
              <label>水平偏心 / m<input :value="cgFromCentroid.toFixed(2)" readonly tabindex="-1" /></label>
            </div>
            <p class="muted" :class="{ warn: !cgInside }">
              {{ cgInside ? '水平偏移改变吊钩位置；竖向偏移改变重心标记高度。' : '重心超出吊物轮廓，请检查坐标。' }}
            </p>
          </fieldset>
          <details>
            <summary>吊索与净空</summary>
            <div class="pair">
              <label>吊索竖直高度 / m<input type="number" step="any" placeholder="留空自动推算" v-model="form.slingHeight" /></label>
              <label>吊点内缩 / m<input type="number" step="any" min="0" v-model="form.lugInset" /></label>
              <label>吊物底净空 / m<input required type="number" step="any" min="0" v-model="form.clearance" /></label>
            </div>
            <p class="muted">所需起升高度 = 净空 + 吊物高 + 吊索高，自动推算，无需手工填写。</p>
          </details>
          <button class="primary" :disabled="!!geometryIssue">下一步：选择车型</button>
        </form>

        <form v-else @submit.prevent="calculate">
          <h2>单机车型与工况</h2>
          <p class="summary">
            吊物 {{ form.length }}×{{ form.depth }}×{{ form.loadHeight }} m ·
            {{ form.payload }} t · 重心 ({{ cg.x.toFixed(2) }}, {{ cg.y.toFixed(2) }}, {{ cg.z.toFixed(2) }}) m
            <button type="button" class="link" @click="goStep(1)">修改</button>
          </p>
          <label
            >机型<select v-model="form.model">
              <option v-for="model in choices">{{ model }}</option>
            </select></label
          ><label
            >性能表配置<select v-model="form.config">
              <option value="">比较全部配置</option>
              <option v-for="item in configs" :value="item.config">
                {{ item.config }}
              </option>
            </select></label
          ><label
            >查表方式<select v-model="form.radiusMode">
              <option>最远幅度</option>
              <option>指定幅度</option>
            </select></label
          >
          <label v-if="form.radiusMode === '指定幅度'"
            >指定幅度 / m<input
              required
              type="number"
              step="any"
              min=".001"
              v-model="form.radius"
          /></label>
          <label v-if="hookOptions.length">实车主钩
            <select v-model="form.hookChoice" required>
              <option disabled value="">请选择实车安装的主钩</option>
              <option v-for="hook in hookOptions" :key="hook.mass_t" :value="String(hook.mass_t)">
                {{ hook.rated_t }} t 钩 · 自重 {{ hook.mass_t }} t
              </option>
              <option value="manual">手动填写其他吊钩</option>
            </select>
          </label>
          <div class="pair">
            <label v-if="customHook"
              >吊钩自重 / t<input
                type="number"
                step="any"
                min="0.000001"
                :required="needsHookMass"
                :placeholder="legacyHook ? '默认 ' + legacyHook + ' t' : '按铭牌填写（吨）'"
                v-model="form.hook"
            /></label>
            <label
              >索具 / t<input
                required
                type="number"
                step="any"
                min="0"
                v-model="form.rigging" /></label
            >
          </div>
          <details>
            <summary>系数</summary>
            <div class="pair">
              <label
                >动载系数<input required type="number" step="any" min=".001" v-model="form.factor" /></label
              ><label
                >负荷率上限<input required type="number" step="any" min=".001" max="1" v-model="form.limit" /></label
              >
            </div>
          </details>
          <button class="primary" :disabled="busy || !models.length">
            {{ busy ? '查表中…' : '计算并生成图纸' }}
          </button>
        </form>

        <aside v-if="showResult && snapshot">
          <h2>复核结果</h2>
          <p class="status" :data-state="cap?.status">
            {{ cap?.status || '待计算' }}
          </p>
          <span class="radius-label">采用幅度</span>
          <strong class="metric"
            >{{ cap?.max_radius ?? '—' }} <small>m</small></strong
          >
          <p>{{ cap?.explanation || '等待有效工况' }}</p>
          <dl>
            <dt>采用吊钩自重</dt>
            <dd>{{ cap?.hook_mass || '—' }} t</dd>
            <dt>计算荷载</dt>
            <dd>{{ cap?.required.toFixed(3) ?? '—' }} t</dd>
            <dt>额定载荷</dt>
            <dd>{{ cap?.rated_load ?? '—' }} t</dd>
            <dt>采用臂长</dt>
            <dd>{{ cap?.boom_len ?? '—' }} m</dd>
            <dt>表档起升高度</dt>
            <dd>{{ cap?.lift_height ?? '—' }} m</dd>
            <dt>所需起升高度</dt>
            <dd>{{ load?.required_lift_height_m?.toFixed(2) ?? '—' }} m</dd>
            <dt>最大索力</dt>
            <dd>{{ load?.max_force_t?.toFixed(2) ?? '—' }} t</dd>
            <dt>负荷率</dt>
            <dd>
              {{
                cap?.utilization != null
                  ? (cap.utilization * 100).toFixed(1) + '%'
                  : '—'
              }}
            </dd>
          </dl>
          <p class="muted" v-for="w in snapshot?.warnings">{{ w }}</p>
        </aside>
      </div>
      <section class="stage">
        <nav v-if="showResult && snapshot">
          <button :class="{ active: tab === 'sheet' }" @click="tab = 'sheet'">
            吊装示意</button
          ><button :class="{ active: tab === 'cad' }" @click="showCad">CAD 核图</button>
          <div class="tools exports" aria-label="导出本次工况" role="group">
            <span class="muted">导出本次工况</span>
            <button
              v-for="fmt in ['svg', 'dxf', 'png', 'docx']"
              :key="fmt"
              :disabled="!snapshot || (fmt !== 'docx' && !snapshot.svg)"
              :title="'导出本次工况 ' + fmt.toUpperCase()"
              @click="save(fmt)"
            >{{ fmt.toUpperCase() }}</button>
          </div>
        </nav>
        <nav v-else class="stage-title">
          <strong>货物图 · 尺寸 / 重量 / 重心</strong>
          <span class="muted">第 {{ step }} 步</span>
        </nav>
        <div v-if="showResult && snapshot && tab === 'sheet'" class="paper">
          <button v-if="snapshot?.svg" class="sheet-open" aria-label="放大吊装示意图" title="放大吊装示意图" @click="sheetViewer?.open()" v-html="snapshot.svg"></button>
          <p v-else>尚无可显示的工况立面</p>
        </div>
        <Load3D
          v-else-if="!showResult && !geometryIssue"
          :length="+form.length"
          :width="+form.depth"
          :height="+form.loadHeight"
          :cg="cg"
          :sling-height="previewSlingHeight"
          :inset="+form.lugInset || 0"
          :weight="+form.payload || 0"
        />
        <p v-else-if="!showResult" class="hint" role="status">{{ geometryIssue }}</p>
        <CadPane v-if="usedCad && showResult && snapshot" v-show="tab === 'cad'" :snapshot="snapshot" />
        <div v-if="!showResult || tab === 'sheet'" class="caption">
          {{ showResult && tab === 'sheet'
            ? '点击图纸放大 · A3 立面 · 图示姿态不等于现场净空校核'
            : '固定轴测视图 · 虚线连接吊钩与重心 G' }}
        </div>
      </section>
    </div>
    <p role="status" v-if="notice">{{ notice }}</p>
    <footer>用于专业复核，不作为工程实施依据。</footer>
    <SheetViewer v-if="snapshot?.svg" ref="sheetViewer" :svg="snapshot.svg" />
  </main>
</template>
