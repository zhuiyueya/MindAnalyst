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
const selectedContentType = ref('')

const summaryNormalized = computed(() => {
  if (!summary.value || !summary.value.json_data) return null
  return summary.value.json_data.normalized || summary.value.json_data
})

const fetchData = async () => {
  try {
    const res = await api.getVideo(videoId)
    video.value = res.data.video
    summary.value = res.data.summary
    segments.value = res.data.segments
    selectedContentType.value = video.value?.content_type || ''
    
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

const saveContentType = async () => {
  processing.value = true
  try {
    await api.setVideoType(videoId, { content_type: selectedContentType.value || null })
    await fetchData()
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

onMounted(fetchData)

const triggerResummarize = async (includeFallback = false) => {
  const includeFallbackFlag = includeFallback instanceof Event ? false : includeFallback
  const message = includeFallbackFlag
    ? 'Re-summarize this video (including fallback transcript)?'
    : 'Re-summarize this video?'
  if (!confirm(message)) return
  processing.value = true
  try {
    await api.resummarizeVideo(videoId, includeFallbackFlag)
    alert('Task started.')
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

const triggerReprocessAsr = async () => {
  if (!confirm('Re-fetch transcript (ASR/subtitles) for this video?')) return
  processing.value = true
  try {
    await api.reprocessVideoAsr(videoId)
    alert('Transcript reprocess started.')
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
        <span>Content Type: {{ video.content_type || 'generic' }}</span>
        <a :href="video.url" target="_blank" class="text-indigo-600 hover:underline">Original Link</a>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <div class="flex items-center space-x-2">
          <label class="text-sm text-gray-600">Content Type</label>
          <input
            v-model="selectedContentType"
            placeholder="e.g. insight / howto"
            class="border rounded px-2 py-1 text-sm"
          />
          <button
            @click="saveContentType"
            :disabled="processing"
            class="px-3 py-1 bg-gray-900 text-white rounded text-xs"
          >
            Save
          </button>
        </div>
        <button 
          @click="triggerResummarize"
          :disabled="processing"
          class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
        >
          Re-Summarize
        </button>
        <button 
          @click="triggerResummarize(true)"
          :disabled="processing"
          class="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm"
        >
          Re-Summarize (Include Fallback)
        </button>
        <button 
          @click="triggerReprocessAsr"
          :disabled="processing"
          class="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 text-sm"
        >
          Re-Fetch Transcript (ASR)
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
            <div v-if="summaryNormalized && summaryNormalized.one_liner" class="mb-4 bg-blue-50 p-3 rounded">
                <strong>One Liner:</strong> {{ summaryNormalized.one_liner }}
            </div>
            
            <div v-if="summaryNormalized && summaryNormalized.key_points">
                <strong>Key Points:</strong>
                <ul class="list-disc pl-5 space-y-1 mt-2">
                    <li v-for="(point, idx) in summaryNormalized.key_points" :key="idx">{{ point }}</li>
                </ul>
            </div>

            <div v-if="summaryNormalized && summaryNormalized.principles && summaryNormalized.principles.length" class="mt-4">
                <strong>Core Principles:</strong>
                <ul class="list-disc pl-5 space-y-1 mt-2">
                    <li v-for="(item, idx) in summaryNormalized.principles" :key="`p-${idx}`">{{ item }}</li>
                </ul>
            </div>

            <div v-if="summaryNormalized && summaryNormalized.actionable_guidelines && summaryNormalized.actionable_guidelines.length" class="mt-4">
                <strong>Actionable Guidelines:</strong>
                <ul class="list-disc pl-5 space-y-1 mt-2">
                    <li v-for="(item, idx) in summaryNormalized.actionable_guidelines" :key="`a-${idx}`">{{ item }}</li>
                </ul>
            </div>

            <div v-if="summaryNormalized && summaryNormalized.cognitive_warnings && summaryNormalized.cognitive_warnings.length" class="mt-4">
                <strong>Cognitive Warnings:</strong>
                <ul class="list-disc pl-5 space-y-1 mt-2">
                    <li v-for="(item, idx) in summaryNormalized.cognitive_warnings" :key="`w-${idx}`">{{ item }}</li>
                </ul>
            </div>

            <div v-if="summaryNormalized && summaryNormalized.case_studies && summaryNormalized.case_studies.length" class="mt-4">
                <strong>Case Studies:</strong>
                <div class="mt-2 space-y-3">
                    <div v-for="(item, idx) in summaryNormalized.case_studies" :key="`c-${idx}`" class="rounded border border-gray-200 p-3">
                        <div v-if="item.description" class="text-gray-800">{{ item.description }}</div>
                        <div v-else class="space-y-1 text-gray-700">
                            <div v-if="item.背景"><strong>背景：</strong>{{ item.背景 }}</div>
                            <div v-if="item['问题根源（感性/理性）']"><strong>问题根源：</strong>{{ item['问题根源（感性/理性）'] }}</div>
                            <div v-if="item.导致的后果"><strong>导致的后果：</strong>{{ item.导致的后果 }}</div>
                            <div v-if="item.正确的做法"><strong>正确的做法：</strong>{{ item.正确的做法 }}</div>
                        </div>
                    </div>
                </div>
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
