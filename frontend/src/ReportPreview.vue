<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{ reportId: string }>()
const dialog = ref<HTMLDialogElement>()
const url = ref('')
const loading = ref(false)
const saving = ref(false)
const previewError = ref('')
const saveError = ref('')

function clearPreview() {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''
}
watch(() => props.reportId, clearPreview)
onBeforeUnmount(clearPreview)

async function open() {
  dialog.value?.showModal()
  if (url.value || loading.value) return
  const reportId = props.reportId
  loading.value = true
  previewError.value = ''
  try {
    const html = await window.pywebview!.api.report(reportId)
    if (reportId === props.reportId && dialog.value)
      url.value = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  } catch (error) {
    previewError.value = String(error)
  } finally {
    loading.value = false
  }
}

async function save(format: 'html' | 'docx') {
  saving.value = true
  saveError.value = ''
  try {
    await window.pywebview!.api.export(props.reportId, format)
  } catch (error) {
    saveError.value = String(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <button type="button" @click="open">计算书预览</button>
  <dialog ref="dialog" class="report-dialog" aria-label="设计计算书预览">
    <div class="report-pane">
      <div class="report-toolbar">
        <h2>设计计算书预览</h2>
        <button type="button" :disabled="saving || !url" @click="save('html')">导出 HTML</button>
        <button type="button" :disabled="saving || !url" @click="save('docx')">保存 Word</button>
        <button type="button" autofocus @click="dialog?.close()">关闭</button>
      </div>
      <p v-if="saveError" class="report-error" role="alert">{{saveError}}</p>
      <iframe v-if="url" :src="url" title="设计计算书正文" sandbox=""></iframe>
      <p v-else-if="previewError" class="report-error" role="alert">{{previewError}}</p>
      <p v-else class="report-loading" role="status">正在生成预览…</p>
    </div>
  </dialog>
</template>

<style scoped>
.report-dialog{width:min(1100px,96vw);height:min(920px,92dvh);max-width:none;max-height:none;padding:0;
  color:#182a35;background:#f8fafb;border:1px solid #c1cfd5;border-radius:12px}
.report-dialog::backdrop{background:#142530a8}
.report-pane{display:flex;flex-direction:column;height:100%;min-height:0}
.report-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:10px 14px;border-bottom:1px solid #c1cfd5}
.report-toolbar h2{margin:0 auto 0 0;font-size:16px}
.report-pane iframe{width:100%;min-height:0;flex:1;border:0}
.report-loading,.report-error{margin:12px 16px}
.report-error{color:#a61e32}
</style>
