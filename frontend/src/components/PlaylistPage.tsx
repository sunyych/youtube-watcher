import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Header from './Header'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { 
  faPlay, 
  faTrash, 
  faBroom,
  faPlus,
  faEdit,
  faFolder,
  faFolderOpen,
  faGripVertical
} from '@fortawesome/free-solid-svg-icons'
import { playlistApi, PlaylistItemResponse, PlaylistResponse, historyApi, HistoryItem } from '../services/api'
import './PlaylistPage.css'

interface PlaylistPageProps {
  onLogout: () => void
}

const PlaylistPage: React.FC<PlaylistPageProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [playlists, setPlaylists] = useState<PlaylistResponse[]>([])
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<number | null>(null)
  const [items, setItems] = useState<PlaylistItemResponse[]>([])
  const [videos, setVideos] = useState<HistoryItem[]>([])
  const [selectedVideoIds, setSelectedVideoIds] = useState<Set<number>>(new Set())
  const [loadingPlaylists, setLoadingPlaylists] = useState(true)
  const [loadingItems, setLoadingItems] = useState(true)
  const [loadingVideos, setLoadingVideos] = useState(true)
  const [removing, setRemoving] = useState<number | null>(null)
  const [updatingPlaylist, setUpdatingPlaylist] = useState(false)
  const [draggedVideoIds, setDraggedVideoIds] = useState<Set<number>>(new Set())
  const [dragOverPlaylistId, setDragOverPlaylistId] = useState<number | null>(null)
  const [draggedItemId, setDraggedItemId] = useState<number | null>(null)
  const [dragOverItemIndex, setDragOverItemIndex] = useState<number | null>(null)

  useEffect(() => {
    loadPlaylists(true)
    loadVideos()
  }, [])

  useEffect(() => {
    if (selectedPlaylistId !== null) {
      loadPlaylistItems(selectedPlaylistId)
    } else {
      setItems([])
      setLoadingItems(false)
    }
  }, [selectedPlaylistId])

  const loadPlaylists = async (selectFirstIfNeeded: boolean = false) => {
    setLoadingPlaylists(true)
    try {
      const data = await playlistApi.getPlaylists()
      setPlaylists(data)

      if (data.length === 0) {
        setSelectedPlaylistId(null)
        setItems([])
      } else if (selectFirstIfNeeded || selectedPlaylistId === null) {
        setSelectedPlaylistId(data[0].id)
      } else {
        // Ensure selected playlist still exists
        const exists = data.some(p => p.id === selectedPlaylistId)
        if (!exists) {
          setSelectedPlaylistId(data[0].id)
        }
      }
    } catch (err) {
      console.error('Failed to load playlists:', err)
      alert(t('playlist.loadPlaylistsFailed'))
    } finally {
      setLoadingPlaylists(false)
    }
  }

  const loadPlaylistItems = async (playlistId: number) => {
    setLoadingItems(true)
    try {
      const data = await playlistApi.getPlaylistItems(playlistId)
      setItems(data)
    } catch (err) {
      console.error('Failed to load playlist:', err)
      alert(t('playlist.loadFailed'))
    } finally {
      setLoadingItems(false)
    }
  }

  const loadVideos = async () => {
    setLoadingVideos(true)
    try {
      // Load all videos with a large limit
      const data = await historyApi.getHistory(0, 10000)
      setVideos(data)
    } catch (err) {
      console.error('Failed to load videos:', err)
      alert(t('playlist.loadVideosFailed'))
    } finally {
      setLoadingVideos(false)
    }
  }

  const handlePlay = (videoRecordId: number) => {
    navigate(`/player/${videoRecordId}?from=playlist`)
  }


  const handleRemove = async (itemId: number) => {
    if (!window.confirm(t('playlist.removeConfirm'))) {
      return
    }
    
    setRemoving(itemId)
    try {
      await playlistApi.removeItem(itemId)
      if (selectedPlaylistId !== null) {
        await loadPlaylistItems(selectedPlaylistId)
      }
    } catch (err) {
      console.error('Failed to remove item:', err)
      alert(t('playlist.removeFailed'))
    } finally {
      setRemoving(null)
    }
  }

  const handleClear = async () => {
    if (!window.confirm(t('playlist.clearConfirm'))) {
      return
    }
    
    if (selectedPlaylistId === null) {
      alert(t('playlist.selectPlaylist'))
      return
    }
    
    try {
      await playlistApi.clearPlaylist(selectedPlaylistId)
      await loadPlaylistItems(selectedPlaylistId)
      alert(t('playlist.clearSuccess'))
    } catch (err) {
      console.error('Failed to clear playlist:', err)
      alert(t('playlist.clearFailed'))
    }
  }

  const handleCreatePlaylist = async () => {
    const name = window.prompt(t('playlist.newPlaylistPrompt'))
    if (!name || !name.trim()) {
      return
    }
    setUpdatingPlaylist(true)
    try {
      const playlist = await playlistApi.createPlaylist(name.trim())
      await loadPlaylists()
      setSelectedPlaylistId(playlist.id)
      alert(t('playlist.createSuccess'))
    } catch (err) {
      console.error('Failed to create playlist:', err)
      alert(t('playlist.createFailed'))
    } finally {
      setUpdatingPlaylist(false)
    }
  }

  const handleRenamePlaylist = async (playlistId: number, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation()
    }
    const current = playlists.find(p => p.id === playlistId)
    const name = window.prompt(t('playlist.renamePlaylistPrompt'), current?.name || '')
    if (!name || !name.trim()) {
      return
    }
    setUpdatingPlaylist(true)
    try {
      await playlistApi.updatePlaylist(playlistId, name.trim())
      await loadPlaylists()
      alert(t('playlist.renameSuccess'))
    } catch (err) {
      console.error('Failed to rename playlist:', err)
      alert(t('playlist.renameFailed'))
    } finally {
      setUpdatingPlaylist(false)
    }
  }

  const handleDeletePlaylist = async (playlistId: number, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation()
    }
    const current = playlists.find(p => p.id === playlistId)
    const confirmMessage = current
      ? t('playlist.deletePlaylistConfirm', { name: current.name })
      : t('playlist.deletePlaylistConfirmNoName')
    if (!window.confirm(confirmMessage)) {
      return
    }
    setUpdatingPlaylist(true)
    try {
      await playlistApi.deletePlaylist(playlistId)
      await loadPlaylists(true)
      alert(t('playlist.deleteSuccess'))
    } catch (err) {
      console.error('Failed to delete playlist:', err)
      alert(t('playlist.deleteFailed'))
    } finally {
      setUpdatingPlaylist(false)
    }
  }

  const handleVideoSelect = (videoId: number, checked: boolean) => {
    setSelectedVideoIds(prev => {
      const newSet = new Set(prev)
      if (checked) {
        newSet.add(videoId)
      } else {
        newSet.delete(videoId)
      }
      return newSet
    })
  }

  const handleSelectAll = () => {
    if (selectedVideoIds.size === videos.length) {
      setSelectedVideoIds(new Set())
    } else {
      setSelectedVideoIds(new Set(videos.map(v => v.id)))
    }
  }


  // Drag and drop handlers for videos to playlists
  const handleVideoDragStart = (e: React.DragEvent, videoId: number) => {
    // If this video is selected, drag all selected videos
    const videosToDrag = selectedVideoIds.has(videoId) ? selectedVideoIds : new Set([videoId])
    setDraggedVideoIds(videosToDrag)
    e.dataTransfer.effectAllowed = 'move'
    // Store all video IDs as JSON
    e.dataTransfer.setData('application/json', JSON.stringify(Array.from(videosToDrag)))
    e.dataTransfer.setData('text/plain', videoId.toString()) // Fallback
  }

  const handleVideoDragEnd = () => {
    setDraggedVideoIds(new Set())
  }

  const handlePlaylistDragOver = (e: React.DragEvent, playlistId: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverPlaylistId(playlistId)
  }

  const handlePlaylistDragLeave = () => {
    setDragOverPlaylistId(null)
  }

  const handlePlaylistDrop = async (e: React.DragEvent, playlistId: number) => {
    e.preventDefault()
    setDragOverPlaylistId(null)
    
    // Get video IDs from drag data
    let videoIds: number[] = []
    try {
      const jsonData = e.dataTransfer.getData('application/json')
      if (jsonData) {
        videoIds = JSON.parse(jsonData)
      } else {
        // Fallback to single video ID
        const videoId = parseInt(e.dataTransfer.getData('text/plain'))
        if (videoId) videoIds = [videoId]
      }
    } catch (err) {
      console.error('Failed to parse drag data:', err)
      return
    }

    if (videoIds.length === 0) return

    setUpdatingPlaylist(true)
    try {
      let successCount = 0
      let failCount = 0
      for (const videoId of videoIds) {
        try {
          await playlistApi.addItem(videoId, playlistId)
          successCount++
        } catch (err: any) {
          if (err.response?.status === 400 && err.response?.data?.detail?.includes('already in playlist')) {
            // Skip if already in playlist
            continue
          }
          failCount++
        }
      }
      if (selectedPlaylistId === playlistId) {
        await loadPlaylistItems(playlistId)
      }
      setSelectedVideoIds(new Set())
      if (failCount === 0) {
        alert(t('playlist.addSelectedSuccess', { count: successCount }))
      } else {
        alert(t('playlist.addSelectedPartial', { success: successCount, fail: failCount }))
      }
    } catch (err) {
      console.error('Failed to add videos:', err)
      alert(t('playlist.addSelectedFailed'))
    } finally {
      setUpdatingPlaylist(false)
      setDraggedVideoIds(new Set())
    }
  }

  // Drag and drop handlers for playlist items (reordering)
  const handleItemDragStart = (e: React.DragEvent, itemId: number) => {
    setDraggedItemId(itemId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', itemId.toString())
  }

  const handleItemDragEnd = () => {
    setDraggedItemId(null)
    setDragOverItemIndex(null)
  }

  const handleItemDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverItemIndex(index)
  }

  const handleItemDragLeave = () => {
    setDragOverItemIndex(null)
  }

  const handleItemDrop = async (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault()
    setDragOverItemIndex(null)
    
    const draggedItemId = parseInt(e.dataTransfer.getData('text/plain'))
    if (!draggedItemId || !selectedPlaylistId) return

    const currentIndex = items.findIndex(item => item.id === draggedItemId)
    if (currentIndex === targetIndex || currentIndex === -1) return

    // Calculate new position: targetIndex + 1 (positions are 1-based)
    const newPosition = targetIndex + 1

    try {
      await playlistApi.updateItem(draggedItemId, newPosition)
      await loadPlaylistItems(selectedPlaylistId)
    } catch (err) {
      console.error('Failed to reorder item:', err)
      alert(t('playlist.moveFailed'))
    } finally {
      setDraggedItemId(null)
    }
  }

  return (
    <div className="playlist-page page-with-header">
      <Header title={t('playlist.title')} onLogout={onLogout} />

      <div className="playlist-layout">
        {/* Left sidebar: Playlist tree */}
        <div className="playlist-sidebar">
          <div className="playlist-sidebar-header">
            <h3>{t('playlist.playlists')}</h3>
            <button
              className="add-playlist-sidebar-button"
              onClick={handleCreatePlaylist}
              disabled={updatingPlaylist}
              title={t('playlist.newPlaylist')}
            >
              <FontAwesomeIcon icon={faPlus} />
            </button>
          </div>
          <div className="playlist-tree">
            {loadingPlaylists ? (
              <div className="playlist-tree-loading">{t('app.loading')}</div>
            ) : playlists.length === 0 ? (
              <div className="playlist-tree-empty">{t('playlist.noPlaylists')}</div>
            ) : (
              playlists.map((playlist) => (
                <div
                  key={playlist.id}
                  className={`playlist-tree-item ${selectedPlaylistId === playlist.id ? 'active' : ''} ${dragOverPlaylistId === playlist.id ? 'drag-over' : ''}`}
                  onClick={() => setSelectedPlaylistId(playlist.id)}
                  onDragOver={(e) => handlePlaylistDragOver(e, playlist.id)}
                  onDragLeave={handlePlaylistDragLeave}
                  onDrop={(e) => handlePlaylistDrop(e, playlist.id)}
                >
                  <div className="playlist-tree-item-content">
                    <FontAwesomeIcon 
                      icon={selectedPlaylistId === playlist.id ? faFolderOpen : faFolder} 
                      className="playlist-tree-icon"
                    />
                    <span className="playlist-tree-name">{playlist.name}</span>
                  </div>
                  <div className="playlist-tree-item-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="playlist-tree-edit-button"
                      onClick={(e) => handleRenamePlaylist(playlist.id, e)}
                      disabled={updatingPlaylist}
                      title={t('playlist.renamePlaylist')}
                    >
                      <FontAwesomeIcon icon={faEdit} />
                    </button>
                    <button
                      className="playlist-tree-delete-button"
                      onClick={(e) => handleDeletePlaylist(playlist.id, e)}
                      disabled={updatingPlaylist}
                      title={t('playlist.deletePlaylist')}
                    >
                      <FontAwesomeIcon icon={faTrash} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Selected playlist items */}
          {selectedPlaylistId !== null && (
            <div className="playlist-items-panel">
              <div className="playlist-items-header">
                <h4>
                  {playlists.find(p => p.id === selectedPlaylistId)?.name || t('playlist.title')}
                </h4>
                <div className="playlist-items-actions">
                  <button 
                    className="clear-button"
                    onClick={handleClear}
                    title={t('playlist.clear')}
                    disabled={updatingPlaylist}
                  >
                    <FontAwesomeIcon icon={faBroom} />
                  </button>
                </div>
              </div>
              {loadingItems ? (
                <div className="empty-state-small">{t('app.loading')}</div>
              ) : items.length === 0 ? (
                <div className="empty-state-small">{t('playlist.emptyState')}</div>
              ) : (
                <div className="playlist-items-list">
                  {items.map((item, index) => (
                    <div
                      key={item.id}
                      className={`playlist-item ${draggedItemId === item.id ? 'dragging' : ''} ${dragOverItemIndex === index ? 'drag-over' : ''}`}
                      draggable
                      onDragStart={(e) => handleItemDragStart(e, item.id)}
                      onDragEnd={handleItemDragEnd}
                      onDragOver={(e) => handleItemDragOver(e, index)}
                      onDragLeave={handleItemDragLeave}
                      onDrop={(e) => handleItemDrop(e, index)}
                    >
                      <div className="playlist-item-drag-handle">
                        <FontAwesomeIcon icon={faGripVertical} />
                      </div>
                      <div className="playlist-item-info">
                        <h4>{item.title || item.url}</h4>
                        <div className="playlist-item-meta">
                          <span className={`status status-${item.status}`}>
                            {item.status}
                          </span>
                          {item.status === 'completed' && (
                            <span className="progress">{Math.round(item.progress)}%</span>
                          )}
                        </div>
                      </div>
                      <div className="playlist-item-actions">
                        {item.status === 'completed' && (
                          <button
                            className="play-button"
                            onClick={() => handlePlay(item.video_record_id)}
                            title={t('playlist.play')}
                          >
                            <FontAwesomeIcon icon={faPlay} />
                          </button>
                        )}
                        <button
                          className="remove-button"
                          onClick={() => handleRemove(item.id)}
                          disabled={removing === item.id}
                          title={t('playlist.remove')}
                        >
                          <FontAwesomeIcon icon={faTrash} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right content: Video list */}
        <div className="playlist-main-content">
          <div className="videos-section">
            <div className="videos-header">
              <h3>{t('playlist.allVideos')}</h3>
              <div className="videos-actions">
                <button
                  className="select-all-button"
                  onClick={handleSelectAll}
                >
                  {selectedVideoIds.size === videos.length ? t('playlist.deselectAll') : t('playlist.selectAll')}
                </button>
                {selectedVideoIds.size > 0 && (
                  <span className="selected-count">
                    {t('playlist.selectedCount', { count: selectedVideoIds.size })}
                  </span>
                )}
              </div>
            </div>
            {loadingVideos ? (
              <div className="empty-state">{t('app.loading')}</div>
            ) : videos.length === 0 ? (
              <div className="empty-state">{t('playlist.noVideos')}</div>
            ) : (
              <div className="videos-list">
                {videos.map((video) => (
                  <div
                    key={video.id}
                    className={`video-item ${selectedVideoIds.has(video.id) ? 'selected' : ''} ${draggedVideoIds.has(video.id) ? 'dragging' : ''}`}
                    draggable
                    onDragStart={(e) => handleVideoDragStart(e, video.id)}
                    onDragEnd={handleVideoDragEnd}
                  >
                    <input
                      type="checkbox"
                      checked={selectedVideoIds.has(video.id)}
                      onChange={(e) => handleVideoSelect(video.id, e.target.checked)}
                      className="video-checkbox"
                      onClick={(e) => e.stopPropagation()}
                    />
                    <div className="video-item-info">
                      <h4>{video.title || video.url}</h4>
                      <div className="video-item-meta">
                        <span className={`status status-${video.status}`}>
                          {video.status}
                        </span>
                        {video.keywords && (
                          <span className="video-keywords">
                            {video.keywords.split(',').slice(0, 3).join(', ')}
                          </span>
                        )}
                      </div>
                    </div>
                    {video.status === 'completed' && (
                      <button
                        className="video-play-button"
                        onClick={() => handlePlay(video.id)}
                        title={t('playlist.play')}
                      >
                        <FontAwesomeIcon icon={faPlay} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default PlaylistPage