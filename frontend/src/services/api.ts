// API service for frontend
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' ? '' : 'http://localhost:8000')

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user_id: number
  username: string
}

export interface ProcessVideoRequest {
  url: string
  language?: string
}

export interface VideoStatus {
  id: number
  url: string
  title?: string
  status: string
  progress: number
  queue_position?: number
  error_message?: string
}

export interface HistoryItem {
  id: number
  url: string
  title?: string
  summary?: string
  language?: string
  status: string
  keywords?: string  // Comma-separated keywords
  created_at: string
}

export interface HistoryDetail extends HistoryItem {
  transcript?: string
  keywords?: string  // Comma-separated keywords
  progress: number
  completed_at?: string
  error_message?: string
}

export interface UpdateHistoryRequest {
  transcript?: string
  keywords?: string
}

export interface QueueStatus {
  queue_size: number
  processing: number
  processing_tasks: Array<{
    id: number
    status: string
  }>
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export interface ChangeUsernameRequest {
  new_username: string
}

export interface ChangeUsernameResponse {
  message: string
  old_username: string
  new_username: string
}

export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/api/auth/login', { username, password })
    return response.data
  },
  
  register: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/api/auth/register', { username, password })
    return response.data
  },
  
  changePassword: async (oldPassword: string, newPassword: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/api/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword
    })
    return response.data
  },
  
  changeUsername: async (newUsername: string): Promise<ChangeUsernameResponse> => {
    const response = await api.post<ChangeUsernameResponse>('/api/auth/change-username', {
      new_username: newUsername
    })
    return response.data
  },
}

export const videoApi = {
  process: async (url: string, language?: string): Promise<VideoStatus> => {
    const response = await api.post<VideoStatus>('/api/video/process', { url, language })
    return response.data
  },
  
  getStatus: async (id: number): Promise<VideoStatus> => {
    const response = await api.get<VideoStatus>(`/api/video/status/${id}`)
    return response.data
  },
  
  getQueue: async (): Promise<QueueStatus> => {
    const response = await api.get<QueueStatus>('/api/video/queue')
    return response.data
  },
  
  retry: async (id: number): Promise<VideoStatus> => {
    const response = await api.post<VideoStatus>(`/api/video/retry/${id}`)
    return response.data
  },
  
  getStreamUrl: (recordId: number): string => {
    // Use relative URL since nginx proxies /api to backend
    // No authentication required for local access
    return `/api/video/${recordId}/stream`
  },
}

export const historyApi = {
  getHistory: async (skip = 0, limit = 100): Promise<HistoryItem[]> => {
    const response = await api.get<HistoryItem[]>('/api/history', {
      params: { skip, limit },
    })
    return response.data
  },
  
  getHistoryCount: async (): Promise<number> => {
    const response = await api.get<{ count: number }>('/api/history/count')
    return response.data.count
  },
  
  getDetail: async (id: number): Promise<HistoryDetail> => {
    const response = await api.get<HistoryDetail>(`/api/history/${id}`)
    return response.data
  },
  
  updateHistory: async (id: number, data: UpdateHistoryRequest): Promise<HistoryDetail> => {
    const response = await api.put<HistoryDetail>(`/api/history/${id}`, data)
    return response.data
  },
  
  searchHistory: async (query: string, skip = 0, limit = 100): Promise<HistoryItem[]> => {
    const response = await api.get<HistoryItem[]>('/api/history/search', {
      params: { q: query, skip, limit },
    })
    return response.data
  },
  
  searchHistoryCount: async (query: string): Promise<number> => {
    const response = await api.get<{ count: number }>('/api/history/search/count', {
      params: { q: query },
    })
    return response.data.count
  },
  
  exportMarkdown: async (id: number, includeTimestamps = false): Promise<Blob> => {
    const response = await api.get(`/api/history/${id}/export`, {
      params: { include_timestamps: includeTimestamps },
      responseType: 'blob',
    })
    return response.data
  },
  
  generateKeywords: async (id: number): Promise<HistoryDetail> => {
    const response = await api.post<HistoryDetail>(`/api/history/${id}/generate-keywords`)
    return response.data
  },
  
  deleteHistory: async (id: number): Promise<void> => {
    await api.delete(`/api/history/${id}`)
  },
}

export interface PlaylistResponse {
  id: number
  name: string
  user_id: number
  created_at: string
  updated_at?: string
}

export interface PlaylistItemResponse {
  id: number
  playlist_id: number
  video_record_id: number
  position: number
  created_at: string
  title?: string
  url: string
  status: string
  progress: number
}

export interface AddPlaylistItemRequest {
  video_record_id: number
}

export interface UpdatePlaylistItemRequest {
  position: number
}

export const playlistApi = {
  getPlaylist: async (): Promise<PlaylistResponse> => {
    const response = await api.get<PlaylistResponse>('/api/playlist')
    return response.data
  },
  
  getPlaylistItems: async (): Promise<PlaylistItemResponse[]> => {
    const response = await api.get<PlaylistItemResponse[]>('/api/playlist/items')
    return response.data
  },
  
  addItem: async (videoRecordId: number): Promise<PlaylistItemResponse> => {
    const response = await api.post<PlaylistItemResponse>('/api/playlist/items', {
      video_record_id: videoRecordId
    })
    return response.data
  },
  
  updateItem: async (itemId: number, position: number): Promise<PlaylistItemResponse> => {
    const response = await api.put<PlaylistItemResponse>(`/api/playlist/items/${itemId}`, {
      position
    })
    return response.data
  },
  
  removeItem: async (itemId: number): Promise<void> => {
    await api.delete(`/api/playlist/items/${itemId}`)
  },
  
  clearPlaylist: async (): Promise<void> => {
    await api.delete('/api/playlist/items')
  },
}

export default api
