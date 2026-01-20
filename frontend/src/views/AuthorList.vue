<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const authors = ref([])
const loading = ref(true)

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
  <div class="space-y-6">
    <div class="flex justify-between items-center">
      <h2 class="text-2xl font-bold text-gray-900">Authors</h2>
    </div>

    <div v-if="loading" class="text-center py-10 text-gray-500">Loading...</div>
    
    <div v-else class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <div 
        v-for="author in authors" 
        :key="author.id" 
        class="bg-white overflow-hidden shadow rounded-lg hover:shadow-md transition-shadow cursor-pointer border border-transparent hover:border-indigo-500"
        @click="$router.push(`/authors/${author.id}`)"
      >
        <div class="px-4 py-5 sm:p-6 flex items-center space-x-4">
          <img 
            v-if="author.avatar_url" 
            :src="author.avatar_url" 
            alt="" 
            class="h-16 w-16 rounded-full bg-gray-100"
          >
          <div v-else class="h-16 w-16 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xl font-bold">
            {{ author.name.charAt(0) }}
          </div>
          
          <div class="flex-1 min-w-0">
            <h3 class="text-lg font-medium text-gray-900 truncate">
              {{ author.name }}
            </h3>
            <p class="text-sm text-gray-500 truncate">
              Platform: {{ author.platform }}
            </p>
            <div v-if="author.author_status" class="mt-2 flex flex-wrap gap-2 text-xs">
              <span class="px-2 py-1 rounded bg-gray-100 text-gray-700">
                Videos: {{ author.author_status.total_videos }}
              </span>
              <span class="px-2 py-1 rounded bg-green-100 text-green-700">
                ASR ready: {{ author.author_status.asr_status_counts.ready }}
              </span>
              <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
                ASR fallback: {{ author.author_status.asr_status_counts.fallback }}
              </span>
              <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
                ASR pending: {{ author.author_status.asr_status_counts.pending }}
              </span>
              <span class="px-2 py-1 rounded bg-red-100 text-red-700">
                ASR missing: {{ author.author_status.asr_status_counts.missing }}
              </span>
              <span class="px-2 py-1 rounded bg-green-100 text-green-700">
                Summary ready: {{ author.author_status.summary_status_counts.ready }}
              </span>
              <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
                Summary pending: {{ author.author_status.summary_status_counts.pending }}
              </span>
              <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
                Summary skipped: {{ author.author_status.summary_status_counts.skipped_fallback }}
              </span>
              <span class="px-2 py-1 rounded bg-red-100 text-red-700">
                Summary blocked: {{ author.author_status.summary_status_counts.blocked }}
              </span>
              <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
                Quality full: {{ author.author_status.content_quality_counts.full }}
              </span>
              <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
                Quality summary: {{ author.author_status.content_quality_counts.summary }}
              </span>
              <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
                Quality missing: {{ author.author_status.content_quality_counts.missing }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
