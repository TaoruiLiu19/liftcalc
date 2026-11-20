<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
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
  usedCad = ref(false)
const form = reactive({
  model: 'QY70K-1',
  config: '',
  mode: '最远幅度',
  radius: '10',
  payload: '10',
  hook: '',
  rigging: '0.3',
  height: '',
  limit: '0.90',
  factor: '1.1',
  width: '3.2',
  loadHeight: '3.8',
  clearance: '1',
})
const choices = computed(() => [...new Set(models.value.map((m) => m.model))]),
  configs = computed(() => models.value.filter((m) => m.model === form.model))
const cap = computed(() => snapshot.value?.cap)
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
    notice.value = '输入已改变，请重新计算。'
  },
  { flush: 'sync' },
)
watch(
  () => form.model,
  () => {
    form.config = ''
  },
)
async function calculate() {
  const id = revision
  busy.value = true
  notice.value = ''
  try {
    const data = await window.pywebview!.api.calculate({
      kind: 'crane.capability',
      crane: { model: form.model, brand: configs.value[0]?.brand || '徐工' },
      config: form.config || null,
      payload: +form.payload,
      hook_mass: +form.hook,
      rigging: +form.rigging,
      limit: +form.limit,
      dynamic_factor: +form.factor,
      required_lift_height: form.height === '' ? null : +form.height,
      target_radius: form.mode === '指定幅度' ? +form.radius : null,
      load_width_m: +form.width,
      load_height_m: +form.loadHeight,
      clearance_m: +form.clearance,
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
    await calculate()
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
    <b>Liftcalc</b><span class="divider"></span><span>单机吊装复核</span
    ><small>● 本机离线</small>
    <select class="theme-select" aria-label="界面主题" v-model="theme"><option value="refract">Refract</option><option value="dusk">Dusk</option></select>
  </header>
  <main>
    <div class="workspace">
      <div class="inspector">
        <form @submit.prevent="calculate">
          <h2>工况输入</h2>
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
            >查表方式<select v-model="form.mode">
              <option>最远幅度</option>
              <option>指定幅度</option>
            </select></label
          >
          <label v-if="form.mode === '指定幅度'"
            >指定幅度 / m<input
              required
              type="number"
              step="any"
              min=".001"
              v-model="form.radius"
          /></label>
          <div class="pair">
            <label
              >吊件 / t<input
                required
                type="number"
                step="any"
                min=".001"
                v-model="form.payload" /></label
            ><label
              >吊钩 / t<input
                type="number"
                step="any"
                min="0"
                placeholder="机型库"
                v-model="form.hook"
            /></label>
            <label
              >索具 / t<input
                required
                type="number"
                step="any"
                min="0"
                v-model="form.rigging" /></label
            ><label
              >要求钩高 / m<input
                type="number"
                step="any"
                min="0"
                placeholder="不限"
                v-model="form.height"
            /></label>
          </div>
          <details>
            <summary>系数与图示尺寸</summary>
            <div class="pair">
              <label
                >动载系数<input
                  required
                  type="number"
                  step="any"
                  min=".001"
                  v-model="form.factor" /></label
              ><label
                >负荷率上限<input
                  required
                  type="number"
                  step="any"
                  min=".001"
                  max="1"
                  v-model="form.limit" /></label
              ><label
                >吊物宽 / m<input
                  required
                  type="number"
                  step="any"
                  min=".01"
                  v-model="form.width" /></label
              ><label
                >吊物高 / m<input
                  required
                  type="number"
                  step="any"
                  min=".01"
                  v-model="form.loadHeight" /></label
              ><label
                >图示净空 / m<input
                  required
                  type="number"
                  step="any"
                  min="0"
                  v-model="form.clearance"
              /></label>
            </div>
          </details>
          <button class="primary" :disabled="busy || !models.length">
            {{ busy ? '查表中…' : '计算并生成图纸' }}
          </button>
        </form>
        <aside>
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
            <dt>计算荷载</dt>
            <dd>{{ cap?.required.toFixed(3) ?? '—' }} t</dd>
            <dt>额定载荷</dt>
            <dd>{{ cap?.rated_load ?? '—' }} t</dd>
              <dt>采用臂长</dt>
              <dd>{{ cap?.boom_len ?? '—' }} m</dd>
              <dt>表档起升高度</dt>
              <dd>{{ cap?.lift_height ?? '—' }} m</dd>
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
        <nav>
          <button :class="{ active: tab === 'sheet' }" @click="tab = 'sheet'">
            吊装示意</button
          ><button
            :class="{ active: tab === 'cad' }"
            @click="showCad"
          >
            CAD 核图
          </button>
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
        <div v-show="tab === 'sheet'" class="paper">
          <button v-if="snapshot?.svg" class="sheet-open" aria-label="放大吊装示意图" title="放大吊装示意图" @click="sheetViewer?.open()" v-html="snapshot.svg"></button>
          <p v-else>尚无可显示的工况立面</p>
        </div>
        <CadPane v-if="usedCad" v-show="tab === 'cad'" :snapshot="snapshot" />
        <div v-if="tab === 'sheet'" class="caption">
          点击图纸放大 · A3 立面 · 图示姿态不等于现场净空校核
        </div>
      </section>

    </div>
    <p role="status" v-if="notice">{{ notice }}</p>
    <footer>仅供学习与专业复核，不作为工程实施依据。</footer>
    <SheetViewer v-if="snapshot?.svg" ref="sheetViewer" :svg="snapshot.svg" />
  </main>
</template>
