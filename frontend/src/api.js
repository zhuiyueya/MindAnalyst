import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1', // Vite proxy handles this to localhost:8000
  headers: {
    'Content-Type': 'application/json',
  },
});

export default {
  // Authors
  getAuthors() {
    return apiClient.get('/authors');
  },
  getAuthor(id) {
    return apiClient.get(`/authors/${id}`);
  },
  getAuthorVideos(id) {
    return apiClient.get(`/authors/${id}/videos`);
  },
  regenerateReport(id) {
    return apiClient.post(`/authors/${id}/regenerate_report`);
  },
  setAuthorType(id, data) {
    return apiClient.post(`/authors/${id}/set_type`, data);
  },
  resummarizeAll(id, includeFallback = false) {
    return apiClient.post(`/authors/${id}/resummarize_all`, null, {
      params: { include_fallback: includeFallback }
    });
  },
  resummarizePending(id) {
    return apiClient.post(`/authors/${id}/resummarize_pending`);
  },
  reprocessAuthorAsr(id) {
    return apiClient.post(`/authors/${id}/reprocess_asr`);
  },

  // Videos
  getVideo(id) {
    return apiClient.get(`/videos/${id}`);
  },
  getVideoPlayback(id) {
    return apiClient.get(`/videos/${id}/playback`);
  },
  resummarizeVideo(id, includeFallback = false) {
    return apiClient.post(`/videos/${id}/resummarize`, null, {
      params: { include_fallback: includeFallback }
    });
  },
  reprocessVideoAsr(id) {
    return apiClient.post(`/videos/${id}/reprocess_asr`);
  },
  setVideoType(id, data) {
    return apiClient.post(`/videos/${id}/set_type`, data);
  },

  // Ingest & Chat
  ingest(data) {
    return apiClient.post('/ingest', data);
  },
  chat(data) {
    return apiClient.post('/chat', data);
  },

  // LLM Logs
  listLlmCalls(params = {}) {
    return apiClient.get('/llm_calls', { params });
  }
};
