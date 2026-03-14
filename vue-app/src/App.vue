<template>
  <div class="shell">
    <aside class="shell-sidebar">
      <div class="brand">
        <div class="brand-kicker">ZhongAn</div>
        <div class="brand-title">Form Workspace</div>
      </div>
      <nav class="shell-nav">
        <RouterLink to="/" class="nav-link">模板与审核</RouterLink>
      </nav>
    </aside>
    <main class="shell-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>
