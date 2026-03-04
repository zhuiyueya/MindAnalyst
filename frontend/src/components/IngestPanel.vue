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
  <div class="max-w-3xl mx-auto py-12">
    <div class="mb-8 border-b border-border pb-4">
      <h2 class="text-3xl font-bold text-text-primary uppercase tracking-widest flex items-center">
        <span class="text-primary mr-2">>></span> {{ t('ingest.title') }}
      </h2>
      <p class="font-mono text-xs text-text-secondary mt-2 pl-8">
        {{ t('ingest.protocol') }}: {{ t('ingest.bilibiliExtraction') }}
      </p>
    </div>
    
    <div class="terminal-card mb-8">
      <div class="grid grid-cols-1 gap-6">
        <div>
          <label class="block text-xs font-bold text-text-secondary uppercase mb-2 tracking-wider">
            {{ t('ingest.targetIdentifier') }}
          </label>
          <div class="flex items-center border-b border-border focus-within:border-primary transition-colors">
            <span class="text-text-secondary font-mono text-sm px-2 bg-surface/50">
              space.bilibili.com/
            </span>
            <input 
              v-model="mid"
              type="text"
              class="flex-1 bg-transparent border-none text-primary font-mono text-lg py-2 focus:ring-0 placeholder-gray-700"
              :placeholder="t('ingest.midPlaceholder')"
              @keyup.enter="handleIngest"
            />
          </div>
          <p class="mt-2 text-[10px] text-text-secondary font-mono">
            {{ t('ingest.midHelp') }}
          </p>
        </div>
        
        <div>
          <label class="block text-xs font-bold text-text-secondary uppercase mb-2 tracking-wider">
            {{ t('ingest.fetchLimit') }}
          </label>
          <input 
            v-model.number="limit"
            type="number"
            min="1"
            class="bg-transparent border border-border text-primary font-mono text-sm py-2 px-3 w-32 focus:border-primary focus:outline-none"
          />
        </div>

        <button 
          @click="handleIngest" 
          :disabled="isLoading || !mid"
          class="w-full py-4 border border-primary bg-primary/10 text-primary font-bold uppercase tracking-widest hover:bg-primary hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary/10 disabled:hover:text-primary relative overflow-hidden group"
        >
          <span v-if="isLoading" class="flex items-center justify-center">
            <span class="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full mr-3"></span>
            {{ t('ingest.processingRequest') }}
          </span>
          <span v-else class="group-hover:tracking-[0.2em] transition-all duration-300">
            {{ t('ingest.start').toUpperCase() }}
          </span>
        </button>
      </div>
    </div>

    <!-- System Output Log -->
    <div v-if="message || error" class="terminal-card min-h-[100px] font-mono text-sm mb-8">
      <div class="text-[10px] text-text-secondary uppercase mb-2 border-b border-border pb-1">{{ t('ingest.systemOutputLog') }}</div>
      
      <div v-if="message" class="text-primary">
        <span class="text-white">[{{ new Date().toLocaleTimeString() }}]</span> {{ t('ingest.successLabel') }}: {{ message }}
      </div>
      
      <div v-if="error" class="text-secondary">
        <span class="text-white">[{{ new Date().toLocaleTimeString() }}]</span> {{ t('ingest.errorLabel') }}: {{ error }}
      </div>
    </div>
    
    <!-- Protocol Documentation -->
    <div class="border border-border p-6 bg-black/20 text-xs font-mono text-text-secondary">
      <h3 class="font-bold text-white uppercase mb-4 flex items-center">
        <span class="w-2 h-2 bg-white mr-2"></span>
        {{ t('ingest.howItWorksTitle').toUpperCase() }}
      </h3>
      <ol class="space-y-2 list-decimal list-inside marker:text-primary">
        <li><span class="text-text-secondary">{{ t('ingest.step1') }}</span></li>
        <li><span class="text-text-secondary">{{ t('ingest.step2') }}</span></li>
        <li><span class="text-text-secondary">{{ t('ingest.step3') }}</span></li>
        <li><span class="text-text-secondary">{{ t('ingest.step4') }}</span></li>
      </ol>
    </div>
  </div>
</template>
