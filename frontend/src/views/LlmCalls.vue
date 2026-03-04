<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t, locale } = useI18n()

const logs = ref([])
const loading = ref(false)
const error = ref('')
const total = ref(0)
const limit = ref(30)
const offset = ref(0)

const filters = ref({
  task_type: '',
  content_type: '',
  profile_key: '',
  status: '',
  model: '',
  start_time: '',
  end_time: ''
})

const hasPrev = computed(() => offset.value > 0)
const hasNext = computed(() => offset.value + limit.value < total.value)

const formatDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value)
}

const formatJson = (value) => {
  if (!value || typeof value !== 'object') return value ?? ''
  return JSON.stringify(value, null, 2)
}

const getTruncationLabel = (meta) => {
  if (!meta || typeof meta !== 'object') return ''
  const truncated = Boolean(meta.input_truncated || meta.context_truncated)
  return truncated ? t('llmLogs.truncatedYes') : t('llmLogs.truncatedNo')
}

const fetchLogs = async (resetOffset = false) => {
  loading.value = true
  error.value = ''
  if (resetOffset) offset.value = 0
  try {
    const params = {
      limit: limit.value,
      offset: offset.value
    }
    Object.entries(filters.value).forEach(([key, value]) => {
      if (value) params[key] = value
    })
    const res = await api.listLlmCalls(params)
    logs.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    console.error(e)
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  fetchLogs(true)
}

const resetFilters = () => {
  filters.value = {
    task_type: '',
    content_type: '',
    profile_key: '',
    status: '',
    model: '',
    start_time: '',
    end_time: ''
  }
  fetchLogs(true)
}

const nextPage = () => {
  if (!hasNext.value) return
  offset.value += limit.value
  fetchLogs()
}

const prevPage = () => {
  if (!hasPrev.value) return
  offset.value = Math.max(0, offset.value - limit.value)
  fetchLogs()
}

onMounted(() => {
  fetchLogs(true)
})
</script>

<template>
  <div class="space-y-6 h-[calc(100vh-80px)] flex flex-col">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between border-b border-border pb-4 flex-shrink-0">
      <div>
        <h2 class="text-3xl font-bold text-text-primary uppercase tracking-widest flex items-center">
          <span class="text-secondary mr-2">>></span> {{ t('llmLogs.title') }}
        </h2>
        <p class="font-mono text-xs text-text-secondary mt-1 pl-8">
          {{ t('llmLogs.systemEventStream') }} // {{ t('llmLogs.recording') }}
        </p>
      </div>
      <button
        class="terminal-button text-xs"
        @click="fetchLogs(true)"
      >
        [{{ t('llmLogs.refreshStream') }}]
      </button>
    </div>

    <!-- Filter Panel (Fixed height or collapsible, but here let's keep it fixed and scroll the list) -->
    <div class="terminal-card flex-shrink-0">
      <div class="text-[10px] font-bold text-text-secondary uppercase mb-4 border-b border-border pb-2">{{ t('llmLogs.queryParameters') }}</div>
      <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.taskType') }}</label>
          <input v-model="filters.task_type" class="terminal-input text-xs" placeholder="e.g. summary.single" />
        </div>
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.contentType') }}</label>
          <input v-model="filters.content_type" class="terminal-input text-xs" placeholder="e.g. insight" />
        </div>
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.profileKey') }}</label>
          <input v-model="filters.profile_key" class="terminal-input text-xs" placeholder="e.g. v10" />
        </div>
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.status') }}</label>
          <input v-model="filters.status" class="terminal-input text-xs" placeholder="e.g. success" />
        </div>
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.model') }}</label>
          <input v-model="filters.model" class="terminal-input text-xs" placeholder="e.g. Qwen2.5" />
        </div>
        <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.limit') }}</label>
          <input v-model.number="limit" type="number" min="1" max="200" class="terminal-input text-xs" />
        </div>
         <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.startTime') }}</label>
          <input v-model="filters.start_time" type="datetime-local" class="terminal-input text-xs" />
        </div>
         <div>
          <label class="text-[10px] text-text-secondary uppercase block mb-1">{{ t('llmLogs.filters.endTime') }}</label>
          <input v-model="filters.end_time" type="datetime-local" class="terminal-input text-xs" />
        </div>
      </div>
      <div class="flex flex-wrap gap-2 mt-6">
        <button class="terminal-button text-xs py-1 px-3" @click="applyFilters">
          {{ t('llmLogs.applyFilters') }}
        </button>
        <button class="terminal-button-secondary text-xs py-1 px-3" @click="resetFilters">
          {{ t('llmLogs.resetFilters') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-10 font-mono text-primary animate-pulse">
      > {{ t('llmLogs.fetchingLogs') }}
    </div>
    <div v-else-if="error" class="text-secondary font-mono border border-secondary p-4 bg-secondary/10">
      {{ t('llmLogs.errorLabel') }}: {{ error }}
    </div>

    <div v-else class="flex-1 overflow-y-auto pr-2 scrollbar-terminal space-y-4">
      <div class="flex items-center justify-between text-xs font-mono text-text-secondary">
        <div>{{ t('llmLogs.totalRecords') }}: <span class="text-white">{{ total }}</span></div>
        <div class="flex items-center gap-2">
          <button class="hover:text-primary disabled:opacity-30" :disabled="!hasPrev" @click="prevPage">
            &lt; PREV
          </button>
          <span class="text-border">|</span>
          <button class="hover:text-primary disabled:opacity-30" :disabled="!hasNext" @click="nextPage">
            NEXT &gt;
          </button>
        </div>
      </div>

      <div v-if="logs.length === 0" class="text-text-secondary font-mono text-center py-10 border border-dashed border-border">
        {{ t('llmLogs.noDataFound') }}
      </div>

      <div v-for="log in logs" :key="log.id" class="terminal-card p-4 space-y-3 group hover:border-primary/50 transition-colors">
        <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between border-b border-border pb-2">
          <div>
            <div class="text-[10px] text-text-secondary font-mono">{{ formatDate(log.created_at) }}</div>
            <div class="text-base font-bold text-primary font-mono">{{ log.task_type }}</div>
          </div>
          <span
            class="px-2 py-0.5 text-[10px] font-bold uppercase border"
            :class="log.status === 'success' ? 'border-primary text-primary bg-primary/10' : 'border-secondary text-secondary bg-secondary/10'"
          >
            {{ log.status }}
          </span>
        </div>

        <div class="grid grid-cols-1 gap-2 md:grid-cols-3 text-xs font-mono text-text-secondary">
          <div><span class="text-text-secondary uppercase">{{ t('llmLogs.content') }}:</span> <span class="text-white">{{ log.content_type || '-' }}</span></div>
          <div><span class="text-text-secondary uppercase">{{ t('llmLogs.profile') }}:</span> <span class="text-white">{{ log.profile_key || '-' }}</span></div>
          <div><span class="text-text-secondary uppercase">{{ t('llmLogs.model') }}:</span> <span class="text-white">{{ log.model || '-' }}</span></div>
        </div>

        <div class="grid grid-cols-1 gap-2 md:grid-cols-3 text-xs font-mono text-text-secondary">
          <div>
            <span class="text-text-secondary uppercase">{{ t('llmLogs.tokens') }}:</span>
            <span class="text-tertiary">{{ log.prompt_tokens ?? '-' }}</span> / <span class="text-tertiary">{{ log.completion_tokens ?? '-' }}</span>
          </div>
          <div>
            <span class="text-text-secondary uppercase">{{ t('llmLogs.truncated') }}:</span>
            <span :class="log.request_meta?.input_truncated ? 'text-secondary' : 'text-white'">{{ getTruncationLabel(log.request_meta) }}</span>
          </div>
          <div v-if="log.error_message">
            <span class="text-secondary uppercase">{{ t('llmLogs.errorLabel') }}:</span>
            <span class="text-secondary">{{ log.error_message }}</span>
          </div>
        </div>

        <div class="space-y-2 mt-4 pt-4 border-t border-border/50">
           <details class="group/details">
            <summary class="cursor-pointer text-xs font-bold text-text-secondary uppercase hover:text-primary select-none flex items-center">
              <span class="mr-2 transform group-open/details:rotate-90 transition-transform">▶</span>
              {{ t('llmLogs.fields.prompts') }}
            </summary>
            <div class="mt-3 space-y-3 pl-4 border-l border-border ml-1">
              <div>
                <div class="text-[10px] text-text-secondary uppercase mb-1">System</div>
                <pre class="whitespace-pre-wrap text-xs text-text-primary bg-black/30 border border-border p-3 overflow-x-auto">{{ log.system_prompt || '-' }}</pre>
              </div>
              <div>
                <div class="text-[10px] text-text-secondary uppercase mb-1">User</div>
                <pre class="whitespace-pre-wrap text-xs text-text-primary bg-black/30 border border-border p-3 overflow-x-auto">{{ log.user_prompt || '-' }}</pre>
              </div>
            </div>
          </details>

          <details class="group/details">
            <summary class="cursor-pointer text-xs font-bold text-text-secondary uppercase hover:text-primary select-none flex items-center">
              <span class="mr-2 transform group-open/details:rotate-90 transition-transform">▶</span>
              {{ t('llmLogs.fields.response') }}
            </summary>
            <pre class="mt-2 whitespace-pre-wrap text-xs text-primary bg-black/30 border border-border p-3 pl-4 ml-1 overflow-x-auto">{{ log.response_text || '-' }}</pre>
          </details>

          <details class="group/details">
            <summary class="cursor-pointer text-xs font-bold text-text-secondary uppercase hover:text-primary select-none flex items-center">
               <span class="mr-2 transform group-open/details:rotate-90 transition-transform">▶</span>
               {{ t('llmLogs.fields.meta') }}
            </summary>
            <div class="mt-2 pl-4 ml-1 border-l border-border space-y-2">
              <pre class="whitespace-pre-wrap text-[10px] text-text-secondary bg-black/30 border border-border p-3 overflow-x-auto">{{ formatJson(log.request_meta) || '-' }}</pre>
              <pre class="whitespace-pre-wrap text-[10px] text-text-secondary bg-black/30 border border-border p-3 overflow-x-auto">{{ formatJson(log.response_meta) || '-' }}</pre>
            </div>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>
