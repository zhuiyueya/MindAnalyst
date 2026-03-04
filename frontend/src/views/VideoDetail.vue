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
  <div v-if="loading" class="text-center py-20 font-mono text-primary animate-pulse">
    > {{ t('videoDetail.loadingMedia') }}
  </div>
  <div v-else class="flex flex-col h-[calc(100vh-80px)] overflow-hidden">
    <!-- Header (Fixed & Compact) -->
    <div class="terminal-card mb-4 flex-shrink-0 p-4">
      <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-3 mb-1">
             <button @click="$router.back()" class="text-xs text-text-secondary hover:text-primary flex-shrink-0">
               &lt; {{ t('common.backToAuthor') }}
             </button>
             <div class="h-3 w-px bg-border"></div>
             <h2 class="text-lg font-bold text-text-primary truncate font-sans tracking-tight">{{ video.title }}</h2>
          </div>
          
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] font-mono text-text-secondary">
             <span>{{ formatDate(video.published_at) }}</span>
             <span class="text-border">|</span>
             <span>{{ video.content_type || t('videoDetail.generic') }}</span>
             <span class="text-border">|</span>
             <a :href="video.url" target="_blank" class="text-tertiary hover:underline uppercase">[{{ t('videoDetail.openSource') }}]</a>
             
             <!-- Status Badges Inline -->
             <div class="flex items-center gap-2 ml-2">
                <span :class="video.asr_status === 'ready' ? 'text-primary' : 'text-secondary'" class="uppercase">
                  ASR:{{ statusText(video.asr_status) }}
                </span>
                <span :class="video.summary_status === 'ready' ? 'text-primary' : 'text-secondary'" class="uppercase">
                  SUM:{{ statusText(video.summary_status) }}
                </span>
                <span :class="video.content_quality === 'full' ? 'text-primary' : 'text-secondary'" class="uppercase">
                  QUAL:{{ qualityText(video.content_quality) }}
                </span>
             </div>
          </div>
        </div>

        <!-- Compact Actions -->
        <div class="flex flex-col items-end gap-2 flex-shrink-0">
           <div class="flex items-center gap-2">
              <input
                v-model="selectedContentType"
                :placeholder="t('author.authorTypePlaceholder')"
                class="terminal-input text-[10px] py-1 w-24 h-6"
              />
              <button @click="saveContentType" :disabled="processing" class="terminal-button text-[10px] py-0 px-2 h-6">
                {{ t('common.save') }}
              </button>
           </div>
           <div class="flex items-center gap-1">
              <button @click="triggerResummarize" :disabled="processing" class="terminal-button text-[10px] py-0 px-2 h-6">
                {{ t('video.resummarize').toUpperCase() }}
              </button>
              <button @click="triggerReprocessAsr" :disabled="processing" class="terminal-button-secondary text-[10px] py-0 px-2 h-6">
                ASR
              </button>
           </div>
        </div>
      </div>

      <!-- Collapsible Summary/Keywords -->
      <details class="mt-2 text-[10px] text-text-secondary cursor-pointer group">
         <summary class="hover:text-primary select-none list-none flex items-center gap-2">
            <span class="border border-border px-1 group-open:bg-primary group-open:text-black transition-colors">INFO</span>
            <span v-if="!videoShortSummary" class="italic opacity-50">{{ t('videoDetail.noSummaryData') }}</span>
            <span v-else class="truncate max-w-xl text-text-primary">{{ videoShortSummary }}</span>
         </summary>
         <div class="mt-2 pl-2 border-l border-border space-y-2 bg-surface/50 p-2">
            <div v-if="videoShortSummary">
               <span class="text-tertiary uppercase mr-2">{{ t('videoDetail.shortSummary') }}:</span>
               <span class="text-text-primary">{{ videoShortSummary }}</span>
            </div>
            <div v-if="videoShortKeywords.length" class="flex flex-wrap gap-1">
               <span class="text-tertiary uppercase mr-2">{{ t('videoDetail.keywords') }}:</span>
               <span v-for="kw in videoShortKeywords" :key="kw" class="px-1 border border-border text-text-primary bg-black/20">
                 {{ kw }}
               </span>
            </div>
         </div>
      </details>
    </div>

    <!-- Playback (Fixed if present, scrollable if large?) -> Keep it scrollable with content -->
    
    <!-- Content Area (Scrollable) -->
    <div class="flex-1 overflow-y-auto pr-2 scrollbar-terminal space-y-6 pb-12">
        <div v-if="playbackUrl" class="terminal-card">
          <h3 class="text-xs font-bold text-text-secondary uppercase mb-4 flex items-center">
            <span class="w-1.5 h-1.5 bg-tertiary mr-2"></span>
            {{ t('videoDetail.mediaPlayback') }}
          </h3>
          <audio controls class="w-full h-8" :src="playbackUrl">
            {{ t('video.audioNotSupported') }}
          </audio>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Summary -->
          <div class="terminal-card h-fit">
            <h3 class="text-xs font-bold text-text-secondary uppercase mb-4 border-b border-border pb-2 flex items-center justify-between sticky top-0 bg-surface z-10 pt-2">
               <span>{{ t('videoDetail.analysisSummary') }}</span>
               <span class="text-[10px] text-primary">{{ t('videoDetail.processed') }}</span>
            </h3>
            
            <div v-if="summary" class="prose prose-invert max-w-none text-sm font-mono leading-relaxed">
                <div v-if="summaryBlocks.length" class="space-y-4">
                    <div v-for="(block, idx) in summaryBlocks" :key="idx" class="border border-border p-4 bg-surface/50">
                        <div class="text-[10px] font-bold uppercase tracking-wide text-tertiary mb-2 border-b border-border/50 pb-1">{{ block.type }}</div>
                        <div class="prose prose-invert max-w-none text-xs" v-html="renderMarkdown(block.text)"></div>
                    </div>
                </div>
                <div v-else-if="bracketBlocks.length" class="space-y-4">
                    <div v-for="(block, idx) in bracketBlocks" :key="idx" class="border border-border p-4 bg-surface/50">
                        <div class="text-[10px] font-bold tracking-wide text-tertiary mb-2 border-b border-border/50 pb-1">[{{ block.tag }}]</div>
                        <div class="prose prose-invert max-w-none text-xs" v-html="renderMarkdown(block.text)"></div>
                    </div>
                </div>
                <div v-else-if="summary.content" class="whitespace-pre-wrap text-xs">
                    {{ summary.content }}
                </div>
            </div>
            <div v-else class="text-text-secondary italic text-xs border border-dashed border-border p-4 text-center">{{ t('videoDetail.noSummaryData') }}</div>
          </div>

          <!-- Transcript -->
          <div class="terminal-card h-fit">
            <h3 class="text-xs font-bold text-text-secondary uppercase mb-4 border-b border-border pb-2 flex items-center justify-between sticky top-0 bg-surface z-10 pt-2">
               <span>{{ t('videoDetail.rawTranscript') }}</span>
               <span class="text-[10px] text-secondary">{{ segments.length }} {{ t('videoDetail.segments') }}</span>
            </h3>
            
            <div v-if="segments.length > 0" class="space-y-2 font-mono max-h-[800px] overflow-y-auto scrollbar-terminal">
                <div v-for="seg in segments" :key="seg.id" class="text-xs hover:bg-white/5 p-1 rounded transition-colors group">
                    <div class="flex gap-3">
                        <span class="text-text-secondary min-w-[80px] select-none group-hover:text-primary transition-colors">
                            [{{ formatTime(seg.start_time_ms) }}]
                        </span>
                        <p class="text-text-primary group-hover:text-white">{{ seg.text }}</p>
                    </div>
                </div>
            </div>
            <div v-else class="text-text-secondary italic text-xs border border-dashed border-border p-4 text-center">{{ t('videoDetail.noTranscriptData') }}</div>
          </div>
        </div>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-terminal::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-terminal::-webkit-scrollbar-track {
  @apply bg-background;
}
.scrollbar-terminal::-webkit-scrollbar-thumb {
  @apply bg-border hover:bg-primary;
}
</style>
