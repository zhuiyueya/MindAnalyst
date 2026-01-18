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
  resummarizeAll(id) {
    return apiClient.post(`/authors/${id}/resummarize_all`);
  },

  // Videos
  getVideo(id) {
    return apiClient.get(`/videos/${id}`);
  },
  getVideoPlayback(id) {
    return apiClient.get(`/videos/${id}/playback`);
  },
  resummarizeVideo(id) {
    return apiClient.post(`/videos/${id}/resummarize`);
  },

  // Ingest & Chat
  ingest(data) {
    return apiClient.post('/ingest', data);
  },
  chat(data) {
    return apiClient.post('/chat', data);
  }
};
