<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()
const currentLocale = computed(() => locale.value)

const setLocale = (value) => {
  locale.value = value
  localStorage.setItem('lang', value)
}
</script>

<template>
  <div class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Header -->
    <header class="bg-white shadow z-10">
      <div class="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
        <router-link to="/" class="text-2xl font-bold text-gray-900 hover:text-indigo-600 transition-colors">
          {{ t('nav.appName') }}
        </router-link>
        <nav class="flex items-center space-x-4">
          <router-link 
            to="/authors"
            class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-50"
            active-class="bg-gray-100 text-indigo-600"
          >
            {{ t('nav.authors') }}
          </router-link>
          <router-link 
            to="/ingest"
            class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-50"
            active-class="bg-gray-100 text-indigo-600"
          >
            {{ t('nav.ingest') }}
          </router-link>
          <router-link 
            to="/chat"
            class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-50"
            active-class="bg-gray-100 text-indigo-600"
          >
            {{ t('nav.chat') }}
          </router-link>
          <router-link 
            to="/llm-calls"
            class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-50"
            active-class="bg-gray-100 text-indigo-600"
          >
            {{ t('nav.llmLogs') }}
          </router-link>
          <div class="flex items-center space-x-2">
            <span class="text-xs text-gray-500">{{ t('nav.language') }}</span>
            <button
              class="px-2 py-1 rounded text-xs border"
              :class="currentLocale === 'zh-CN' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-700 border-gray-300'"
              @click="setLocale('zh-CN')"
            >
              {{ t('nav.languageZh') }}
            </button>
            <button
              class="px-2 py-1 rounded text-xs border"
              :class="currentLocale === 'en-US' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-700 border-gray-300'"
              @click="setLocale('en-US')"
            >
              {{ t('nav.languageEn') }}
            </button>
          </div>
        </nav>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 max-w-7xl w-full mx-auto py-6 sm:px-6 lg:px-8">
      <!-- Use router-view -->
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
