<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const { t } = useI18n()
const md = new MarkdownIt()

const messages = ref([
  { role: 'assistant', content: t('chat.welcome') }
])
const query = ref('')
const isLoading = ref(false)
const messagesEndRef = ref(null)
const authors = ref([])
const selectedAuthorId = ref(null)
const tagFilter = ref('')
const isReindexing = ref(false)

const fetchAuthors = async () => {
  try {
    const res = await axios.get('/api/v1/authors')
    authors.value = res.data
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

  const rawQuery = query.value
  const tags = (tagFilter.value || '').trim()
  const userQuery = tags ? `tag:${tags} ${rawQuery}` : rawQuery
  messages.value.push({ role: 'user', content: userQuery, timestamp: new Date().toLocaleTimeString() })
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
      citations: res.data.citations,
      timestamp: new Date().toLocaleTimeString()
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `${t('chat.errorPrefix')}${e.response?.data?.detail || e.message}`,
      timestamp: new Date().toLocaleTimeString()
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

const triggerReindexAuthor = async () => {
  if (isReindexing.value) return
  if (!confirm(t('rag.confirmReindexAuthor'))) return
  isReindexing.value = true
  try {
    await axios.post('/api/v1/rag/reindex', { author_id: selectedAuthorId.value })
    alert(t('common.batchTaskStarted'))
  } catch (e) {
    alert(t('common.failedPrefix') + (e.response?.data?.detail || e.message))
  } finally {
    isReindexing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-120px)] border border-border bg-surface/30">
    <!-- Terminal Toolbar -->
    <div class="px-6 py-3 border-b border-border bg-surface flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
          <span class="text-[10px] font-bold text-text-secondary uppercase">{{ t('chat.scope') }}:</span>
          <select 
            v-model="selectedAuthorId" 
            class="bg-background border border-border text-primary text-xs font-mono py-1 px-2 focus:outline-none focus:border-primary"
          >
            <option :value="null">{{ t('chat.allAuthors').toUpperCase() }}</option>
            <option v-for="author in authors" :key="author.id" :value="author.id">
              {{ author.name.toUpperCase() }}
            </option>
          </select>
        </div>
        <div class="flex items-center space-x-2">
           <span class="text-[10px] font-bold text-text-secondary uppercase">{{ t('chat.filter') }}:</span>
           <input
            v-model="tagFilter"
            type="text"
            :placeholder="t('chat.tagPlaceholder')"
            class="bg-background border border-border text-primary text-xs font-mono py-1 px-2 focus:outline-none focus:border-primary w-40"
          />
        </div>
      </div>
      
      <div class="flex items-center space-x-4">
        <button
          @click="triggerReindexAuthor"
          :disabled="isReindexing || !selectedAuthorId"
          class="text-[10px] font-bold text-text-secondary hover:text-primary disabled:opacity-30 uppercase tracking-tighter"
        >
          [{{ t('chat.reindexScope') }}]
        </button>
        <div class="h-4 w-px bg-border"></div>
        <button @click="fetchAuthors" class="text-[10px] font-bold text-tertiary hover:text-white uppercase tracking-tighter">
          [{{ t('chat.refreshAuthors') }}]
        </button>
      </div>
    </div>

    <!-- Terminal Output Area -->
    <div class="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-terminal">
      <div 
        v-for="(msg, idx) in messages" 
        :key="idx"
        class="flex flex-col"
      >
        <!-- Role & Timestamp -->
        <div class="flex items-center space-x-2 mb-2">
           <span :class="[msg.role === 'user' ? 'text-secondary' : 'text-primary', 'text-[10px] font-bold uppercase']">
             {{ msg.role === 'user' ? `>> ${t('chat.userInput')}` : `>> ${t('chat.analystCore')}` }}
           </span>
           <span class="text-[10px] text-text-secondary font-mono">[{{ msg.timestamp || t('chat.init') }}]</span>
        </div>

        <!-- Content -->
        <div 
          :class="[
            'p-4 border font-mono text-sm leading-relaxed',
            msg.role === 'user' ? 'border-secondary/30 bg-secondary/5 text-text-primary' : 'border-primary/30 bg-primary/5 text-text-primary'
          ]"
        >
          <div v-if="msg.role === 'assistant'" class="prose prose-invert max-w-none text-sm" v-html="md.render(msg.content)"></div>
          <div v-else class="whitespace-pre-wrap">{{ msg.content }}</div>
          
          <!-- Citations / Sources -->
          <div v-if="msg.citations && msg.citations.length" class="mt-6 pt-4 border-t border-border">
            <div class="text-[10px] font-bold text-tertiary uppercase mb-3">{{ t('chat.sourcedDocuments') }}:</div>
            <div class="space-y-3">
              <div v-for="(cit, cIdx) in msg.citations" :key="cIdx" class="text-xs group">
                <div class="flex items-start gap-3">
                  <span class="text-tertiary font-bold">[{{ cit.index }}]</span>
                  <div class="flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <a v-if="cit.url" :href="cit.url" target="_blank" class="text-text-primary font-bold hover:text-tertiary transition-colors">
                        {{ cit.title || t('chat.untitledRef') }}
                      </a>
                      <span v-else class="text-text-primary font-bold">{{ cit.title || t('chat.untitledRef') }}</span>
                      <span v-if="cit.tag" class="text-[9px] px-1 border border-border text-text-secondary uppercase">{{ cit.tag }}</span>
                    </div>
                    <div class="mt-1 text-text-secondary line-clamp-2 italic group-hover:line-clamp-none transition-all">
                      "{{ cit.text }}"
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Typing Indicator -->
      <div v-if="isLoading" class="flex flex-col">
         <div class="text-[10px] font-bold text-primary uppercase mb-2">>> {{ t('chat.analystCore') }}</div>
         <div class="p-4 border border-primary/30 bg-primary/5">
            <div class="flex space-x-1">
              <div class="w-1.5 h-3 bg-primary animate-pulse"></div>
              <span class="text-xs text-primary font-mono animate-pulse">{{ t('chat.processingQuery') }}</span>
            </div>
         </div>
      </div>
      
      <div ref="messagesEndRef"></div>
    </div>

    <!-- Terminal Input Area -->
    <div class="p-6 bg-surface border-t border-border">
      <div class="flex items-center gap-4">
        <span class="text-primary font-bold animate-pulse">></span>
        <input 
          v-model="query"
          @keyup.enter="handleChat"
          type="text"
          :placeholder="t('chat.askPlaceholder').toUpperCase()"
          class="flex-1 bg-transparent border-none text-primary font-mono text-sm focus:ring-0 placeholder-gray-700"
          :disabled="isLoading"
        />
        <button 
          @click="handleChat"
          :disabled="isLoading || !query.trim()"
          class="terminal-button py-1 px-4 text-xs"
        >
          {{ t('chat.execute') }}
        </button>
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
