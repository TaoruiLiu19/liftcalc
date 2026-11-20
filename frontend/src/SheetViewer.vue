<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ svg: string }>()
const dialog = ref<HTMLDialogElement>()
const viewport = ref<HTMLDivElement>()
const zoom = ref(1)
const x = ref(0)
const y = ref(0)
const dragging = ref(false)
let drag: { id: number; lastX: number; lastY: number } | null = null

function reset() {
  zoom.value = 1
  x.value = 0
  y.value = 0
}

function open() {
  reset()
  dialog.value?.showModal()
}
defineExpose({ open })

function moveTo(left: number, top: number) {
  const { clientWidth: w, clientHeight: h } = viewport.value!
  // Keep the drawing centre within half a viewport of either edge at fit scale.
  x.value = Math.min(w / 2, Math.max(w / 2 - w * zoom.value, left))
  y.value = Math.min(h / 2, Math.max(h / 2 - h * zoom.value, top))
}

function zoomTo(value: number, anchorX?: number, anchorY?: number) {
  const box = viewport.value!.getBoundingClientRect()
  const px = anchorX ?? box.width / 2
  const py = anchorY ?? box.height / 2
  const next = Math.max(1, Math.min(4, value))
  const ratio = next / zoom.value
  zoom.value = next
  moveTo(px - (px - x.value) * ratio, py - (py - y.value) * ratio)
}

function wheel(event: WheelEvent) {
  const box = viewport.value!.getBoundingClientRect()
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? box.height : 1
  const delta = Math.max(-240, Math.min(240, event.deltaY * unit))
  zoomTo(zoom.value * Math.exp(-delta / 600), event.clientX - box.left, event.clientY - box.top)
}

function startDrag(event: PointerEvent) {
  if (event.button !== 0 || drag) return
  viewport.value!.setPointerCapture(event.pointerId)
  drag = { id: event.pointerId, lastX: event.clientX, lastY: event.clientY }
  dragging.value = true
}
function pan(event: PointerEvent) {
  if (!drag || drag.id !== event.pointerId) return
  moveTo(x.value + event.clientX - drag.lastX, y.value + event.clientY - drag.lastY)
  drag.lastX = event.clientX
  drag.lastY = event.clientY
}
function stopDrag() {
  drag = null
  dragging.value = false
}
</script>

<template>
  <dialog ref="dialog" class="sheet-dialog" aria-label="吊装示意图放大查看" @close="stopDrag">
    <div class="sheet-bar">
      <strong>吊装示意图</strong><span class="muted">左键拖动 · 滚轮缩放</span>
      <button aria-label="缩小" :disabled="zoom <= 1" @click="zoomTo(zoom - 0.5)">−</button>
      <button title="恢复全图" @click="reset">{{ Math.round(zoom * 100) }}%</button>
      <button aria-label="放大" :disabled="zoom >= 4" @click="zoomTo(zoom + 0.5)">＋</button>
      <button autofocus @click="dialog?.close()">关闭</button>
    </div>
    <div ref="viewport" class="sheet-scroll" :class="{ dragging }" tabindex="0" aria-label="图纸，方向键平移"
      @keydown.left.prevent="moveTo(x + 40, y)" @keydown.right.prevent="moveTo(x - 40, y)"
      @keydown.up.prevent="moveTo(x, y + 40)" @keydown.down.prevent="moveTo(x, y - 40)"
      @wheel.prevent="wheel" @pointerdown="startDrag" @pointermove="pan"
      @lostpointercapture="stopDrag">
      <div class="sheet-surface" :style="{ transform: 'translate(' + x + 'px,' + y + 'px) scale(' + zoom + ')' }" v-html="svg"></div>
    </div>
  </dialog>
</template>
