import axios from 'axios';

// Pulls from your .env file
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: Attach the JWT token to every outgoing request
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('meta_s_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Handle expired tokens globally
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // If backend returns 401 Unauthorized, trigger the event App.jsx is listening for
    if (error.response && error.response.status === 401) {
      window.dispatchEvent(new Event('auth-expired'));
    }
    return Promise.reject(error);
  }
);

// Centralized API definitions
export const api = {
  // Auth
  // Note: If using standard FastAPI OAuth2, login might need to be sent as FormData instead of JSON. 
  // Assuming JSON here based on typical MERN/Modern stacks.
  login: (email, password) => apiClient.post('/auth/login', { email, password }),
  register: (email, password) => apiClient.post('/auth/register', { email, password }),
  
  // Inbox
  getFetchedEmails: (params) => apiClient.get('/inbox', { params }),
  fetchEmails: (limit) => apiClient.post('/inbox/sync', { limit }),
  
  // Swarm / AI
  triageEmail: (data) => apiClient.post('/swarm/triage', data),
  
  // Analytics
  getMetrics: () => apiClient.get('/analytics/metrics'),
};