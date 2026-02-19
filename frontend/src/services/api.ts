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

// Handle 401 errors - automatically logout and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Session expired or unauthorized - clear token and redirect to login
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('user_id')
      
      // Only redirect if we're not already on the login page
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

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

export interface AuthConfigResponse {
  allow_registration: boolean
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
  watch_position_seconds?: number
}

export interface HistoryItem {
  id: number
  url: string
  title?: string
  summary?: string
  language?: string
  status: string
  keywords?: string  // Comma-separated keywords
  upload_date?: string  // Video upload date from YouTube
  thumbnail_path?: string  // Path to thumbnail image
  thumbnail_url?: string
  source_video_id?: string
  channel_id?: string
  channel_title?: string
  uploader_id?: string
  uploader?: string
  view_count?: number
  like_count?: number
  duration_seconds?: number
  downloaded_at?: string
  read_count?: number
  created_at: string
  subscription_id?: number  // Set when video was added via channel subscription
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

export interface TaskItem {
  id: number
  url: string
  title?: string
  status: string
  progress: number
  error_message?: string
  created_at?: string
  updated_at?: string
  downloaded_at?: string
  completed_at?: string
}

export interface TaskListResponse {
  total: number
  skip: number
  limit: number
  items: TaskItem[]
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

export interface UserProfileResponse {
  user_id: number
  username: string
  summary_language: string
}

export const authApi = {
  getProfile: async (): Promise<UserProfileResponse> => {
    const response = await api.get<UserProfileResponse>('/api/auth/profile')
    return response.data
  },

  updateSummaryLanguage: async (summaryLanguage: string): Promise<{ summary_language: string }> => {
    const response = await api.patch<{ summary_language: string }>('/api/auth/settings/summary-language', {
      summary_language: summaryLanguage,
    })
    return response.data
  },

  login: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/api/auth/login', { username, password })
    return response.data
  },

