<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const md = new MarkdownIt()

const author = ref(null)
const report = ref(null)
const videos = ref([])
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
    videos.value = vidRes.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

const renderReport = computed(() => {
  if (!report.value || !report.value.content) return 'No report generated yet.'
  return md.render(report.value.content)
})

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

const triggerResummarizeAll = async () => {
  if (!confirm('Re-summarize ALL videos? This is a heavy operation.')) return
  processing.value = true
  try {
    await api.resummarizeAll(authorId)
    alert('Batch task started.')
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
          <div class="mt-4 flex space-x-3">
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
    <div v-if="activeTab === 'report'" class="bg-white shadow rounded-lg p-6 prose max-w-none">
      <div v-html="renderReport"></div>
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
                Status: <span :class="video.has_summary ? 'text-green-600' : 'text-yellow-600'">{{ video.has_summary ? 'Summarized' : 'Pending' }}</span>
              </p>
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
