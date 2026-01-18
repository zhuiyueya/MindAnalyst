<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const videoId = route.params.id

const video = ref(null)
const summary = ref(null)
const segments = ref([])
const playbackUrl = ref('')
const loading = ref(true)
const processing = ref(false)

const fetchData = async () => {
  try {
    const res = await api.getVideo(videoId)
    video.value = res.data.video
    summary.value = res.data.summary
    segments.value = res.data.segments
    
    // Try to get playback url
    try {
        const urlRes = await api.getVideoPlayback(videoId)
        playbackUrl.value = urlRes.data.url
    } catch (e) {
        console.warn("Playback URL not available:", e)
    }
    
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

const triggerResummarize = async () => {
  if (!confirm('Re-summarize this video?')) return
  processing.value = true
  try {
    await api.resummarizeVideo(videoId)
    alert('Task started.')
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

const formatTime = (ms) => {
    const s = Math.floor(ms / 1000)
    const m = Math.floor(s / 60)
    const rs = s % 60
    return `${m.toString().padStart(2, '0')}:${rs.toString().padStart(2, '0')}`
}
</script>

<template>
  <div v-if="loading" class="text-center py-10">Loading...</div>
  <div v-else class="space-y-6">
    <!-- Header -->
    <div class="bg-white shadow rounded-lg p-6">
      <h2 class="text-2xl font-bold text-gray-900">{{ video.title }}</h2>
      <div class="mt-2 flex items-center space-x-4 text-sm text-gray-500">
        <span>{{ new Date(video.published_at).toLocaleDateString() }}</span>
        <span>Quality: {{ video.content_quality }}</span>
        <a :href="video.url" target="_blank" class="text-indigo-600 hover:underline">Original Link</a>
      </div>
      <div class="mt-4">
        <button 
          @click="triggerResummarize"
          :disabled="processing"
          class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
        >
          Re-Summarize
        </button>
      </div>
    </div>

    <!-- Playback -->
    <div v-if="playbackUrl" class="bg-white shadow rounded-lg p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">Original Audio/Video</h3>
      <audio controls class="w-full" :src="playbackUrl">
        Your browser does not support the audio element.
      </audio>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Summary -->
      <div class="bg-white shadow rounded-lg p-6 h-fit">
        <h3 class="text-lg font-medium text-gray-900 mb-4 border-b pb-2">Summary</h3>
        <div v-if="summary" class="prose max-w-none text-sm">
            <div v-if="summary.json_data && summary.json_data.one_liner" class="mb-4 bg-blue-50 p-3 rounded">
                <strong>One Liner:</strong> {{ summary.json_data.one_liner }}
            </div>
            
            <div v-if="summary.json_data && summary.json_data.key_points">
                <strong>Key Points:</strong>
                <ul class="list-disc pl-5 space-y-1 mt-2">
                    <li v-for="(point, idx) in summary.json_data.key_points" :key="idx">{{ point }}</li>
                </ul>
            </div>
            
            <div v-if="summary.content && !summary.json_data" class="whitespace-pre-wrap">
                {{ summary.content }}
            </div>
        </div>
        <div v-else class="text-gray-500 italic">No summary available.</div>
      </div>

      <!-- Transcript -->
      <div class="bg-white shadow rounded-lg p-6 max-h-[800px] overflow-y-auto">
        <h3 class="text-lg font-medium text-gray-900 mb-4 border-b pb-2">Transcript</h3>
        <div v-if="segments.length > 0" class="space-y-4">
            <div v-for="seg in segments" :key="seg.id" class="text-sm">
                <div class="text-xs text-gray-400 mb-1">
                    {{ formatTime(seg.start_time_ms) }} - {{ formatTime(seg.end_time_ms) }}
                </div>
                <p class="text-gray-800">{{ seg.text }}</p>
            </div>
        </div>
        <div v-else class="text-gray-500 italic">No transcript segments available.</div>
      </div>
    </div>
  </div>
</template>
