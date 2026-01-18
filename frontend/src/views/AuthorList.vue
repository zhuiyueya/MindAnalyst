<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const authors = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await api.getAuthors()
    authors.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex justify-between items-center">
      <h2 class="text-2xl font-bold text-gray-900">Authors</h2>
    </div>

    <div v-if="loading" class="text-center py-10 text-gray-500">Loading...</div>
    
    <div v-else class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <div 
        v-for="author in authors" 
        :key="author.id" 
        class="bg-white overflow-hidden shadow rounded-lg hover:shadow-md transition-shadow cursor-pointer border border-transparent hover:border-indigo-500"
        @click="$router.push(`/authors/${author.id}`)"
      >
        <div class="px-4 py-5 sm:p-6 flex items-center space-x-4">
          <img 
            v-if="author.avatar_url" 
            :src="author.avatar_url" 
            alt="" 
            class="h-16 w-16 rounded-full bg-gray-100"
          >
          <div v-else class="h-16 w-16 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xl font-bold">
            {{ author.name.charAt(0) }}
          </div>
          
          <div class="flex-1 min-w-0">
            <h3 class="text-lg font-medium text-gray-900 truncate">
              {{ author.name }}
            </h3>
            <p class="text-sm text-gray-500 truncate">
              Platform: {{ author.platform }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
