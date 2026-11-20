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
const theme = ref('refract')
watch(theme, value => { document.documentElement.dataset.theme = value }, { immediate: true })
const sheetViewer = ref<InstanceType<typeof SheetViewer>>()
const models = ref<Model[]>([]),
  snapshot = ref<Snapshot | null>(null),
  busy = ref(false),
  notice = ref(''),
  tab = ref('sheet'),
  usedCad = ref(false),
  step = ref(1),
  mode = ref<'single' | 'dual'>('single')
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
const halfLength = computed(() => Math.max(0.05, +form.length / 2 || 0.05))
const halfDepth = computed(() => Math.max(0.05, +form.depth / 2 || 0.05))
const halfHeight = computed(() => Math.max(0.05, +form.loadHeight / 2 || 0.05))
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
    if (step.value === 3) notice.value = '输入已改变，请重新计算。'
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
  if (next > step.value) {
    if (step.value === 1 && !geometryReady.value) {
      notice.value = '请先填写吊物尺寸与重量（均为正数）。'
      return
    }
    if (step.value === 1 && !cgInside.value) {
      notice.value = '重心坐标超出吊物轮廓，请按相对形心的实际位置填写。'
      return
    }
    if (step.value === 2 && !geometryReady.value) {
      notice.value = '吊物参数不完整，请回到第一步。'
      return
    }
  }
  notice.value = ''
  step.value = next
}
function goToCrane() {
  goStep(3)
}
async function calculate() {
  const id = revision
  busy.value = true
  notice.value = ''
  try {
    if (!geometryReady.value) {
      notice.value = '吊物尺寸与重量必须为正。'
      step.value = 1
      return
    }
    if (!cgInside.value) {
      notice.value = '重心坐标超出吊物轮廓，请按相对形心的实际位置填写。'
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
      mode: mode.value,
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
      step.value = 3
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
    <select class="theme-select" aria-label="界面主题" v-model="theme"><option value="refract">Refract</option><option value="dusk">Dusk</option></select>
  </header>
  <main>
    <div class="workspace">
      <div class="inspector">
        <ol class="steps" aria-label="计算步骤">
          <li v-for="item in [{ n: 1, t: '吊物' }, { n: 2, t: '双机' }, { n: 3, t: '车型' }]" :key="item.n"
              :class="{ active: step === item.n, done: step > item.n }">
            <button type="button" @click="goStep(item.n)"><b>{{ item.n }}</b>{{ item.t }}</button>
          </li>
        </ol>

        <form v-if="step === 1" @submit.prevent="goStep(2)">
          <h2>① 吊物尺寸与重量</h2>
          <div class="pair">
            <label>长（沿幅度）/ m<input required type="number" step="any" min=".01" v-model="form.length" /></label>
            <label>宽（垂直立面）/ m<input required type="number" step="any" min=".01" v-model="form.depth" /></label>
            <label>高 / m<input required type="number" step="any" min=".01" v-model="form.loadHeight" /></label>
            <label>吊物重量 / t<input required type="number" step="any" min=".001" v-model="form.payload" /></label>
          </div>
          <p class="hint">
            右侧已按真实尺寸生成三维货物图（带坐标系）。原点在形心：x 沿长度、指向远离吊车，y 沿宽度，z 竖向。
            请在下方填写重心坐标（相对形心）。
          </p>
          <fieldset class="cg-field">
            <legend>② 重心坐标（相对形心）</legend>
            <div class="pair">
              <label>ex / m<input type="number" step="0.05" :min="-halfLength" :max="halfLength" v-model="form.cgX" /></label>
              <label>ey / m<input type="number" step="0.05" :min="-halfDepth" :max="halfDepth" v-model="form.cgY" /></label>
              <label>ez / m<input type="number" step="0.05" :min="-halfHeight" :max="halfHeight" v-model="form.cgZ" /></label>
              <label>水平偏心 / m<input :value="cgFromCentroid.toFixed(2)" readonly tabindex="-1" /></label>
            </div>
            <p class="muted" :class="{ warn: !cgInside }">
              {{ cgInside ? '重心落在吊物轮廓内。偏心时四根吊索受力不均，双机抬吊也按重心位置分载。' : '重心超出吊物轮廓，请检查坐标。' }}
            </p>
          </fieldset>
          <details>
            <summary>吊索与净空</summary>
            <div class="pair">
              <label>吊索竖直高度 / m<input type="number" step="any" min=".1" v-model="form.slingHeight" /></label>
              <label>吊点内缩 / m<input type="number" step="any" min="0" v-model="form.lugInset" /></label>
              <label>吊物底净空 / m<input required type="number" step="any" min="0" v-model="form.clearance" /></label>
            </div>
            <p class="muted">所需起升高度 = 净空 + 吊物高 + 吊索高，自动推算，无需手工填写。</p>
          </details>
          <button class="primary" :disabled="!geometryReady">下一步：吊装方式</button>
        </form>

        <form v-else-if="step === 2" @submit.prevent="goToCrane">
          <h2>③ 吊装方式</h2>
          <div class="mode-cards">
            <button type="button" class="mode-card" :class="{ active: mode === 'single' }" @click="mode = 'single'">
              <b>单机</b><span>一台汽车吊，按原厂性能表反查最远幅度</span>
            </button>
            <button type="button" class="mode-card" :class="{ active: mode === 'dual' }" disabled
                    title="双机抬吊接口已预留，当前版本暂不可用">
              <b>双机抬吊</b><span>按重心位置分配负荷（接口已预留，暂不可用）</span>
            </button>
          </div>
          <p class="hint">双机抬吊的后端计算与计算书已成节（按重心分载，缺重心时退回 60/40），界面暂未开放。</p>
          <button class="primary" type="submit">下一步：选择车型</button>
        </form>

        <form v-else @submit.prevent="calculate">
          <h2>④ 车型与工况</h2>
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

        <aside v-if="snapshot">
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
        <nav v-if="snapshot">
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
        <div v-if="snapshot && tab === 'sheet'" class="paper">
          <button v-if="snapshot?.svg" class="sheet-open" aria-label="放大吊装示意图" title="放大吊装示意图" @click="sheetViewer?.open()" v-html="snapshot.svg"></button>
          <p v-else>尚无可显示的工况立面</p>
        </div>
        <Load3D
          v-else-if="!snapshot"
          :length="+form.length || 3.2"
          :width="+form.depth || 3.2"
          :height="+form.loadHeight || 3.8"
          :cg="cg"
          :sling-height="+form.slingHeight || 3.5"
          :inset="+form.lugInset || 0"
          :weight="+form.payload || 0"
        />
        <CadPane v-if="usedCad && snapshot" v-show="tab === 'cad'" :snapshot="snapshot" />
        <div class="caption">
          {{ snapshot && tab === 'sheet'
            ? '点击图纸放大 · A3 立面 · 图示姿态不等于现场净空校核'
            : '拖动三维图可旋转 · 重心用形心符号标出 · 数据不完整时不出图' }}
        </div>
      </section>
    </div>
    <p role="status" v-if="notice">{{ notice }}</p>
    <footer>仅供学习与专业复核，不作为工程实施依据。</footer>
    <SheetViewer v-if="snapshot?.svg" ref="sheetViewer" :svg="snapshot.svg" />
  </main>
</template>
