<script setup lang="ts">
import { computed, ref } from 'vue'
const props=defineProps<{
  length:number; width:number; points:number[][]; pick:number
  gauge:number; site?:boolean; cranes:{center:number[]; exclusion:number}[]; poses:number[][]; obstacles:number[][]; focus?:number
}>()
const emit=defineEmits<{place:[x:number,y:number]}>()
const hover=ref<number[]>()
const W=600,H=316
function outline(p:number[]){
  const a=p[2]*Math.PI/180,c=Math.cos(a),s=Math.sin(a)
  return [[-1,-1],[1,-1],[1,1],[-1,1]].map(([u,v])=>{
    const x=u*props.length/2,y=v*props.width/2
    return [p[0]+x*c-y*s,p[1]+x*s+y*c]
  })
}
const bodies=computed(()=>props.site?props.poses.map(outline):[outline([0,0,0])])
const rails=computed(()=>{
  if(!props.site) return []
  const [cx,cy,deg]=props.poses[1], a=deg*Math.PI/180
  return [-1,1].map(side=>[-1,1].map(end=>{
    const u=end*props.length*.72,v=side*props.gauge/2
    return [cx+u*Math.cos(a)-v*Math.sin(a),cy+u*Math.sin(a)+v*Math.cos(a)]
  }))
})
const disks=computed(()=>props.site?[...props.cranes.map((c,i)=>({p:c.center,r:c.exclusion,label:'AB'[i]+' 机'})),
  ...props.obstacles.map((o,i)=>({p:o,r:o[2],label:'障碍 '+(i+1)}))]:[])
