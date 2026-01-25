import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AuthorList from '../views/AuthorList.vue'
import AuthorDetail from '../views/AuthorDetail.vue'
import VideoDetail from '../views/VideoDetail.vue'
import IngestPanel from '../components/IngestPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import LlmCalls from '../views/LlmCalls.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/ingest', component: IngestPanel },
  { path: '/chat', component: ChatPanel },
  { path: '/authors', component: AuthorList },
  { path: '/authors/:id', component: AuthorDetail },
  { path: '/videos/:id', component: VideoDetail },
  { path: '/llm-calls', component: LlmCalls },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
