<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

const messages = ref([
  { role: 'assistant', content: t('chat.welcome') }
])
const query = ref('')
const isLoading = ref(false)
const messagesEndRef = ref(null)
const authors = ref([])
const selectedAuthorId = ref(null)

const fetchAuthors = async () => {
  try {
    const res = await axios.get('/api/v1/authors')
    authors.value = res.data
    if (authors.value.length > 0) {
      // Default select the first one if not set
      // selectedAuthorId.value = authors.value[0].id
    }
  } catch (e) {
    console.error('Failed to fetch authors', e)
  }
}

onMounted(() => {
  fetchAuthors()
})

const scrollToBottom = () => {
  nextTick(() => {
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

const handleChat = async () => {
  if (!query.value.trim() || isLoading.value) return

  const userQuery = query.value
  messages.value.push({ role: 'user', content: userQuery })
  query.value = ''
  isLoading.value = true
  scrollToBottom()

  try {
    const res = await axios.post('/api/v1/chat', {
      query: userQuery,
      author_id: selectedAuthorId.value
    })
    
    messages.value.push({ 
      role: 'assistant', 
      content: res.data.answer,
      citations: res.data.citations 
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `${t('chat.errorPrefix')}${e.response?.data?.detail || e.message}`
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Toolbar -->
    <div class="px-6 py-3 border-b bg-gray-50 flex items-center justify-between">
      <div class="flex items-center space-x-2">
        <label class="text-sm font-medium text-gray-700">{{ t('chat.toolbarLabel') }}</label>
        <select 
          v-model="selectedAuthorId" 
          class="block w-48 pl-3 pr-10 py-1.5 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
        >
          <option :value="null">{{ t('chat.allAuthors') }}</option>
          <option v-for="author in authors" :key="author.id" :value="author.id">
            {{ author.name }} ({{ author.platform }})
          </option>
        </select>
      </div>
      <button @click="fetchAuthors" class="text-xs text-indigo-600 hover:text-indigo-800">
        {{ t('chat.refreshAuthors') }}
      </button>
    </div>

    <!-- Chat History -->
    <div class="flex-1 overflow-y-auto p-6 space-y-4">
      <div 
        v-for="(msg, idx) in messages" 
        :key="idx"
        :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
      >
        <div 
          :class="[
            'max-w-[80%] rounded-lg p-4 shadow',
            msg.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-900'
          ]"
        >
          <div class="whitespace-pre-wrap">{{ msg.content }}</div>
          
          <!-- Citations -->
          <div v-if="msg.citations && msg.citations.length" class="mt-4 pt-4 border-t border-gray-300 text-xs">
            <p class="font-semibold mb-2">{{ t('chat.sources') }}</p>
            <ul class="space-y-1">
              <li v-for="(cit, cIdx) in msg.citations" :key="cIdx" class="text-gray-600">
                <a :href="cit.url" target="_blank" class="hover:underline hover:text-indigo-600 flex items-start">
                  <span class="mr-1">[{{ cit.index }}]</span>
                  <span>{{ cit.text.substring(0, 50) }}... ({{ Math.floor(cit.start_time / 60) }}:{{ String(Math.floor(cit.start_time % 60)).padStart(2, '0') }})</span>
                </a>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div v-if="isLoading" class="flex justify-start">
        <div class="bg-gray-100 rounded-lg p-4 shadow">
          <div class="flex space-x-2">
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-75"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-150"></div>
          </div>
        </div>
      </div>
      <div ref="messagesEndRef"></div>
    </div>

    <!-- Input Area -->
    <div class="p-4 bg-gray-50 border-t">
      <div class="flex space-x-4">
        <input 
          v-model="query"
          @keyup.enter="handleChat"
          type="text"
          :placeholder="t('chat.askPlaceholder')"
          class="flex-1 p-3 border rounded-md focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          :disabled="isLoading"
        />
        <button 
          @click="handleChat"
          :disabled="isLoading || !query.trim()"
          class="bg-indigo-600 text-white px-6 py-3 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          {{ t('chat.send') }}
        </button>
      </div>
    </div>
  </div>
</template>
