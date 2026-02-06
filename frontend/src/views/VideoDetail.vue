<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import api from '../api'

const route = useRoute()
const videoId = route.params.id
const { t, locale } = useI18n()
const md = new MarkdownIt()

const renderMarkdown = (value) => md.render(String(value || ''))

const video = ref(null)
const summary = ref(null)
const segments = ref([])
const playbackUrl = ref('')
const loading = ref(true)
const processing = ref(false)
const selectedContentType = ref('')

const summaryBlocks = computed(() => {
  if (!summary.value || !summary.value.json_data) return []
  const blocks = summary.value.json_data.blocks
  return Array.isArray(blocks) ? blocks : []
})

const videoShortSummary = computed(() => {
  const payload = summary.value?.short_json
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (typeof payload === 'object') {
    return String(payload.summary || '')
  }
  return ''
})

const videoShortKeywords = computed(() => {
  const payload = summary.value?.short_json
  if (!payload || typeof payload !== 'object') return []
  const keywords = payload.keywords
  return Array.isArray(keywords) ? keywords.map((x) => String(x)) : []
})

const bracketBlocks = computed(() => {
  const content = summary.value?.content
  if (!content || typeof content !== 'string') return []

  const re = /\[([^\]]+?)\]/g
  const matches = Array.from(content.matchAll(re))
  if (!matches.length) return []

  const blocks = []
  for (let i = 0; i < matches.length; i += 1) {
    const tag = matches[i][1]
    const start = matches[i].index + matches[i][0].length
    const end = i + 1 < matches.length ? matches[i + 1].index : content.length
    const text = content.slice(start, end).trim()
    blocks.push({ tag, text })
  }
  return blocks
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
    ? t('video.confirmResummarizeIncludeFallback')
    : t('video.confirmResummarize')
  if (!confirm(message)) return
  processing.value = true
  try {
    await api.resummarizeVideo(videoId, includeFallbackFlag)
    alert(t('common.taskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const triggerReprocessAsr = async () => {
  if (!confirm(t('video.confirmReprocessAsr'))) return
  processing.value = true
  try {
    await api.reprocessVideoAsr(videoId)
    alert(t('common.transcriptReprocessStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + e.message)
  } finally {
    processing.value = false
  }
}

const statusText = (status) => t(`status.values.${status || 'pending'}`)
const qualityText = (quality) => t(`status.values.${quality || 'summary'}`)

const formatDate = (value) => {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat(locale.value).format(new Date(value))
  } catch (e) {
    return new Date(value).toLocaleDateString()
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
  <div v-if="loading" class="text-center py-10">{{ t('common.loading') }}</div>
  <div v-else class="space-y-6">
    <!-- Header -->
    <div class="bg-white shadow rounded-lg p-6">
      <h2 class="text-2xl font-bold text-gray-900">{{ video.title }}</h2>
      <div class="mt-2 flex items-center space-x-4 text-sm text-gray-500">
        <span>{{ formatDate(video.published_at) }}</span>
        <span>{{ t('common.contentType') }}: {{ video.content_type || 'generic' }}</span>
        <a :href="video.url" target="_blank" class="text-indigo-600 hover:underline">{{ t('common.originalLink') }}</a>
      </div>
      <div class="mt-3 flex flex-wrap gap-2 text-xs">
        <span :class="video.asr_status === 'ready'
          ? 'bg-green-100 text-green-700'
          : video.asr_status === 'fallback'
            ? 'bg-amber-100 text-amber-700'
            : video.asr_status === 'missing'
              ? 'bg-red-100 text-red-700'
              : 'bg-yellow-100 text-yellow-700'"
          class="px-2 py-1 rounded"
        >
          {{ t('status.labels.asr') }}: {{ statusText(video.asr_status) }}
        </span>
        <span :class="video.summary_status === 'ready'
          ? 'bg-green-100 text-green-700'
          : video.summary_status === 'blocked'
            ? 'bg-red-100 text-red-700'
            : video.summary_status === 'skipped_fallback'
              ? 'bg-amber-100 text-amber-700'
              : 'bg-yellow-100 text-yellow-700'"
          class="px-2 py-1 rounded"
        >
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
        <span
          v-if="summary && summary.video_category"
          class="px-2 py-1 rounded bg-purple-100 text-purple-700"
        >
          {{ t('video.videoCategory') }}: {{ summary.video_category }}
        </span>
      </div>
      <div v-if="videoShortSummary" class="mt-3">
        <div class="text-xs text-gray-500 mb-1">{{ t('video.shortSummary') }}</div>
        <div class="text-sm text-gray-800 whitespace-pre-wrap">{{ videoShortSummary }}</div>
      </div>
      <div v-if="videoShortKeywords.length" class="mt-2 flex flex-wrap gap-2 text-xs">
        <span class="text-gray-500">{{ t('video.shortKeywords') }}:</span>
        <span
          v-for="kw in videoShortKeywords"
          :key="kw"
          class="px-2 py-1 rounded bg-sky-100 text-sky-700"
        >
          {{ kw }}
        </span>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <div class="flex items-center space-x-2">
          <label class="text-sm text-gray-600">{{ t('common.contentType') }}</label>
          <input
            v-model="selectedContentType"
            :placeholder="t('author.authorTypePlaceholder')"
            class="border rounded px-2 py-1 text-sm"
          />
          <button
            @click="saveContentType"
            :disabled="processing"
            class="px-3 py-1 bg-gray-900 text-white rounded text-xs"
          >
            {{ t('common.save') }}
          </button>
        </div>
        <button 
          @click="triggerResummarize"
          :disabled="processing"
          class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
        >
          {{ t('video.resummarize') }}
        </button>
        <button 
          @click="triggerResummarize(true)"
          :disabled="processing"
          class="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm"
        >
          {{ t('video.resummarizeIncludeFallback') }}
        </button>
        <button 
          @click="triggerReprocessAsr"
          :disabled="processing"
          class="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 text-sm"
        >
          {{ t('video.reprocessAsr') }}
        </button>
      </div>
    </div>

    <!-- Playback -->
    <div v-if="playbackUrl" class="bg-white shadow rounded-lg p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">{{ t('video.originalMedia') }}</h3>
      <audio controls class="w-full" :src="playbackUrl">
        {{ t('video.audioNotSupported') }}
      </audio>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Summary -->
      <div class="bg-white shadow rounded-lg p-6 h-fit">
        <h3 class="text-lg font-medium text-gray-900 mb-4 border-b pb-2">{{ t('video.summaryTitle') }}</h3>
        <div v-if="summary" class="prose max-w-none text-sm">
            <div v-if="summaryBlocks.length" class="space-y-3">
                <div v-for="(block, idx) in summaryBlocks" :key="idx" class="rounded border border-gray-200 p-3">
                    <div class="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">{{ block.type }}</div>
                    <div class="prose max-w-none" v-html="renderMarkdown(block.text)"></div>
                </div>
            </div>
            <div v-else-if="bracketBlocks.length" class="space-y-3">
                <div v-for="(block, idx) in bracketBlocks" :key="idx" class="rounded border border-gray-200 p-3">
                    <div class="text-xs font-semibold tracking-wide text-gray-500 mb-2">[{{ block.tag }}]</div>
                    <div class="prose max-w-none" v-html="renderMarkdown(block.text)"></div>
                </div>
            </div>
            <div v-else-if="summary.content" class="whitespace-pre-wrap">
                {{ summary.content }}
            </div>
        </div>
        <div v-else class="text-gray-500 italic">{{ t('video.noSummary') }}</div>
      </div>

      <!-- Transcript -->
      <div class="bg-white shadow rounded-lg p-6 max-h-[800px] overflow-y-auto">
        <h3 class="text-lg font-medium text-gray-900 mb-4 border-b pb-2">{{ t('video.transcriptTitle') }}</h3>
        <div v-if="segments.length > 0" class="space-y-4">
            <div v-for="seg in segments" :key="seg.id" class="text-sm">
                <div class="text-xs text-gray-400 mb-1">
                    {{ formatTime(seg.start_time_ms) }} - {{ formatTime(seg.end_time_ms) }}
                </div>
                <p class="text-gray-800">{{ seg.text }}</p>
            </div>
        </div>
        <div v-else class="text-gray-500 italic">{{ t('video.noTranscript') }}</div>
      </div>
    </div>
  </div>
</template>
