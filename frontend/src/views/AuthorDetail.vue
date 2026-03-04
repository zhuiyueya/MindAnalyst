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
const categoryReportsByType = ref({})
const selectedReportType = ref('')
const selectedCategory = ref('')
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
    categoryReportsByType.value = authRes.data.category_reports_by_type || {}
    selectedAuthorType.value = author.value?.author_type || ''
    if (selectedAuthorType.value && reportsByType.value[selectedAuthorType.value]) {
      selectedReportType.value = selectedAuthorType.value
    } else {
      const types = Object.keys(reportsByType.value)
      selectedReportType.value = types.length ? types[0] : ''
    }
    videos.value = vidRes.data
    authorStatus.value = authRes.data.author_status || null

    const categoriesForType = categoryReportsByType.value?.[selectedReportType.value] || {}
    const keys = Object.keys(categoriesForType)
    selectedCategory.value = keys.length ? keys[0] : ''
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const escapeHtml = (value) => {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const isPlainObject = (value) => Object.prototype.toString.call(value) === '[object Object]'

const renderJsonValue = (value) => {
  if (value === null || value === undefined) {
    return '<span class="text-text-secondary">-</span>'
  }
  if (typeof value === 'string') {
    return `<div class="prose prose-invert max-w-none text-text-primary text-sm">${md.render(value)}</div>`
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return `<span class="text-primary font-mono">${escapeHtml(value)}</span>`
  }
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="text-text-secondary">[]</span>'
    return `<div class="space-y-2 border-l border-border pl-4">${value
      .map((item) => `<div class="my-2">${renderJsonValue(item)}</div>`)
      .join('')}</div>`
  }
  if (isPlainObject(value)) {
    const entries = Object.entries(value)
    if (!entries.length) return '<span class="text-text-secondary">{}</span>'
    return `<div class="space-y-3 border-l border-border pl-4">${entries
      .map(
        ([key, val]) => `
          <div class="my-2">
            <div class="text-xs font-bold uppercase tracking-wide text-tertiary mb-1">${escapeHtml(key)}</div>
            ${renderJsonValue(val)}
          </div>
        `
      )
      .join('')}</div>`
  }
  return `<span class="text-text-primary">${escapeHtml(value)}</span>`
}

const renderJsonBlock = (value) => `<div class="space-y-4 font-mono text-sm">${renderJsonValue(value)}</div>`

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
const authorCategories = computed(() => author.value?.category_list || [])

const categoryReportKeys = computed(() => {
  const type = selectedReportType.value || ''
  const group = categoryReportsByType.value?.[type] || {}
  return Object.keys(group)
})

const activeCategoryReport = computed(() => {
  const type = selectedReportType.value || ''
  const group = categoryReportsByType.value?.[type] || {}
  if (!selectedCategory.value) return null
  return group[selectedCategory.value] || null
})

const videoCategoryLabel = (value) => {
  if (!value) return ''
  return String(value)
}

const videoShortSummary = (video) => {
  const payload = video?.short_json
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (typeof payload === 'object') {
    return String(payload.summary || '')
  }
  return ''
}

const videoShortKeywords = (video) => {
  const payload = video?.short_json
  if (!payload || typeof payload !== 'object') return []
  const keywords = payload.keywords
  return Array.isArray(keywords) ? keywords.map((x) => String(x)) : []
}

const statusClass = (status) => {
  switch (status) {
    case 'ready':
      return 'text-primary'
    case 'fallback':
      return 'text-secondary'
    case 'missing':
      return 'text-red-500'
    case 'blocked':
      return 'text-red-500'
    case 'skipped_fallback':
      return 'text-secondary'
    default:
      return 'text-text-secondary'
  }
}