const frame=computed(()=>{
  const pts=[[0,0],...bodies.value.flat(),...rails.value.flat(),...disks.value.flatMap(d=>[[d.p[0]-d.r,d.p[1]-d.r],[+d.p[0]+d.r,+d.p[1]+d.r]])]
  const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1])
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys)
  const k=Math.min((W-130)/Math.max(.001,x1-x0),(H-96)/Math.max(.001,y1-y0))
  return {k,ox:W/2-k*(x1+x0)/2,oy:H/2+k*(y1+y0)/2}
})
const X=(x:number)=>frame.value.ox+x*frame.value.k
const Y=(y:number)=>frame.value.oy-y*frame.value.k
const poly=(ps:number[][])=>ps.map(p=>X(p[0])+','+Y(p[1])).join(' ')
const tick=computed(()=>{
  const raw=62/frame.value.k,unit=10**Math.floor(Math.log10(raw))
  return ([1,2,5,10].find(n=>n*unit>=raw)??10)*unit
})
function marks(max:number,offset:number,sign:number){
  const gap=tick.value*frame.value.k, start=Math.ceil((26-offset)/gap), end=Math.floor((max-26-offset)/gap)
  return Array.from({length:Math.max(0,end-start+1)},(_,i)=>({px:offset+(start+i)*gap,n:Number(((start+i)*tick.value*sign).toPrecision(5))}))
}
const xt=computed(()=>marks(W,frame.value.ox,1)),yt=computed(()=>marks(H,frame.value.oy,-1))
function locate(e:PointerEvent|MouseEvent){
  const matrix=(e.currentTarget as SVGSVGElement).getScreenCTM()
  if(!matrix) return
  const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse())
  const x=(p.x-frame.value.ox)/frame.value.k,y=(frame.value.oy-p.y)/frame.value.k
  if(Math.abs(x)>props.length/2 || Math.abs(y)>props.width/2) return
  return [Number(x.toFixed(3)),Number(y.toFixed(3))]
}
</script>
<template>
<figure><figcaption><b>{{site?'场地平面':'吊物顶面'}}</b><span>{{site?'场地坐标':'局部坐标'}} · m</span></figcaption>
<svg viewBox="0 0 600 316" :class="{pick:!site}" :aria-label="site?'场地坐标图':'点选吊点与重心的局部坐标图'" @pointermove="!site && (hover=locate($event))" @pointerleave="hover=undefined" @click="e=>{const p=locate(e);if(!site && p)emit('place',p[0],p[1])}">
  <g class="grid"><path v-for="t in xt" :key="'x'+t.n" :d="'M'+t.px+' 18v280'"/><path v-for="t in yt" :key="'y'+t.n" :d="'M20 '+t.px+'h560'"/></g>
  <g v-if="site" class="rails"><polyline v-for="(rail,i) in rails" :key="i" :points="poly(rail)"/>
    <polyline class="travel" :points="poly(poses)"/></g>
  <polygon v-for="(b,i) in bodies" :key="i" :points="poly(b)" :class="['body',{end:i===1}]"/>
  <g class="axis"><path :d="'M18 '+Y(0)+'H582l-6 -3m6 3-6 3'"/><path :d="'M'+X(0)+' 299V15l-3 6m3 -6 3 6'"/></g>
  <g class="ticks"><text v-for="t in xt.filter(t=>t.n!==0)" :key="t.n" :x="t.px" y="308" text-anchor="middle">{{t.n}}</text><text v-for="t in yt.filter(t=>t.n!==0)" :key="t.n" x="4" :y="t.px+4">{{t.n}}</text>
  <text :x="X(0)+7" :y="Y(0)+15">O</text><text x="568" :y="Y(0)-8">+X</text><text :x="X(0)+7" y="20">+Y</text></g>
  <template v-if="!site">
    <polyline :points="poly(points.slice(0,2))" class="ab"/>
    <g v-for="(p,i) in points" :key="i" :transform="'translate('+X(p[0])+','+Y(p[1])+')'" :class="['marker',{cg:i===2}]">
      <circle v-if="i===pick" r="11" fill="none" stroke="currentColor"/><circle r="5" fill="currentColor"/><text x="7" y="-9">{{'ABG'[i]}}</text>
    </g>
  </template>
  <template v-else><g v-for="(d,i) in disks" :key="i" :class="['disk',{focus:i===focus}]">
    <circle :cx="X(d.p[0])" :cy="Y(d.p[1])" :r="Math.max(0,d.r*frame.k)"/><text :x="X(d.p[0])+4" :y="Y(d.p[1])-4">{{d.label}}</text></g>
    <text v-for="(p,i) in poses" :key="i" :x="X(p[0])+5" :y="Y(p[1])+16">{{i?'落位':'起吊'}}</text>
  </template>
</svg>
<p>{{site?'实线为起吊位置，虚线为落位位置，圆为平面禁入区。':hover?'X '+hover[0].toFixed(3)+' m　 Y '+hover[1].toFixed(3)+' m':'原点 O 在吊物形心，+X 沿车长，+Y 沿车宽。'}}</p></figure>
</template>
<style scoped>
figure{margin:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--plot)}
figcaption{padding:12px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}
figcaption span,p{font-size:12px;color:var(--quiet)}p{padding:6px 14px;margin:0;border-top:1px solid var(--line)}
svg{display:block;width:100%;height:auto}.pick{cursor:crosshair}
.grid path{stroke:var(--line);stroke-width:.7}.axis path{stroke:var(--quiet);stroke-width:1.1;fill:none}
text{font:13px 'Microsoft YaHei UI',sans-serif;fill:var(--ink)}.ticks text{font-size:11px;fill:var(--quiet)}
.rails polyline{stroke:var(--quiet);stroke-width:1.4;fill:none}.rails .travel{stroke-dasharray:3 4}.body{fill:var(--wash);stroke:var(--accent);stroke-width:1.5}.end{stroke-dasharray:5 4;fill:none}
.ab{stroke:var(--accent);stroke-dasharray:5 3;fill:none}.marker{color:var(--accent)}.cg{color:var(--warm)}
.marker text{fill:currentColor;font-weight:700}.disk circle{stroke:var(--quiet);fill:none}.focus circle{stroke:var(--accent);stroke-width:2;fill:var(--wash)}
</style>
