<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    length: number
    width: number
    height: number
    cg?: { x: number; y: number; z: number }
    slingHeight?: number
    inset?: number
    weight?: number
  }>(),
  { cg: () => ({ x: 0, y: 0, z: 0 }), slingHeight: 3.2, inset: 0, weight: 0 },
)

const yaw = 34 * Math.PI / 180
const pitch = 21 * Math.PI / 180

const VIEW_W = 720
const VIEW_H = 430

function project(x: number, y: number, z: number): [number, number] {
  const cy = Math.cos(yaw)
  const sy = Math.sin(yaw)
  const cp = Math.cos(pitch)
  const sp = Math.sin(pitch)
  const u = x * cy - y * sy
  const depth = x * sy + y * cy
  return [u, z * cp + depth * sp]
}

const model = computed(() => {
  const L = props.length
  const B = props.width
  const H = props.height
  const hx = L / 2
  const hy = B / 2
  const hz = H / 2
  const inset = props.inset
  const apex = { x: props.cg.x, y: props.cg.y, z: hz + props.slingHeight }
  const lugs = [
    { x: hx - inset, y: hy - inset, z: hz },
    { x: -(hx - inset), y: hy - inset, z: hz },
    { x: hx - inset, y: -(hy - inset), z: hz },
    { x: -(hx - inset), y: -(hy - inset), z: hz },
  ]
  const corners = [-hx, hx].flatMap((x) => [-hy, hy].flatMap((y) => [-hz, hz].map((z) => ({ x, y, z }))))
  const axis = Math.max(hx, hy) * 1.85 + 0.3
  const axisZ = apex.z + 0.9

  const pts = [...lugs.map((p) => ({ ...p, z: apex.z })), ...corners, { x: axis, y: 0, z: 0 }, { x: 0, y: axis, z: 0 }, { x: 0, y: 0, z: axisZ }]
  const projected = pts.map((p) => project(p.x, p.y, p.z))
  const us = projected.map((p) => p[0])
  const vs = projected.map((p) => p[1])
  const spanU = Math.max(...us) - Math.min(...us) || 1
  const spanV = Math.max(...vs) - Math.min(...vs) || 1
  const scale = Math.min(560 / spanU, 300 / spanV)
  const ox = VIEW_W / 2 - ((Math.min(...us) + Math.max(...us)) / 2) * scale
  const oy = 235 + ((Math.min(...vs) + Math.max(...vs)) / 2) * scale

  const at = (p: { x: number; y: number; z: number }) => {
    const [u, v] = project(p.x, p.y, p.z)
    return { x: ox + u * scale, y: oy - v * scale }
  }

  const c = (sx: number, sy: number, sz: number) => at({ x: sx * hx, y: sy * hy, z: sz * hz })
  const box = {
    bottom: [c(-1, -1, -1), c(1, -1, -1), c(1, 1, -1), c(-1, 1, -1)],
    top: [c(-1, -1, 1), c(1, -1, 1), c(1, 1, 1), c(-1, 1, 1)],
  }
  const edges: { a: { x: number; y: number }; b: { x: number; y: number }; hidden: boolean }[] = []
  const pair = (a: { x: number; y: number }, b: { x: number; y: number }, hidden = false) =>
    edges.push({ a, b, hidden })
  for (let i = 0; i < 4; i += 1) {
    pair(box.bottom[i], box.bottom[(i + 1) % 4])
    pair(box.top[i], box.top[(i + 1) % 4])
    pair(box.bottom[i], box.top[i], i === 0)
  }

  const origin = at({ x: 0, y: 0, z: 0 })
  const cg = at({ x: props.cg.x, y: props.cg.y, z: props.cg.z })
  const hook = at(apex)
  const slings = lugs.map((lug) => ({ a: hook, b: at(lug), lug: at(lug) }))
  const axes = [
    { a: origin, b: at({ x: axis, y: 0, z: 0 }), label: 'x（长度，远离吊车）', tag: 'x', dx: 6, dy: 4, anchor: 'start' },
    { a: origin, b: at({ x: 0, y: axis, z: 0 }), label: `y（宽度 B=${B.toFixed(2)}）`, tag: 'y', dx: -6, dy: -6, anchor: 'end' },
    { a: origin, b: at({ x: 0, y: 0, z: axisZ }), label: 'z（竖向）', tag: 'z', dx: 6, dy: 4, anchor: 'start' },
  ]

  const mid = (a: { x: number; y: number }, b: { x: number; y: number }) => ({
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
  })
  const labels = [
    { p: mid(box.bottom[0], box.bottom[1]), text: `L=${L.toFixed(2)} m`, dx: 0, dy: 26, anchor: 'middle' },
    { p: mid(box.top[3], box.bottom[3]), text: `H=${H.toFixed(2)} m`, dx: -14, dy: 4, anchor: 'end' },
  ]

  return { box, edges, axes, slings, hook, cg, origin, labels, scale, L, B, H, hx, hy, hz }
})
</script>

