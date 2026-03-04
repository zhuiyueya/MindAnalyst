<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t, locale } = useI18n()
const router = useRouter()
const currentLocale = computed(() => locale.value)

const setLocale = (value) => {
  locale.value = value
  localStorage.setItem('lang', value)
}

const navItems = computed(() => [
  { path: '/', label: t('dashboard.operationModules'), icon: '■' },
  { path: '/authors', label: t('nav.authors'), icon: '◈' },
  { path: '/ingest', label: t('nav.ingest'), icon: '📥' },
  { path: '/chat', label: t('nav.chat'), icon: '💬' },
  { path: '/llm-calls', label: t('nav.llmLogs'), icon: '⚡' },
])

const currentTime = ref(new Date().toLocaleTimeString())
setInterval(() => {
  currentTime.value = new Date().toLocaleTimeString()
}, 1000)
</script>

<template>
  <div class="min-h-screen flex bg-background text-text-primary font-mono selection:bg-primary selection:text-background">
    <!-- Command Rail (Sidebar) -->
    <aside class="w-64 bg-surface border-r border-border flex flex-col h-screen fixed left-0 top-0 z-50">
      <div class="p-6 border-b border-border">
        <h1 class="text-xl font-bold font-sans text-primary tracking-tighter">
          MIND_ANALYST
          <span class="text-xs text-text-secondary block font-mono mt-1 opacity-50">v2.0.0-beta</span>
        </h1>
      </div>

      <nav class="flex-1 py-6 px-4 space-y-2">
        <router-link 
          v-for="item in navItems" 
          :key="item.path"
          :to="item.path"
          class="flex items-center px-4 py-3 text-sm font-medium transition-all duration-0 border border-transparent hover:border-primary/50 hover:text-primary group"
          active-class="bg-primary text-black border-primary font-bold"
        >
          <span class="mr-3 opacity-50 group-hover:opacity-100">{{ item.icon }}</span>
          {{ item.label }}
        </router-link>
      </nav>

      <!-- System Status / Footer -->
      <div class="p-6 border-t border-border text-xs text-text-secondary space-y-4">
        <div class="space-y-1 font-mono">
          <div class="flex justify-between">
            <span>{{ t('app.sysTime') }}</span>
            <span class="text-primary">{{ currentTime }}</span>
          </div>
          <div class="flex justify-between">
            <span>{{ t('app.apiStat') }}</span>
            <span class="text-primary">{{ t('app.online') }}</span>
          </div>
          <div class="flex justify-between">
            <span>{{ t('app.dbConn') }}</span>
            <span class="text-primary">{{ t('app.active') }}</span>
          </div>
        </div>

        <div class="flex space-x-2 pt-4 border-t border-border/50">
          <button
            class="px-2 py-1 border text-[10px] uppercase hover:bg-primary hover:text-black transition-colors"
            :class="currentLocale === 'zh-CN' ? 'bg-primary text-black border-primary' : 'border-border text-text-secondary'"
            @click="setLocale('zh-CN')"
          >
            CN
          </button>
          <button
            class="px-2 py-1 border text-[10px] uppercase hover:bg-primary hover:text-black transition-colors"
            :class="currentLocale === 'en-US' ? 'bg-primary text-black border-primary' : 'border-border text-text-secondary'"
            @click="setLocale('en-US')"
          >
            EN
          </button>
        </div>
      </div>
    </aside>

    <!-- Main Content Area -->
    <main class="flex-1 ml-64 p-8 min-h-screen h-screen overflow-hidden relative flex flex-col">
      <!-- Top Bar Decoration -->
      <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-transparent to-transparent opacity-50 z-50"></div>
      
      <div class="flex-1 overflow-y-auto pr-2 scrollbar-terminal relative">
        <router-view v-slot="{ Component }">
          <transition name="glitch" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<style>
/* Glitch Transition Effect */
.glitch-enter-active,
.glitch-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease, filter 0.1s;
}

.glitch-enter-from {
  opacity: 0;
  transform: translateX(-10px);
  filter: blur(4px);
}

.glitch-leave-to {
  opacity: 0;
  transform: translateX(10px);
  filter: blur(4px);
}

.scrollbar-terminal::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-terminal::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-terminal::-webkit-scrollbar-thumb {
  background: #27272a;
  border-radius: 0;
}
.scrollbar-terminal::-webkit-scrollbar-thumb:hover {
  background: #ccff00;
}
</style>
