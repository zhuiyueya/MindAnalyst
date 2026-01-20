<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="text-center py-20">
    <h1 class="text-4xl font-bold text-gray-900 mb-4">{{ t('dashboard.title') }}</h1>
    <p class="text-lg text-gray-600 mb-8">{{ t('dashboard.subtitle') }}</p>
    
    <div class="flex justify-center space-x-4">
      <router-link 
        to="/authors" 
        class="px-6 py-3 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 font-medium"
      >
        {{ t('dashboard.exploreAuthors') }}
      </router-link>
      <router-link 
        to="/ingest" 
        class="px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 font-medium"
      >
        {{ t('dashboard.ingestContent') }}
      </router-link>
    </div>
  </div>
</template>
