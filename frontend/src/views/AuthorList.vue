<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const authors = ref([])
const loading = ref(true)
const { t } = useI18n()

onMounted(async () => {
  try {
    const res = await api.getAuthors()
    authors.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-8">
    <div class="flex justify-between items-end border-b border-border pb-4">
      <h2 class="text-3xl font-bold text-text-primary uppercase tracking-widest">
        <span class="text-tertiary">/</span> {{ t('authors.title') }}
      </h2>
      <div class="font-mono text-xs text-text-secondary">
        TOTAL_RECORDS: <span class="text-tertiary">{{ authors.length }}</span>
      </div>
    </div>

    <div v-if="loading" class="text-center py-20 font-mono text-primary animate-pulse">
      > SYSTEM_LOADING_DATA...
    </div>
    
    <div v-else class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <div 
        v-for="author in authors" 
        :key="author.id" 
        class="terminal-card group hover:border-tertiary transition-colors cursor-pointer"
        @click="$router.push(`/authors/${author.id}`)"
      >
        <!-- Card Header -->
        <div class="flex items-start space-x-4 mb-6">
          <div class="relative">
            <img 
              v-if="author.avatar_url" 
              :src="author.avatar_url" 
              alt="" 
              class="h-16 w-16 grayscale group-hover:grayscale-0 transition-all border border-border"
            >
            <div v-else class="h-16 w-16 bg-surface border border-border flex items-center justify-center text-text-secondary text-xl font-bold font-mono">
              {{ author.name.charAt(0) }}
            </div>
            <!-- Status Dot -->
            <div class="absolute -bottom-1 -right-1 w-3 h-3 bg-primary border border-black"></div>
          </div>
          
          <div class="flex-1 min-w-0 overflow-hidden">
            <h3 class="text-lg font-bold text-text-primary truncate font-sans tracking-tight group-hover:text-tertiary transition-colors">
              {{ author.name }}
            </h3>
            <div class="text-xs font-mono text-text-secondary uppercase mt-1">
              PLATFORM: <span class="text-white">{{ author.platform }}</span>
            </div>
             <div class="text-[10px] font-mono text-text-secondary uppercase mt-1 truncate">
              ID: {{ author.id.substring(0, 8) }}...
            </div>
          </div>
        </div>

        <!-- Stats Grid -->
        <div v-if="author.author_status" class="grid grid-cols-2 gap-px bg-border border border-border">
          <div class="bg-surface p-2">
            <div class="text-[10px] text-text-secondary uppercase">VIDEOS</div>
            <div class="text-lg font-mono font-bold text-primary">{{ author.author_status.total_videos }}</div>
          </div>
          <div class="bg-surface p-2">
             <div class="text-[10px] text-text-secondary uppercase">QUALITY_FULL</div>
            <div class="text-lg font-mono font-bold text-tertiary">{{ author.author_status.content_quality_counts.full }}</div>
          </div>
          <div class="bg-surface p-2">
             <div class="text-[10px] text-text-secondary uppercase">ASR_READY</div>
            <div class="text-lg font-mono font-bold text-white">{{ author.author_status.asr_status_counts.ready }}</div>
          </div>
          <div class="bg-surface p-2">
             <div class="text-[10px] text-text-secondary uppercase">SUM_READY</div>
            <div class="text-lg font-mono font-bold text-white">{{ author.author_status.summary_status_counts.ready }}</div>
          </div>
        </div>
        
        <!-- Hover Decoration -->
        <div class="absolute bottom-0 left-0 w-full h-0.5 bg-tertiary transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left"></div>
      </div>
    </div>
  </div>
</template>