<template>
  <div class="load3d">
    <svg
      :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`"
      class="load3d-svg"
      role="img"
      aria-label="吊物三维示意：长方体、坐标轴与重心"
    >
      <defs>
        <marker id="axis-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>
      </defs>
      <g class="axis" v-for="axis in model.axes" :key="axis.tag">
        <line :x1="axis.a.x" :y1="axis.a.y" :x2="axis.b.x" :y2="axis.b.y" marker-end="url(#axis-arrow)" />
        <text :x="axis.b.x + axis.dx" :y="axis.b.y + axis.dy" :text-anchor="axis.anchor">{{ axis.label }}</text>
      </g>
      <g class="box">
        <line
          v-for="(edge, index) in model.edges"
          :key="index"
          :x1="edge.a.x"
          :y1="edge.a.y"
          :x2="edge.b.x"
          :y2="edge.b.y"
          :class="{ hidden: edge.hidden }"
        />
      </g>
      <line class="plumb" :x1="model.hook.x" :y1="model.hook.y" :x2="model.cg.x" :y2="model.cg.y" />
      <g class="sling">
        <line v-for="(sling, index) in model.slings" :key="index" :x1="sling.a.x" :y1="sling.a.y" :x2="sling.b.x" :y2="sling.b.y" />
        <circle v-for="(sling, index) in model.slings" :key="`lug-${index}`" :cx="sling.lug.x" :cy="sling.lug.y" r="4" />
        <circle :cx="model.hook.x" :cy="model.hook.y" r="7" class="hook" />
        <text :x="model.hook.x - 12" :y="model.hook.y + 2" text-anchor="end" class="hook-label">吊钩</text>
      </g>
      <g class="dims">
        <text v-for="(label, index) in model.labels" :key="index" :x="label.p.x + label.dx" :y="label.p.y + label.dy" :text-anchor="label.anchor">
          {{ label.text }}
        </text>
      </g>
      <g class="cg">
        <line :x1="model.origin.x" :y1="model.origin.y" :x2="model.cg.x" :y2="model.cg.y" stroke-dasharray="5 4" />
        <circle :cx="model.cg.x" :cy="model.cg.y" r="9" class="cg-circle" />
        <path class="cg-fill" :d="`M ${model.cg.x} ${model.cg.y} L ${model.cg.x - 9} ${model.cg.y} A 9 9 0 0 0 ${model.cg.x} ${model.cg.y - 9} Z`" />
        <path class="cg-fill" :d="`M ${model.cg.x} ${model.cg.y} L ${model.cg.x + 9} ${model.cg.y} A 9 9 0 0 0 ${model.cg.x} ${model.cg.y + 9} Z`" />
        <line :x1="model.cg.x - 12" :y1="model.cg.y" :x2="model.cg.x + 12" :y2="model.cg.y" class="cg-cross" />
        <line :x1="model.cg.x" :y1="model.cg.y - 12" :x2="model.cg.x" :y2="model.cg.y + 12" class="cg-cross" />
        <text :x="model.cg.x + 12" :y="model.cg.y + 4" class="cg-tag">G</text>
      </g>
    </svg>
    <div class="load3d-foot">
      <span>{{ model.L.toFixed(2) }} × {{ model.B.toFixed(2) }} × {{ model.H.toFixed(2) }} m</span>
      <span>{{ weight ? weight.toFixed(2) + ' t' : '—' }}</span>
      <span class="muted">重心相对形心 ({{ props.cg.x.toFixed(2) }}, {{ props.cg.y.toFixed(2) }}, {{ props.cg.z.toFixed(2) }}) m</span>
    </div>
  </div>
</template>
