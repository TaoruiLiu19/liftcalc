<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { AcApDocManager } from '@mlightcad/cad-simple-viewer'
import type { Snapshot } from './types'
const props = defineProps<{ snapshot: Snapshot | null }>()
const host = ref<HTMLDivElement>(),
  picker = ref<HTMLInputElement>()
const layers = ref<{ name: string; isOn: boolean }[]>([]),
  name = ref('未打开图纸'),
  info = ref(''),
  busy = ref(false),
  measuring = ref(false),
  scale = ref<number | null>(null),
  unit = ref('图形单位')
let manager: AcApDocManager | undefined,
  start: { x: number; y: number } | null = null,
  owned: string | null = null
async function open(source: File | Snapshot) {
  if (busy.value) return
  busy.value = true
  info.value = '正在解析 DXF…'
  layers.value = []
  measuring.value = false
  start = null
  owned = null
  try {
    const cad = await import('@mlightcad/cad-simple-viewer')
    cad.AcApI18n.setCurrentLocale('zh')
    if (!manager)
      manager = cad.AcApDocManager.createInstance({
        container: host.value,
        autoResize: true,
        baseUrl: location.origin + '/',
        builtinOpenFileDialog: false,
        webworkerFileUrls: {
          mtextRender: location.origin + '/assets/mtext-renderer-worker.js',
        },
      })
    if (!manager) throw Error('WebGL 不可用，请检查 WebView2 或显示驱动')
    let bytes: ArrayBuffer, filename: string
    if (source instanceof File) {
      if (
        !source.name.toLowerCase().endsWith('.dxf') ||
        source.size > 32 * 1024 * 1024
      )
        throw Error('请选择 32 MB 以内的 DXF')
      bytes = await source.arrayBuffer()
      filename = source.name
      scale.value = null
    } else {
      const encoded = await window.pywebview!.api.dxf(source.id)
      bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)).buffer
      filename = source.cap.model + '-立面.dxf'
      scale.value = source.scale
      owned = source.id
    }
    if (
      !(await manager.openDocument(filename, bytes, {
        mode: cad.AcEdOpenMode.Read,
      }))
    )
      throw Error('DXF 解析失败')
    if (owned && props.snapshot?.id !== owned)
      throw Error('工况已改变，请重新核图')
    layers.value = manager.curDocument.layerStore.getLayers()
    const units: Record<number, string> = {
      1: 'in',
      2: 'ft',
      4: 'mm',
      5: 'cm',
      6: 'm',
    }
    unit.value = units[manager.curDocument.database.insunits] || '图形单位'
    name.value = filename
    info.value = '滚轮缩放 · 中键平移 · 两点测距为自由点选'
  } catch (error) {
    name.value = '未打开图纸'
    info.value = String(error)
    owned = null
    scale.value = null
  } finally {
    busy.value = false
  }
}
function fit() {
  manager?.curView.zoomToFitDrawing()
}
function toggleMeasure() {
  measuring.value = !measuring.value
  start = null
  info.value = measuring.value ? '请选择起点' : '已取消测距'
}
function toggle(name: string, on: boolean) {
  manager?.curDocument.layerStore.setLayerOn(name, on)
  layers.value = manager?.curDocument.layerStore.getLayers() || []
}
function point(event: MouseEvent) {
  if (!measuring.value || !manager || !host.value || event.button !== 0) return
  const rect = host.value.getBoundingClientRect(),
    p = manager.curView.screenToWorld({
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    })
  if (!start) {
    start = { x: p.x, y: p.y }
    info.value = '请选择终点'
    return
  }
  const dist = Math.hypot(p.x - start.x, p.y - start.y)
  info.value =
    '点间距 ' +
    dist.toFixed(2) +
    ' ' +
    unit.value +
    (scale.value
      ? ' · 按 1:' +
        scale.value +
        ' 折算 ' +
        ((dist * scale.value) / 1000).toFixed(3) +
        ' m'
      : '')
  start = null
  measuring.value = false
}
function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.[0]) void open(input.files[0])
  input.value = ''
}
watch(
  () => props.snapshot?.id,
  () => {
    if (owned) {
      name.value = '未打开图纸'
      info.value = '工况已改变，请重新打开本次 DXF'
      layers.value = []
      measuring.value = false
    }
  },
)
onMounted(() => {
  if (props.snapshot?.svg) void open(props.snapshot)
})
</script>
<template>
  <div class="cad">
    <div class="tools">
      <button
        :disabled="busy || !snapshot?.svg"
        @click="snapshot && open(snapshot)"
      >
        本次 DXF</button
      ><button :disabled="busy" @click="picker?.click()">打开本地 DXF</button>
      <input
        hidden
        ref="picker"
        type="file"
        accept=".dxf"
        @change="fileChanged"
      /><button :disabled="busy || !layers.length" @click="fit">全图</button>
      <button
        :disabled="busy || !layers.length"
        :class="{ active: measuring }"
        @click="toggleMeasure"
      >
        两点测距
      </button>
      <details>
        <summary>图层 · {{ layers.length }}</summary>
        <div class="layers">
          <label v-for="layer in layers" :key="layer.name"
            ><input
              type="checkbox"
              :checked="layer.isOn"
              @change="
                toggle(layer.name, ($event.target as HTMLInputElement).checked)
              "
            />
            {{ layer.name }}</label
          >
        </div>
      </details>
    </div>
    <div class="viewport">
      <div class="gl" ref="host" @click.capture="point"></div>
      <div v-if="busy || name === '未打开图纸'" class="cover">
        {{
          busy
            ? '正在载入图纸…'
            : info || '打开本地 DXF，或核对本次计算的导出文件'
        }}
      </div>
    </div>
    <div class="caption">{{ name }} · {{ info }}</div>
  </div>
</template>
