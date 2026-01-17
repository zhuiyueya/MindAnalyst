<script setup>
import { ref } from 'vue'
import IngestPanel from './components/IngestPanel.vue'
import ChatPanel from './components/ChatPanel.vue'

const activeTab = ref('chat')
</script>

<template>
  <div class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Header -->
    <header class="bg-white shadow">
      <div class="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
        <h1 class="text-3xl font-bold text-gray-900">Mind Analyst</h1>
        <div class="space-x-4">
          <button 
            @click="activeTab = 'ingest'"
            :class="activeTab === 'ingest' ? 'bg-indigo-600 text-white' : 'text-gray-700 hover:bg-gray-200'"
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            Data Ingestion
          </button>
          <button 
            @click="activeTab = 'chat'"
            :class="activeTab === 'chat' ? 'bg-indigo-600 text-white' : 'text-gray-700 hover:bg-gray-200'"
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            Chat
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 max-w-7xl w-full mx-auto py-6 sm:px-6 lg:px-8">
      <div class="bg-white overflow-hidden shadow-xl sm:rounded-lg h-[calc(100vh-10rem)] flex flex-col">
        <IngestPanel v-if="activeTab === 'ingest'" />
        <ChatPanel v-else />
      </div>
    </main>
  </div>
</template>
