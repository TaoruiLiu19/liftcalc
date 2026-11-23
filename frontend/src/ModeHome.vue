<script setup lang="ts">
defineEmits<{choose: [mode: 'single' | 'dual']}>()
</script>
<template>
  <main class="mode-home">
    <section aria-labelledby="home-title">
      <h1 id="home-title">选择吊装方式</h1>
      <div class="mode-cards">
        <button v-for="mode in (['single','dual'] as const)" :key="mode" :data-mode="mode" @click="$emit('choose', mode)">
          <svg viewBox="0 0 400 170" aria-hidden="true">
            <defs><pattern :id="'grid-'+mode" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="currentColor" opacity=".13"/></pattern></defs>
            <rect width="400" height="170" :fill="'url(#grid-'+mode+')'"/>
            <g v-if="mode==='single'" stroke="currentColor" stroke-width="2" stroke-linejoin="round">
              <path d="M45 145h310" opacity=".4"/>
              <path d="M73 119h50l8-15h48v11h25l5 15H72z" fill="#204e5c"/>
              <path d="M128 117l7-9h11v9z" fill="#a9d4d9"/>
              <g v-for="x in [88,107,170,189]" :key="x"><circle :cx="x" cy="134" r="10" fill="#20434e"/><circle :cx="x" cy="134" r="4" fill="none"/></g>
              <path d="M115 116l14-21h10l10 21zM127 100l62-38 7 8-62 37zM194 63l42-25 5 6-44 27zM238 37l25-14 4 5-27 17z" fill="#558692"/>
              <circle cx="133" cy="100" r="3" fill="#bfe3e6"/><path d="M265 28v49l-4 4-3-2m4 2-18 18m18-18 18 18" fill="none"/>
              <rect x="240" y="99" width="44" height="25" rx="2" fill="#3f7681"/>
            </g>
            <g v-else stroke="currentColor" stroke-width="2" fill="none">
              <g opacity=".55"><path d="M282 14v142m10-142v142"/><path v-for="y in 13" :key="y" :d="'M278 '+y*11+'h18'"/></g>
              <path d="M102 88Q184 98 279 87" stroke-dasharray="5 5"/>
              <g transform="translate(110 85) rotate(-12)"><rect x="-16" y="-51" width="32" height="102" rx="6" fill="#4b6257"/><path d="M-10-39h20m-20 78h20"/></g>
              <rect x="272" y="37" width="30" height="96" rx="6" stroke-dasharray="5 4"/>
              <g v-for="(y,i) in [30,140]" :key="y"><rect x="183" :y="y-10" width="38" height="20" rx="3" fill="#455f52"/><path :d="'M202 '+y+' L'+(i?118:102)+' '+(i?121:49)" stroke-width="4"/><circle cx="202" :cy="y" r="4" fill="#263e36"/></g>
            </g>
          </svg>
          <span class="card-copy"><strong>{{mode==='single'?'单机吊装':'双机上轨'}}</strong>
            <span>{{mode==='single'?'校核单机工况，生成吊装立面图':'选择双机吊点与重心，校核转向轨迹'}}</span></span>
          <span class="enter" aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  </main>
</template>
<style scoped>
.mode-home{justify-content:center;overflow:auto;padding:32px max(5vw,20px) 8vh}
.mode-home section{width:min(100%,1060px);margin:auto}
h1{font-size:clamp(28px,3.3vw,46px);letter-spacing:-.04em;margin:0 0 26px}
.mode-cards{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.mode-cards button{position:relative;overflow:hidden;text-align:left;border-radius:17px;padding:0;box-shadow:0 12px 35px #14293314}
.mode-cards svg{display:block;width:100%;background:#193d49;color:#b0d5d8}
.mode-cards [data-mode=dual] svg{background:#294337;color:#ccdcc5}
.card-copy{display:grid;gap:7px;padding:22px 60px 24px 24px;font-size:14px}
.card-copy strong{font-size:24px}.enter{position:absolute;right:22px;bottom:30px;font-size:25px}
@media(max-width:660px){.mode-cards{grid-template-columns:1fr}.mode-cards svg{height:105px}.card-copy{padding:12px 55px 12px 18px}.mode-home{justify-content:flex-start}}
</style>