  getConfig: async (): Promise<AuthConfigResponse> => {
    const response = await api.get<AuthConfigResponse>('/api/auth/config')
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
  
  getStatus: async (id: number, opts?: { countRead?: boolean }): Promise<VideoStatus> => {
    const response = await api.get<VideoStatus>(`/api/video/status/${id}`, {
      params: opts?.countRead ? { count_read: true } : undefined,
    })
    return response.data
  },

  saveWatchPosition: async (recordId: number, positionSeconds: number): Promise<void> => {
    await api.put(`/api/video/status/${recordId}/watch-position`, {
      position_seconds: positionSeconds,
    })
  },
  
  getQueue: async (): Promise<QueueStatus> => {
    const response = await api.get<QueueStatus>('/api/video/queue')
    return response.data
  },
  
  retry: async (id: number): Promise<VideoStatus> => {
    const response = await api.post<VideoStatus>(`/api/video/retry/${id}`)
    return response.data
  },

  getTasks: async (statuses: string[], skip = 0, limit = 50): Promise<TaskListResponse> => {
    const response = await api.get<TaskListResponse>('/api/video/tasks', {
      params: { statuses, skip, limit },
      paramsSerializer: (params) => {
        // Ensure arrays are sent as repeated query params: statuses=pending&statuses=converting
        const usp = new URLSearchParams()
        ;(params.statuses || []).forEach((s: string) => usp.append('statuses', s))
        usp.set('skip', String(params.skip ?? 0))
        usp.set('limit', String(params.limit ?? 50))
        return usp.toString()
      },
    })
    return response.data
  },

  bulkRetry: async (recordIds: number[]): Promise<{ updated_count: number; record_ids: number[] }> => {
    const response = await api.post<{ updated_count: number; record_ids: number[] }>('/api/video/bulk/retry', {
      record_ids: recordIds,
    })
    return response.data
  },

  bulkRestartTranscribe: async (recordIds: number[]): Promise<{ updated_count: number; record_ids: number[] }> => {
    const response = await api.post<{ updated_count: number; record_ids: number[] }>(
      '/api/video/bulk/restart-transcribe',
      { record_ids: recordIds }
    )
    return response.data
  },

  bulkRestartSummary: async (recordIds: number[]): Promise<{ updated_count: number; record_ids: number[] }> => {
    const response = await api.post<{ updated_count: number; record_ids: number[] }>(
      '/api/video/bulk/restart-summary',
      { record_ids: recordIds }
    )
    return response.data
  },
  
  getStreamUrl: (recordId: number): string => {
    // Use relative URL since nginx proxies /api to backend
    // No authentication required for local access
    return `/api/video/${recordId}/stream`
  },
  
  getThumbnailUrl: (recordId: number): string => {
    // Use relative URL since nginx proxies /api to backend
    return `/api/video/${recordId}/thumbnail`
  },
}

export const historyApi = {
  getHistory: async (skip = 0, limit = 100, hasSummary?: boolean, source?: 'subscription'): Promise<HistoryItem[]> => {
    const params: Record<string, any> = { skip, limit }
    if (typeof hasSummary === 'boolean') {
      params.has_summary = hasSummary
    }
    if (source === 'subscription') {
      params.source = 'subscription'
    }

    const response = await api.get<HistoryItem[]>('/api/history', {
      params,
    })
    return response.data
  },
  
  getHistoryCount: async (hasSummary?: boolean, source?: 'subscription'): Promise<number> => {
    const params: Record<string, any> = {}
    if (typeof hasSummary === 'boolean') {
      params.has_summary = hasSummary
    }
    if (source === 'subscription') {
      params.source = 'subscription'
    }
    const response = await api.get<{ count: number }>('/api/history/count', {
      params: Object.keys(params).length ? params : undefined,
    })
    return response.data.count
  },
  
  getDetail: async (id: number, opts?: { countRead?: boolean }): Promise<HistoryDetail> => {
    const response = await api.get<HistoryDetail>(`/api/history/${id}`, {
      params: opts?.countRead ? { count_read: true } : undefined,
    })
    return response.data
  },

  getBatch: async (ids: number[]): Promise<HistoryItem[]> => {
    const response = await api.get<HistoryItem[]>('/api/history/batch', {
      params: { ids },
      paramsSerializer: (params) => {
        // ids=1&ids=2...
        const usp = new URLSearchParams()
        ;(params.ids || []).forEach((id: number) => usp.append('ids', String(id)))
        return usp.toString()
      },
    })
    return response.data
  },

  incrementReadCount: async (id: number): Promise<number> => {
    const response = await api.post<{ read_count: number }>(`/api/history/${id}/read`)
    return response.data.read_count
  },
  
  updateHistory: async (id: number, data: UpdateHistoryRequest): Promise<HistoryDetail> => {
    const response = await api.put<HistoryDetail>(`/api/history/${id}`, data)
    return response.data
  },
  
  searchHistory: async (query: string, skip = 0, limit = 100, hasSummary?: boolean, source?: 'subscription'): Promise<HistoryItem[]> => {
    const params: Record<string, any> = { q: query, skip, limit }
    if (typeof hasSummary === 'boolean') {
      params.has_summary = hasSummary
    }
    if (source === 'subscription') {
      params.source = 'subscription'
    }

    const response = await api.get<HistoryItem[]>('/api/history/search', {
      params,
    })
    return response.data
  },
  
  searchHistoryCount: async (query: string, hasSummary?: boolean, source?: 'subscription'): Promise<number> => {
    const params: Record<string, any> = { q: query }
    if (typeof hasSummary === 'boolean') {
      params.has_summary = hasSummary
    }
    if (source === 'subscription') {
      params.source = 'subscription'
    }
    const response = await api.get<{ count: number }>('/api/history/search/count', {
      params,
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

export interface SubscriptionItem {
  id: number
  channel_id: string | null
  channel_url: string
  channel_title: string | null
  status: 'pending' | 'resolved'
  created_at: string
  last_check_at: string | null
}

export const subscriptionsApi = {
  list: async (): Promise<SubscriptionItem[]> => {
    const response = await api.get<SubscriptionItem[]>('/api/subscriptions')
    return response.data
  },
  subscribe: async (channelUrl: string): Promise<SubscriptionItem> => {
    const response = await api.post<SubscriptionItem>('/api/subscriptions', { channel_url: channelUrl })
    return response.data
  },
  unsubscribe: async (id: number): Promise<void> => {
    await api.delete(`/api/subscriptions/${id}`)
  },
  getVideos: async (subscriptionId: number, skip = 0, limit = 100): Promise<HistoryItem[]> => {
    const response = await api.get<HistoryItem[]>(`/api/subscriptions/${subscriptionId}/videos`, {
      params: { skip, limit },
    })
    return response.data
  },
  update: async (id: number, payload: { channel_url?: string }): Promise<SubscriptionItem> => {
    const response = await api.patch<SubscriptionItem>(`/api/subscriptions/${id}`, payload)
    return response.data
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
  getPlaylists: async (): Promise<PlaylistResponse[]> => {
    const response = await api.get<PlaylistResponse[]>('/api/playlist/list')
    return response.data
  },
  
  getPlaylist: async (): Promise<PlaylistResponse> => {
    const response = await api.get<PlaylistResponse>('/api/playlist')
    return response.data
  },
  
  createPlaylist: async (name: string): Promise<PlaylistResponse> => {
    const response = await api.post<PlaylistResponse>('/api/playlist', { name })
    return response.data
  },
  
  updatePlaylist: async (playlistId: number, name: string): Promise<PlaylistResponse> => {
    const response = await api.put<PlaylistResponse>(`/api/playlist/${playlistId}`, { name })
    return response.data
  },
  
  deletePlaylist: async (playlistId: number): Promise<void> => {
    await api.delete(`/api/playlist/${playlistId}`)
  },
  
  getPlaylistItems: async (playlistId?: number): Promise<PlaylistItemResponse[]> => {
    const response = await api.get<PlaylistItemResponse[]>('/api/playlist/items', {
      params: playlistId ? { playlist_id: playlistId } : undefined,
    })
    return response.data
  },
  
  addItem: async (videoRecordId: number, playlistId?: number): Promise<PlaylistItemResponse> => {
    const response = await api.post<PlaylistItemResponse>(
      '/api/playlist/items',
      {
        video_record_id: videoRecordId,
      },
      {
        params: playlistId ? { playlist_id: playlistId } : undefined,
      }
    )
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
  
  clearPlaylist: async (playlistId?: number): Promise<void> => {
    await api.delete('/api/playlist/items', {
      params: playlistId ? { playlist_id: playlistId } : undefined,
    })
  },
}

export default api
