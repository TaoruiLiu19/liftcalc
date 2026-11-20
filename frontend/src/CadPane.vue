<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { AcApDocManager } from '@mlightcad/cad-simple-viewer'
import type { Snapshot } from './types'
const props = defineProps<{ snapshot: Snapshot | null }>()
const host = ref<HTMLDivElement>(),
  picker = ref<HTMLInputElement>()
const name = ref('未打开图纸')
const info = ref('')
const busy = ref(false)
let manager: AcApDocManager | undefined
let owned: string | null = null
async function open(source: File | Snapshot) {
  if (busy.value) return
  busy.value = true
  info.value = '正在解析 DXF…'
  owned = null
  try {
    const cad = await import('@mlightcad/cad-simple-viewer')
    cad.AcApI18n.setCurrentLocale('zh')
    if (!manager) {
      manager = cad.AcApDocManager.createInstance({
        container: host.value,
        autoResize: true,
        baseUrl: location.origin + '/',
        builtinOpenFileDialog: false,
        notificationCenter: false,
        webworkerFileUrls: {
          mtextRender: location.origin + '/assets/mtext-renderer-worker.js',
        },
      })
      // Pan and zoom use the view directly. No interactive commands are needed.
      manager?.commandManager.removeAll()
    }
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
    } else {
      const encoded = await window.pywebview!.api.dxf(source.id)
      bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)).buffer
      filename = source.cap.model + '-立面.dxf'
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
    manager.curView.mode = cad.AcEdViewMode.PAN
    name.value = filename
    info.value = '左键拖动 · 滚轮缩放'
  } catch (error) {
    name.value = '未打开图纸'
    info.value = String(error)
    owned = null
  } finally {
    busy.value = false
  }
}
function fit() {
  manager?.curView.zoomToFitDrawing()
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
      />
      <button :disabled="busy || name === '未打开图纸'" @click="fit">全图</button>
    </div>
    <div class="viewport">
      <div class="gl" ref="host" @contextmenu.capture.prevent.stop
        @dblclick.capture.prevent.stop @dragover.prevent @drop.capture.prevent.stop></div>
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