const renderReport = computed(() => {
  const reportObj = activeCategoryReport.value || activeReport.value
  if (!reportObj || !reportObj.content) return t('author.noReport')
  const content = reportObj.content
  try {
    const parsed = JSON.parse(content)
    return renderJsonBlock(parsed)
  } catch (e) {
    return `<div class="prose prose-invert max-w-none text-text-primary">${md.render(content)}</div>`
  }
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

const triggerCompressShortSummaries = async () => {
  if (!confirm(t('author.confirmCompressShortSummaries'))) return
  processing.value = true
  try {
    await api.compressShortSummaries(authorId)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerGenerateCategories = async () => {
  if (!confirm(t('author.confirmGenerateCategories'))) return
  processing.value = true
  try {
    await api.generateCategories(authorId)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerGenerateCategoryReports = async () => {
  if (!confirm(t('author.confirmGenerateCategoryReports'))) return
  processing.value = true
  try {
    await api.generateCategoryReports(authorId)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerRagReindexAuthor = async () => {
  if (!confirm(t('rag.confirmReindexAuthor'))) return
  processing.value = true
  try {
    await api.ragReindex(authorId)
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerRagReindexAll = async () => {
  if (!confirm(t('rag.confirmReindexAll'))) return
  processing.value = true
  try {
    await api.ragReindex(null)
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
  <div v-if="loading" class="text-center py-20 font-mono text-primary animate-pulse">
    > {{ t('authorDetail.accessingArchives') }}
  </div>
  <div v-else class="flex flex-col lg:flex-row gap-8 h-[calc(100vh-80px)] overflow-hidden">
    
    <!-- Left Column: Identity & Actions (Fixed) -->
    <div class="lg:w-1/3 space-y-6 overflow-y-auto pr-2 scrollbar-terminal">
      <div class="terminal-card">
        <div class="flex items-center justify-between mb-4 border-b border-border pb-2">
           <button @click="$router.push('/authors')" class="text-xs text-text-secondary hover:text-primary flex items-center">
             &lt; {{ t('common.backToAuthors') }}
           </button>
           <span class="text-[10px] text-text-secondary uppercase">ID_CARD</span>
        </div>

        <div class="flex flex-col items-center text-center mb-6">
          <div class="relative mb-4">
             <img 
              v-if="author.avatar_url" 
              :src="author.avatar_url" 
              class="h-32 w-32 grayscale border-2 border-primary p-1"
            >
             <div v-else class="h-32 w-32 bg-surface border-2 border-primary flex items-center justify-center text-text-secondary text-4xl font-bold font-mono">
              {{ author.name.charAt(0) }}
            </div>
          </div>
          <h2 class="text-2xl font-bold text-text-primary tracking-tight">{{ author.name }}</h2>
          <a :href="author.homepage_url" target="_blank" class="text-xs font-mono text-tertiary hover:underline mt-1 truncate max-w-full">
            {{ author.homepage_url }}
          </a>
        </div>

        <div class="border-t border-border pt-4 space-y-3 font-mono text-xs">
           <div class="flex justify-between">
            <span class="text-text-secondary">{{ t('authorDetail.status') }}</span>
            <span class="text-primary">{{ t('authorDetail.active') }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-text-secondary">{{ t('authorDetail.totalVids') }}</span>
            <span class="text-white">{{ authorStatus?.total_videos || 0 }}</span>
          </div>
          <div class="flex justify-between">
             <span class="text-text-secondary">{{ t('authorDetail.asrCoverage') }}</span>
             <span class="text-white">{{ authorStatus?.asr_status_counts.ready || 0 }}</span>
          </div>
          <div class="flex justify-between">
             <span class="text-text-secondary">{{ t('authorList.qualityFull') }}</span>
             <span class="text-white">{{ authorStatus?.content_quality_counts.full || 0 }}</span>
          </div>
        </div>

        <div v-if="authorCategories.length" class="mt-4 pt-4 border-t border-border">
          <div class="text-[10px] text-text-secondary uppercase mb-2">{{ t('authorDetail.tags') }}</div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="category in authorCategories"
              :key="category"
              class="px-2 py-0.5 border border-tertiary/50 text-tertiary text-[10px]"
            >
              {{ category }}
            </span>
          </div>
        </div>
      </div>

      <!-- Control Panel -->
      <div class="terminal-card">
        <h3 class="text-xs font-bold text-text-secondary uppercase mb-4 flex items-center">
          <span class="w-1.5 h-1.5 bg-secondary mr-2"></span>
          {{ t('authorDetail.controlPanel') }}
        </h3>
        
        <div class="space-y-3">
          <div class="flex items-center space-x-2 mb-4">
            <input
              v-model="selectedAuthorType"
              :placeholder="t('author.authorTypePlaceholder')"
              class="terminal-input text-xs"
            />
            <button @click="saveAuthorType" :disabled="processing" class="terminal-button text-xs py-1 px-2">
              {{ t('common.save') }}
            </button>
          </div>

          <div class="grid grid-cols-1 gap-2">
            <button @click="triggerResummarizeAll" :disabled="processing" class="terminal-button text-xs text-center w-full">
              {{ t('author.resummarizeAll') }}
            </button>
            <button @click="triggerCompressShortSummaries" :disabled="processing" class="terminal-button text-xs text-center w-full">
              {{ t('author.compressShortSummaries') }}
            </button>
            <button @click="triggerGenerateCategories" :disabled="processing" class="terminal-button text-xs text-center w-full">
              {{ t('author.generateCategories') }}
            </button>
            <button @click="triggerGenerateCategoryReports" :disabled="processing" class="terminal-button text-xs text-center w-full">
              {{ t('author.generateCategoryReports') }}
            </button>
             <button @click="triggerRagReindexAuthor" :disabled="processing" class="terminal-button-secondary text-xs text-center w-full">
              {{ t('rag.reindexAuthor') }}
            </button>
          </div>
          
           <details class="text-[10px] text-text-secondary cursor-pointer mt-4">
            <summary class="hover:text-primary">{{ t('authorDetail.advancedOperations') }}</summary>
            <div class="grid grid-cols-1 gap-2 mt-2 pl-2 border-l border-border">
              <button @click="triggerRegenerateReport" class="text-left hover:text-white">>> {{ t('author.regenerateReport') }}</button>
              <button @click="triggerResummarizePending" class="text-left hover:text-white">>> {{ t('author.resummarizePending') }}</button>
              <button @click="triggerReprocessAsr" class="text-left hover:text-secondary">>> {{ t('author.reprocessAsr') }}</button>
              <button @click="triggerResummarizeAll(true)" class="text-left hover:text-secondary">>> {{ t('author.resummarizeAllIncludeFallback') }}</button>
            </div>
          </details>
        </div>
      </div>
    </div>

    <!-- Right Column: Data Feed (Scrollable) -->
    <div class="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
      <!-- Tabs -->
      <div class="flex border-b border-border mb-6 flex-shrink-0">
        <button 
          @click="activeTab = 'report'"
          :class="[activeTab === 'report' ? 'border-b-2 border-primary text-primary' : 'text-text-secondary hover:text-white', 'px-6 py-3 text-sm font-mono uppercase tracking-wider transition-colors']"
        >
          {{ t('author.analysisReportTab') }}
        </button>
        <button 
          @click="activeTab = 'videos'"
          :class="[activeTab === 'videos' ? 'border-b-2 border-primary text-primary' : 'text-text-secondary hover:text-white', 'px-6 py-3 text-sm font-mono uppercase tracking-wider transition-colors']"
        >
          {{ t('author.videosTab') }} [{{ videos.length }}]
        </button>
      </div>

      <div class="flex-1 overflow-y-auto pr-2 scrollbar-terminal">
        <!-- Report View -->
        <div v-if="activeTab === 'report'" class="terminal-card min-h-[500px]">
          <div class="flex flex-wrap gap-4 mb-6 border-b border-border pb-4 sticky top-0 bg-surface z-10 pt-2">
             <div v-if="reportTypes.length" class="flex items-center gap-2">
              <span class="text-xs text-text-secondary uppercase">{{ t('authorDetail.type') }}:</span>
              <button
                v-for="type in reportTypes"
                :key="type"
                @click="selectedReportType = type"
                :class="[selectedReportType === type ? 'bg-primary text-black' : 'bg-surface border border-border text-text-secondary', 'px-2 py-1 text-[10px] uppercase font-bold transition-colors']"
              >
                {{ type }}
              </button>
            </div>
             <div v-if="categoryReportKeys.length" class="flex items-center gap-2">
              <span class="text-xs text-text-secondary uppercase">{{ t('authorDetail.cat') }}:</span>
               <button
                v-for="cat in categoryReportKeys"
                :key="cat"
                @click="selectedCategory = cat"
                :class="[selectedCategory === cat ? 'bg-tertiary text-black' : 'bg-surface border border-border text-text-secondary', 'px-2 py-1 text-[10px] uppercase font-bold transition-colors']"
              >
                {{ cat }}
              </button>
            </div>
          </div>
          
          <div class="font-mono text-sm leading-relaxed" v-html="renderReport"></div>
        </div>

        <!-- Videos View -->
        <div v-else-if="activeTab === 'videos'" class="space-y-4 pb-12">
          <div v-for="video in videos" :key="video.id" class="terminal-card p-4 hover:border-primary/50 transition-colors group">
            <div class="flex justify-between items-start">
              <div class="flex-1">
                <h4 
                  class="text-base font-bold text-text-primary cursor-pointer hover:text-primary transition-colors mb-2" 
                  @click="$router.push(`/videos/${video.id}`)"
                >
                  {{ video.title }}
                </h4>
                <div class="flex flex-wrap gap-x-4 gap-y-2 text-[10px] font-mono text-text-secondary uppercase mb-3">
                  <span>{{ t('authorDetail.date') }}: {{ formatDate(video.published_at) }}</span>
                  <span>{{ t('authorDetail.type') }}: {{ video.type }}</span>
                  <span :class="statusClass(video.asr_status)">{{ t('authorDetail.asr') }}: {{ statusText(video.asr_status) }}</span>
                  <span :class="statusClass(video.summary_status)">{{ t('authorDetail.sum') }}: {{ statusText(video.summary_status) }}</span>
                  <span :class="video.content_quality === 'full' ? 'text-primary' : 'text-secondary'">{{ t('authorDetail.qual') }}: {{ qualityText(video.content_quality) }}</span>
                </div>
                
                <div v-if="videoShortSummary(video)" class="text-xs text-text-primary/80 font-mono pl-3 border-l-2 border-border group-hover:border-primary transition-colors">
                  {{ videoShortSummary(video) }}
                </div>
              </div>
               <button 
                   @click="$router.push(`/videos/${video.id}`)"
                   class="ml-4 text-tertiary text-xs hover:underline uppercase"
                 >
                   [{{ t('authorDetail.open') }}]
               </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
