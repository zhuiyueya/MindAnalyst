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
  <div class="space-y-6">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">{{ t('llmLogs.title') }}</h2>
        <p class="text-sm text-gray-500">{{ t('llmLogs.subtitle') }}</p>
      </div>
      <button
        class="px-3 py-2 rounded-md text-sm font-medium bg-gray-900 text-white hover:bg-gray-800"
        @click="fetchLogs(true)"
      >
        {{ t('llmLogs.refresh') }}
      </button>
    </div>

    <div class="bg-white shadow rounded-lg p-4 space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.taskType') }}</label>
          <input v-model="filters.task_type" class="mt-1 w-full rounded border-gray-300 text-sm" placeholder="summary.single" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.contentType') }}</label>
          <input v-model="filters.content_type" class="mt-1 w-full rounded border-gray-300 text-sm" placeholder="insight" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.profileKey') }}</label>
          <input v-model="filters.profile_key" class="mt-1 w-full rounded border-gray-300 text-sm" placeholder="types/insight/author_report/v10" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.status') }}</label>
          <input v-model="filters.status" class="mt-1 w-full rounded border-gray-300 text-sm" placeholder="success" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.model') }}</label>
          <input v-model="filters.model" class="mt-1 w-full rounded border-gray-300 text-sm" placeholder="Qwen/Qwen2.5-7B-Instruct" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.limit') }}</label>
          <input v-model.number="limit" type="number" min="1" max="200" class="mt-1 w-full rounded border-gray-300 text-sm" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.startTime') }}</label>
          <input v-model="filters.start_time" type="datetime-local" class="mt-1 w-full rounded border-gray-300 text-sm" />
        </div>
        <div>
          <label class="text-xs text-gray-500">{{ t('llmLogs.filters.endTime') }}</label>
          <input v-model="filters.end_time" type="datetime-local" class="mt-1 w-full rounded border-gray-300 text-sm" />
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="px-3 py-2 rounded text-sm bg-indigo-600 text-white" @click="applyFilters">
          {{ t('llmLogs.applyFilters') }}
        </button>
        <button class="px-3 py-2 rounded text-sm border" @click="resetFilters">
          {{ t('llmLogs.resetFilters') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-10 text-gray-500">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="text-red-600">{{ error }}</div>

    <div v-else class="space-y-4">
      <div class="flex items-center justify-between text-sm text-gray-500">
        <div>{{ t('llmLogs.total', { total }) }}</div>
        <div class="flex items-center gap-2">
          <button class="px-2 py-1 border rounded" :disabled="!hasPrev" @click="prevPage">
            {{ t('llmLogs.prev') }}
          </button>
          <button class="px-2 py-1 border rounded" :disabled="!hasNext" @click="nextPage">
            {{ t('llmLogs.next') }}
          </button>
        </div>
      </div>

      <div v-if="logs.length === 0" class="text-gray-500">{{ t('llmLogs.empty') }}</div>

      <div v-for="log in logs" :key="log.id" class="bg-white shadow rounded-lg p-4 space-y-3">
        <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <div class="text-xs text-gray-500">{{ formatDate(log.created_at) }}</div>
            <div class="text-lg font-semibold text-gray-900">{{ log.task_type }}</div>
          </div>
          <span
            class="px-2 py-1 rounded text-xs font-medium"
            :class="log.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
          >
            {{ log.status }}
          </span>
        </div>

        <div class="grid grid-cols-1 gap-2 md:grid-cols-3 text-sm text-gray-600">
          <div><span class="text-gray-400">{{ t('llmLogs.fields.contentType') }}:</span> {{ log.content_type || '-' }}</div>
          <div><span class="text-gray-400">{{ t('llmLogs.fields.profileKey') }}:</span> {{ log.profile_key || '-' }}</div>
          <div><span class="text-gray-400">{{ t('llmLogs.fields.model') }}:</span> {{ log.model || '-' }}</div>
        </div>

        <div class="grid grid-cols-1 gap-2 md:grid-cols-3 text-sm">
          <div>
            <span class="text-gray-400">{{ t('llmLogs.fields.tokens') }}:</span>
            {{ log.prompt_tokens ?? '-' }} / {{ log.completion_tokens ?? '-' }} / {{ log.total_tokens ?? '-' }}
          </div>
          <div>
            <span class="text-gray-400">{{ t('llmLogs.fields.truncated') }}:</span>
            {{ getTruncationLabel(log.request_meta) }}
          </div>
          <div>
            <span class="text-gray-400">{{ t('llmLogs.fields.error') }}:</span>
            {{ log.error_message || '-' }}
          </div>
        </div>

        <details class="bg-gray-50 rounded p-3">
          <summary class="cursor-pointer text-sm font-medium text-gray-700">{{ t('llmLogs.fields.prompts') }}</summary>
          <div class="mt-3 space-y-3">
            <div>
              <div class="text-xs text-gray-500 mb-1">System</div>
              <pre class="whitespace-pre-wrap text-sm text-gray-700 bg-white border rounded p-3">{{ log.system_prompt || '-' }}</pre>
            </div>
            <div>
              <div class="text-xs text-gray-500 mb-1">User</div>
              <pre class="whitespace-pre-wrap text-sm text-gray-700 bg-white border rounded p-3">{{ log.user_prompt || '-' }}</pre>
            </div>
          </div>
        </details>

        <details class="bg-gray-50 rounded p-3">
          <summary class="cursor-pointer text-sm font-medium text-gray-700">{{ t('llmLogs.fields.response') }}</summary>
          <pre class="mt-2 whitespace-pre-wrap text-sm text-gray-700 bg-white border rounded p-3">{{ log.response_text || '-' }}</pre>
        </details>

        <details class="bg-gray-50 rounded p-3">
          <summary class="cursor-pointer text-sm font-medium text-gray-700">{{ t('llmLogs.fields.meta') }}</summary>
          <pre class="mt-2 whitespace-pre-wrap text-sm text-gray-700 bg-white border rounded p-3">{{ formatJson(log.request_meta) || '-' }}</pre>
          <pre class="mt-2 whitespace-pre-wrap text-sm text-gray-700 bg-white border rounded p-3">{{ formatJson(log.response_meta) || '-' }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>
