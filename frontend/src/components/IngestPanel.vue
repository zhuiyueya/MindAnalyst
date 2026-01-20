<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const mid = ref('')
const limit = ref(10)
const isLoading = ref(false)
const message = ref('')
const error = ref('')
const { t } = useI18n()

const handleIngest = async () => {
  if (!mid.value.trim()) return
  
  isLoading.value = true
  message.value = ''
  error.value = ''
  
  try {
    const res = await axios.post('/api/v1/ingest', {
      author_id: mid.value.trim(),
      limit: limit.value
    })
    message.value = t('ingest.success', { message: res.data.message, taskId: res.data.task_id ?? '-' })
    mid.value = ''
  } catch (e) {
    error.value = t('ingest.error', { message: e.response?.data?.detail || e.message })
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="p-6 flex flex-col h-full max-w-2xl mx-auto w-full">
    <h2 class="text-xl font-semibold mb-6">{{ t('ingest.title') }}</h2>
    
    <div class="bg-white p-6 rounded-lg shadow-sm border space-y-6">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('ingest.midLabel') }}</label>
        <div class="flex">
          <span class="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 text-gray-500 text-sm">
            space.bilibili.com/
          </span>
          <input 
            v-model="mid"
            type="text"
            class="flex-1 min-w-0 block w-full px-3 py-2 rounded-none rounded-r-md border border-gray-300 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            :placeholder="t('ingest.midPlaceholder')"
          />
        </div>
        <p class="mt-1 text-xs text-gray-500">{{ t('ingest.midHelp') }}</p>
      </div>
      
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('ingest.limitLabel') }}</label>
        <input 
          v-model.number="limit"
          type="number"
          min="1"
          class="block w-full sm:w-32 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
        />
      </div>

      <button 
        @click="handleIngest" 
        :disabled="isLoading || !mid"
        class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg v-if="isLoading" class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        {{ isLoading ? t('common.processing') : t('ingest.start') }}
      </button>
    </div>

    <div v-if="message" class="mt-4 p-4 bg-green-50 border border-green-200 text-green-700 rounded-md flex items-center">
      <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
      </svg>
      {{ message }}
    </div>
    
    <div v-if="error" class="mt-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex items-center">
      <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
      </svg>
      {{ error }}
    </div>
    
    <div class="mt-8 text-sm text-gray-500 bg-gray-50 p-4 rounded-md">
      <h3 class="font-medium text-gray-900 mb-2">{{ t('ingest.howItWorksTitle') }}</h3>
      <ol class="list-decimal list-inside space-y-1">
        <li>{{ t('ingest.step1') }}</li>
        <li>{{ t('ingest.step2') }}</li>
        <li>{{ t('ingest.step3') }}</li>
        <li>{{ t('ingest.step4') }}</li>
      </ol>
    </div>
  </div>
</template>
