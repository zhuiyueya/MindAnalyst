<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const md = new MarkdownIt()
const { t, locale } = useI18n()

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

const statusText = (status) => t(`status.values.${status || 'pending'}`)
const qualityText = (quality) => t(`status.values.${quality || 'summary'}`)

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
  if (!activeReport.value || !activeReport.value.content) return t('author.noReport')
  return md.render(activeReport.value.content)
})

const formatDate = (value) => {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat(locale.value).format(new Date(value))
  } catch (e) {
    return new Date(value).toLocaleDateString()
  }
}

const saveAuthorType = async () => {
  processing.value = true
  try {
    await api.setAuthorType(authorId, { author_type: selectedAuthorType.value || null })
    await fetchData()
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerRegenerateReport = async () => {
  if (!confirm(t('author.confirmRegenerateReport'))) return
  processing.value = true
  try {
    await api.regenerateReport(authorId)
    alert(t('common.checkBackLater'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerResummarizeAll = async (includeFallback = false) => {
  const includeFallbackFlag = includeFallback instanceof Event ? false : includeFallback
  const message = includeFallbackFlag
    ? t('author.confirmResummarizeAllIncludeFallback')
    : t('author.confirmResummarizeAll')
  if (!confirm(message)) return
  processing.value = true
  try {
    await api.resummarizeAll(authorId, includeFallbackFlag)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerResummarizePending = async () => {
  if (!confirm(t('author.confirmResummarizePending'))) return
  processing.value = true
  try {
    await api.resummarizePending(authorId)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerReprocessAsr = async () => {
  if (!confirm(t('author.confirmReprocessAsr'))) return
  processing.value = true
  try {
    await api.reprocessAuthorAsr(authorId)
    alert(t('common.transcriptReprocessStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}
</script>

<template>
  <div v-if="loading" class="text-center py-10">{{ t('common.loading') }}</div>
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
              {{ t('author.status.videos') }}: {{ authorStatus.total_videos }}
            </span>
            <span class="px-2 py-1 rounded bg-green-100 text-green-700">
              {{ t('author.status.asrReady') }}: {{ authorStatus.asr_status_counts.ready }}
            </span>
            <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
              {{ t('author.status.asrFallback') }}: {{ authorStatus.asr_status_counts.fallback }}
            </span>
            <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
              {{ t('author.status.asrPending') }}: {{ authorStatus.asr_status_counts.pending }}
            </span>
            <span class="px-2 py-1 rounded bg-red-100 text-red-700">
              {{ t('author.status.asrMissing') }}: {{ authorStatus.asr_status_counts.missing }}
            </span>
            <span class="px-2 py-1 rounded bg-green-100 text-green-700">
              {{ t('author.status.summaryReady') }}: {{ authorStatus.summary_status_counts.ready }}
            </span>
            <span class="px-2 py-1 rounded bg-yellow-100 text-yellow-700">
              {{ t('author.status.summaryPending') }}: {{ authorStatus.summary_status_counts.pending }}
            </span>
            <span class="px-2 py-1 rounded bg-amber-100 text-amber-700">
              {{ t('author.status.summarySkipped') }}: {{ authorStatus.summary_status_counts.skipped_fallback }}
            </span>
            <span class="px-2 py-1 rounded bg-red-100 text-red-700">
              {{ t('author.status.summaryBlocked') }}: {{ authorStatus.summary_status_counts.blocked }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              {{ t('author.status.qualityFull') }}: {{ authorStatus.content_quality_counts.full }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              {{ t('author.status.qualitySummary') }}: {{ authorStatus.content_quality_counts.summary }}
            </span>
            <span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700">
              {{ t('author.status.qualityMissing') }}: {{ authorStatus.content_quality_counts.missing }}
            </span>
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <div class="flex items-center space-x-2">
              <label class="text-sm text-gray-600">{{ t('author.authorTypeLabel') }}</label>
              <input
                v-model="selectedAuthorType"
                :placeholder="t('author.authorTypePlaceholder')"
                class="border rounded px-2 py-1 text-sm"
              />
              <button
                @click="saveAuthorType"
                :disabled="processing"
                class="px-3 py-1 bg-gray-900 text-white rounded text-xs"
              >
                {{ t('common.save') }}
              </button>
            </div>
            <button 
              @click="triggerRegenerateReport"
              :disabled="processing"
              class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
            >
              {{ t('author.regenerateReport') }}
            </button>
            <button 
              @click="triggerResummarizeAll"
              :disabled="processing"
              class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm"
            >
              {{ t('author.resummarizeAll') }}
            </button>
            <button 
              @click="triggerResummarizePending"
              :disabled="processing"
              class="px-4 py-2 bg-teal-600 text-white rounded hover:bg-teal-700 disabled:opacity-50 text-sm"
            >
              {{ t('author.resummarizePending') }}
            </button>
            <button 
              @click="triggerResummarizeAll(true)"
              :disabled="processing"
              class="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm"
            >
              {{ t('author.resummarizeAllIncludeFallback') }}
            </button>
            <button 
              @click="triggerReprocessAsr"
              :disabled="processing"
              class="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 text-sm"
            >
              {{ t('author.reprocessAsr') }}
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
          {{ t('author.analysisReportTab') }}
        </button>
        <button 
          @click="activeTab = 'videos'"
          :class="[activeTab === 'videos' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300', 'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm']"
        >
          {{ t('author.videosTab') }} ({{ videos.length }})
        </button>
      </nav>
    </div>

    <!-- Content -->
    <div v-if="activeTab === 'report'" class="bg-white shadow rounded-lg p-6">
      <div v-if="reportTypes.length" class="mb-4 flex flex-wrap items-center gap-2">
        <span class="text-sm text-gray-600">{{ t('common.reportType') }}:</span>
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
                {{ t('common.published') }}: {{ formatDate(video.published_at) }} |
                {{ t('common.type') }}: {{ video.type }} |
                {{ t('common.contentType') }}: {{ video.content_type || 'generic' }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2 text-xs">
                <span :class="statusClass(video.asr_status)" class="px-2 py-1 rounded">
                  {{ t('status.labels.asr') }}: {{ statusText(video.asr_status) }}
                </span>
                <span :class="statusClass(video.summary_status)" class="px-2 py-1 rounded">
                  {{ t('status.labels.summary') }}: {{ statusText(video.summary_status) }}
                </span>
                <span
                  :class="video.using_fallback ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-700'"
                  class="px-2 py-1 rounded"
                >
                  {{ t('status.labels.fallback') }}: {{ video.using_fallback ? t('common.yes') : t('common.no') }}
                </span>
                <span
                  :class="video.content_quality === 'full'
                    ? 'bg-green-100 text-green-700'
                    : video.content_quality === 'summary'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-red-100 text-red-700'"
                  class="px-2 py-1 rounded"
                >
                  {{ t('status.labels.quality') }}: {{ qualityText(video.content_quality) }}
                </span>
              </div>
            </div>
            <div class="ml-4">
               <button 
                 @click="$router.push(`/videos/${video.id}`)"
                 class="text-indigo-600 hover:text-indigo-900 text-sm font-medium"
               >
                 {{ t('common.viewDetails') }}
               </button>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
