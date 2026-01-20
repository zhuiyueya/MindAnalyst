<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const md = new MarkdownIt()

const author = ref(null)
const report = ref(null)
const reportsByType = ref({})
const selectedReportType = ref('')
const selectedAuthorType = ref('')
const videos = ref([])
const authorStatus = ref(null)
const loading = ref(true)
const activeTab = ref('report')
const processing = ref(false)

const authorId = route.params.id

const fetchData = async () => {
  try {
    const [authRes, vidRes] = await Promise.all([
      api.getAuthor(authorId),
      api.getAuthorVideos(authorId)
    ])
    
    author.value = authRes.data.author
    report.value = authRes.data.latest_report
    reportsByType.value = authRes.data.reports_by_type || {}
    selectedAuthorType.value = author.value?.author_type || ''
    if (selectedAuthorType.value && reportsByType.value[selectedAuthorType.value]) {
      selectedReportType.value = selectedAuthorType.value
    } else {
      const types = Object.keys(reportsByType.value)
      selectedReportType.value = types.length ? types[0] : ''
    }
    videos.value = vidRes.data
    authorStatus.value = authRes.data.author_status || null
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

const activeReport = computed(() => {
  if (selectedReportType.value && reportsByType.value[selectedReportType.value]) {
    return reportsByType.value[selectedReportType.value][0]
  }
  return report.value
})

const reportTypes = computed(() => Object.keys(reportsByType.value || {}))

const statusClass = (status) => {
  switch (status) {
    case 'ready':
      return 'bg-green-100 text-green-700'
    case 'fallback':
      return 'bg-amber-100 text-amber-700'
    case 'missing':
      return 'bg-red-100 text-red-700'
    case 'blocked':
      return 'bg-red-100 text-red-700'
    case 'skipped_fallback':
      return 'bg-yellow-100 text-yellow-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

const renderReport = computed(() => {
  if (!activeReport.value || !activeReport.value.content) return 'No report generated yet.'
  return md.render(activeReport.value.content)
})

const saveAuthorType = async () => {
  processing.value = true
  try {
    await api.setAuthorType(authorId, { author_type: selectedAuthorType.value || null })
    await fetchData()
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

const triggerRegenerateReport = async () => {
  if (!confirm('Regenerate author report? This may take a while.')) return
  processing.value = true
  try {
    await api.regenerateReport(authorId)
    alert('Task started. Check back later.')
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

const triggerResummarizeAll = async (includeFallback = false) => {
  const includeFallbackFlag = includeFallback instanceof Event ? false : includeFallback
  const message = includeFallbackFlag
    ? 'Re-summarize ALL videos (including fallback transcripts)?'
    : 'Re-summarize ALL videos? This is a heavy operation.'
  if (!confirm(message)) return
  processing.value = true
  try {
    await api.resummarizeAll(authorId, includeFallbackFlag)
    alert('Batch task started.')
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}

const triggerReprocessAsr = async () => {
  if (!confirm('Re-fetch transcripts (ASR/subtitles) for this author?')) return
  processing.value = true
  try {
    await api.reprocessAuthorAsr(authorId)
    alert('Transcript reprocess started.')
  } catch (e) {
    alert('Failed: ' + e.message)
  } finally {
    processing.value = false
  }
}
</script>

<template>
  <div v-if="loading" class="text-center py-10">Loading...</div>
  <div v-else class="space-y-6">
    <!-- Header -->
    <div class="bg-white shadow rounded-lg p-6">
      <div class="flex items-center space-x-6">
        <img 
          v-if="author.avatar_url" 
          :src="author.avatar_url" 
          class="h-24 w-24 rounded-full"
        >
        <div class="flex-1">
          <h2 class="text-3xl font-bold text-gray-900">{{ author.name }}</h2>
          <p class="text-gray-500 mt-1">
            <a :href="author.homepage_url" target="_blank" class="text-indigo-600 hover:underline">
              {{ author.homepage_url }}
            </a>
          </p>
          <div v-if="authorStatus" class="mt-3 flex flex-wrap gap-2 text-xs">
            <span class="px-2 py-1 rounded bg-gray-100 text-gray-700">
              Videos: {{ authorStatus.total_videos }}
            </span>
            <span class="px-2 py-1 rounded bg-green-100 text-green-700">
              ASR ready: {{ authorStatus.asr_status_counts.ready }}
            </span>
            <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
              ASR fallback: {{ authorStatus.asr_status_counts.fallback }}
            </span>
            <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
              ASR pending: {{ authorStatus.asr_status_counts.pending }}
            </span>
            <span class="px-2 py-1 rounded bg-red-100 text-red-700">
              ASR missing: {{ authorStatus.asr_status_counts.missing }}
            </span>
            <span class="px-2 py-1 rounded bg-green-100 text-green-700">
              Summary ready: {{ authorStatus.summary_status_counts.ready }}
            </span>
            <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
              Summary pending: {{ authorStatus.summary_status_counts.pending }}
            </span>
            <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
              Summary skipped: {{ authorStatus.summary_status_counts.skipped_fallback }}
            </span>
            <span class="px-2 py-1 rounded bg-red-100 text-red-700">
              Summary blocked: {{ authorStatus.summary_status_counts.blocked }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              Quality full: {{ authorStatus.content_quality_counts.full }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              Quality summary: {{ authorStatus.content_quality_counts.summary }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              Quality missing: {{ authorStatus.content_quality_counts.missing }}
            </span>
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <div class="flex items-center space-x-2">
              <label class="text-sm text-gray-600">Author Type</label>
              <input
                v-model="selectedAuthorType"
                placeholder="e.g. insight / howto"
                class="border rounded px-2 py-1 text-sm"
              />
              <button
                @click="saveAuthorType"
                :disabled="processing"
                class="px-3 py-1 bg-gray-900 text-white rounded text-xs"
              >
                Save
              </button>
            </div>
            <button 
              @click="triggerRegenerateReport"
              :disabled="processing"
              class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
            >
              Regenerate Report
            </button>
            <button 
              @click="triggerResummarizeAll"
              :disabled="processing"
              class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm"
            >
              Re-Summarize All Videos
            </button>
            <button 
              @click="triggerResummarizeAll(true)"
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
              Re-Fetch Transcripts (ASR)
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button 
          @click="activeTab = 'report'"
          :class="[activeTab === 'report' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300', 'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm']"
        >
          Analysis Report
        </button>
        <button 
          @click="activeTab = 'videos'"
          :class="[activeTab === 'videos' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300', 'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm']"
        >
          Videos ({{ videos.length }})
        </button>
      </nav>
    </div>

    <!-- Content -->
    <div v-if="activeTab === 'report'" class="bg-white shadow rounded-lg p-6">
      <div v-if="reportTypes.length" class="mb-4 flex flex-wrap items-center gap-2">
        <span class="text-sm text-gray-600">Report Type:</span>
        <button
          v-for="type in reportTypes"
          :key="type"
          @click="selectedReportType = type"
          :class="[selectedReportType === type ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700', 'px-3 py-1 rounded text-xs']"
        >
          {{ type }}
        </button>
      </div>
      <div class="prose max-w-none" v-html="renderReport"></div>
    </div>

    <div v-else-if="activeTab === 'videos'" class="bg-white shadow rounded-lg overflow-hidden">
      <ul class="divide-y divide-gray-200">
        <li v-for="video in videos" :key="video.id" class="px-6 py-4 hover:bg-gray-50">
          <div class="flex items-center justify-between">
            <div class="flex-1 min-w-0">
              <h4 class="text-lg font-medium text-indigo-600 truncate cursor-pointer" @click="$router.push(`/videos/${video.id}`)">
                {{ video.title }}
              </h4>
              <p class="text-sm text-gray-500 mt-1">
                Published: {{ new Date(video.published_at).toLocaleDateString() }} |
                Type: {{ video.type }} |
                Content Type: {{ video.content_type || 'generic' }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2 text-xs">
                <span :class="statusClass(video.asr_status)" class="px-2 py-1 rounded">
                  ASR: {{ video.asr_status || 'pending' }}
                </span>
                <span :class="statusClass(video.summary_status)" class="px-2 py-1 rounded">
                  Summary: {{ video.summary_status || 'pending' }}
                </span>
                <span
                  :class="video.using_fallback ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-700'"
                  class="px-2 py-1 rounded"
                >
                  Fallback: {{ video.using_fallback ? 'Yes' : 'No' }}
                </span>
                <span
                  :class="video.content_quality === 'full'
                    ? 'bg-green-100 text-green-700'
                    : video.content_quality === 'summary'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-red-100 text-red-700'"
                  class="px-2 py-1 rounded"
                >
                  Quality: {{ video.content_quality || 'summary' }}
                </span>
              </div>
            </div>
            <div class="ml-4">
               <button 
                 @click="$router.push(`/videos/${video.id}`)"
                 class="text-indigo-600 hover:text-indigo-900 text-sm font-medium"
               >
                 View Details
               </button>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
