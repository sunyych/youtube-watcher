import { useMemo, useState, useEffect } from 'react'
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
  faBookOpen,
  faGripVertical
} from '@fortawesome/free-solid-svg-icons'
import { playlistApi, PlaylistItemResponse, PlaylistResponse, historyApi, HistoryItem } from '../services/api'
import './PlaylistPage.css'

interface PlaylistPageProps {
  onLogout: () => void
}

const PLAYABLE_STATUSES = new Set(['converting', 'transcribing', 'summarizing', 'completed'])
const isPlayableStatus = (status?: string) => !!status && PLAYABLE_STATUSES.has(status)

const PlaylistPage: React.FC<PlaylistPageProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const UNASSIGNED_PLAYLIST_ID = -1
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
  const [videoSearch, setVideoSearch] = useState('')
  const [assignedVideoIds, setAssignedVideoIds] = useState<Set<number>>(new Set())
  const [loadingAssigned, setLoadingAssigned] = useState(false)
  const [selectedPlaylistItemIds, setSelectedPlaylistItemIds] = useState<Set<number>>(new Set())
  const [lastSelectedPlaylistItemIndex, setLastSelectedPlaylistItemIndex] = useState<number | null>(null)
  const [lastSelectedVideoIndex, setLastSelectedVideoIndex] = useState<number | null>(null)

  useEffect(() => {
    loadPlaylists(true)
    loadVideos()
  }, [])

  useEffect(() => {
    if (selectedPlaylistId === UNASSIGNED_PLAYLIST_ID) {
      setItems([])
      setLoadingItems(false)
      return
    }
    if (selectedPlaylistId !== null) {
      loadPlaylistItems(selectedPlaylistId)
    } else {
      setItems([])
      setLoadingItems(false)
    }
    setSelectedPlaylistItemIds(new Set())
    setLastSelectedPlaylistItemIndex(null)
  }, [selectedPlaylistId])

  const refreshAssignedVideoIds = async (pls?: PlaylistResponse[]) => {
    const list = pls ?? playlists
    if (!list || list.length === 0) {
      setAssignedVideoIds(new Set())
      return
    }

    setLoadingAssigned(true)
    try {
      const results = await Promise.allSettled(list.map((p) => playlistApi.getPlaylistItems(p.id)))
      const next = new Set<number>()
      for (const r of results) {
        if (r.status !== 'fulfilled') continue
        for (const it of r.value) next.add(it.video_record_id)
      }
      setAssignedVideoIds(next)
    } finally {
      setLoadingAssigned(false)
    }
  }

  const loadPlaylists = async (selectFirstIfNeeded: boolean = false) => {
    setLoadingPlaylists(true)
    try {
      const data = await playlistApi.getPlaylists()
      setPlaylists(data)
      // Recompute "in any playlist" set
      refreshAssignedVideoIds(data)

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

  const handleOpenPlaylistPlayer = () => {
    if (selectedPlaylistId === null || selectedPlaylistId === UNASSIGNED_PLAYLIST_ID) return
    navigate(`/playlist/${selectedPlaylistId}/play`)
  }

  const handleOpenReadingList = () => {
    if (selectedPlaylistId === null || selectedPlaylistId === UNASSIGNED_PLAYLIST_ID) return
    navigate(`/playlist/${selectedPlaylistId}/read`)
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
      refreshAssignedVideoIds()
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
      refreshAssignedVideoIds()
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
      refreshAssignedVideoIds()
      alert(t('playlist.deleteSuccess'))
    } catch (err) {
      console.error('Failed to delete playlist:', err)
      alert(t('playlist.deleteFailed'))
    } finally {
      setUpdatingPlaylist(false)
    }
  }

  const handleVideoSelectByIndex = (index: number, shiftKey: boolean) => {
    const list = filteredSourceVideos
    if (index < 0 || index >= list.length) return
    if (shiftKey && lastSelectedVideoIndex !== null) {
      const lo = Math.min(lastSelectedVideoIndex, index)
      const hi = Math.max(lastSelectedVideoIndex, index)
      setSelectedVideoIds(prev => {
        const next = new Set(prev)
        for (let i = lo; i <= hi; i++) next.add(list[i].id)
        return next
      })
    } else {
      const videoId = list[index].id
      const currentlySelected = selectedVideoIds.has(videoId)
      setSelectedVideoIds(prev => {
        const next = new Set(prev)
        if (currentlySelected) next.delete(videoId)
        else next.add(videoId)
        return next
      })
      setLastSelectedVideoIndex(index)
    }
  }

  const handlePlaylistItemSelect = (itemId: number, index: number, shiftKey: boolean) => {
    if (shiftKey && lastSelectedPlaylistItemIndex !== null) {
      const lo = Math.min(lastSelectedPlaylistItemIndex, index)
      const hi = Math.max(lastSelectedPlaylistItemIndex, index)
      setSelectedPlaylistItemIds(prev => {
        const next = new Set(prev)
        for (let i = lo; i <= hi; i++) next.add(items[i].id)
        return next
      })
    } else {
      const currentlySelected = selectedPlaylistItemIds.has(itemId)
      setSelectedPlaylistItemIds(prev => {
        const next = new Set(prev)
        if (currentlySelected) next.delete(itemId)
        else next.add(itemId)
        return next
      })
      setLastSelectedPlaylistItemIndex(index)
    }
  }

  const handleRemoveSelectedPlaylistItems = async () => {
    if (selectedPlaylistItemIds.size === 0) return
    if (!window.confirm(t('playlist.removeSelectedConfirm', { count: selectedPlaylistItemIds.size }))) return
    setRemoving(-1)
    try {
      let failCount = 0
      for (const itemId of selectedPlaylistItemIds) {
        try {
          await playlistApi.removeItem(itemId)
        } catch {
          failCount++
        }
      }
      setSelectedPlaylistItemIds(new Set())
      setLastSelectedPlaylistItemIndex(null)
      if (selectedPlaylistId !== null) await loadPlaylistItems(selectedPlaylistId)
      refreshAssignedVideoIds()
      if (failCount > 0) alert(t('playlist.removeSelectedPartial', { fail: failCount }))
    } catch (err) {
      console.error('Failed to remove selected:', err)
      alert(t('playlist.removeFailed'))
    } finally {
      setRemoving(null)
    }
  }

  const unassignedVideos = useMemo(() => {
    if (!videos.length) return []
    return videos.filter((v) => !assignedVideoIds.has(v.id))
  }, [videos, assignedVideoIds])

  const sourceVideos = useMemo(() => {
    return selectedPlaylistId === UNASSIGNED_PLAYLIST_ID ? unassignedVideos : videos
  }, [selectedPlaylistId, unassignedVideos, videos])

  const filteredSourceVideos = useMemo(() => {
    const q = videoSearch.trim().toLowerCase()
    if (!q) return sourceVideos
    return sourceVideos.filter((v) => {
      const title = (v.title || '').toLowerCase()
      const url = (v.url || '').toLowerCase()
      const keywords = (v.keywords || '').toLowerCase()
      return title.includes(q) || url.includes(q) || keywords.includes(q)
    })
  }, [sourceVideos, videoSearch])

  const handleSelectAll = () => {
    const visibleIds = filteredSourceVideos.map((v) => v.id)
    if (visibleIds.length === 0) return

    const allVisibleSelected = visibleIds.every((id) => selectedVideoIds.has(id))
    setSelectedVideoIds((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) {
        // Deselect only visible results; keep other selections
        visibleIds.forEach((id) => next.delete(id))
      } else {
        // Select all visible results
        visibleIds.forEach((id) => next.add(id))
      }
      return next
    })
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
      refreshAssignedVideoIds()
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
        {/* Left sidebar: Reading list + Playlist tree */}
        <div className="playlist-sidebar">
          {/* Reading list section - above playlists */}
          <div className="reading-list-section">
            <div className="reading-list-section-header">
              <FontAwesomeIcon icon={faBookOpen} className="reading-list-section-icon" />
              <span className="reading-list-section-title">{t('playlist.reading.list', '阅读列表')}</span>
            </div>
            <button
              type="button"
              className="reading-list-open-button"
              onClick={handleOpenReadingList}
              disabled={
                selectedPlaylistId === null ||
                selectedPlaylistId === UNASSIGNED_PLAYLIST_ID ||
                updatingPlaylist ||
                loadingItems ||
                items.length === 0
              }
              title={t('playlist.openReading', '打开阅读列表')}
            >
              <FontAwesomeIcon icon={faBookOpen} />
              <span>{t('playlist.openReading', '打开阅读列表')}</span>
            </button>
          </div>

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
              <>
                <div
                  className={`playlist-tree-item ${selectedPlaylistId === UNASSIGNED_PLAYLIST_ID ? 'active' : ''}`}
                  onClick={() => setSelectedPlaylistId(UNASSIGNED_PLAYLIST_ID)}
                  title={t('playlist.unassignedHint', '显示未加入任何播放列表的视频')}
                >
                  <div className="playlist-tree-item-content">
                    <FontAwesomeIcon icon={selectedPlaylistId === UNASSIGNED_PLAYLIST_ID ? faFolderOpen : faFolder} className="playlist-tree-icon" />
                    <span className="playlist-tree-name">
                      {t('playlist.unassigned', '未加入任何播放列表')}
                      <span className="playlist-tree-count">
                        {loadingAssigned ? t('app.loading') : `(${unassignedVideos.length})`}
                      </span>
                    </span>
                  </div>
                </div>

                {playlists.map((playlist) => (
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
                ))}
              </>
            )}
          </div>

          {/* Selected playlist items */}
          {selectedPlaylistId !== null && selectedPlaylistId !== UNASSIGNED_PLAYLIST_ID && (
            <div className="playlist-items-panel">
              <div className="playlist-items-header">
                <h4>
                  {playlists.find(p => p.id === selectedPlaylistId)?.name || t('playlist.title')}
                </h4>
                <div className="playlist-items-actions">
                  {selectedPlaylistItemIds.size > 0 && (
                    <button
                      type="button"
                      className="remove-selected-button"
                      onClick={handleRemoveSelectedPlaylistItems}
                      disabled={removing !== null}
                      title={t('playlist.removeSelected')}
                    >
                      {t('playlist.removeSelected')} ({selectedPlaylistItemIds.size})
                    </button>
                  )}
                  <button
                    className="open-playlist-player-button"
                    onClick={handleOpenPlaylistPlayer}
                    title={t('playlist.openPlayer', '打开播放页')}
                    disabled={updatingPlaylist || loadingItems || items.length === 0}
                  >
                    <FontAwesomeIcon icon={faPlay} />
                  </button>
                  <button
                    className="open-reading-list-button"
                    onClick={handleOpenReadingList}
                    title={t('playlist.openReading', '打开阅读列表')}
                    disabled={updatingPlaylist || loadingItems || items.length === 0}
                  >
                    <FontAwesomeIcon icon={faBookOpen} />
                  </button>
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
                      className={`playlist-item ${selectedPlaylistItemIds.has(item.id) ? 'selected' : ''} ${draggedItemId === item.id ? 'dragging' : ''} ${dragOverItemIndex === index ? 'drag-over' : ''}`}
                      draggable
                      onDragStart={(e) => handleItemDragStart(e, item.id)}
                      onDragEnd={handleItemDragEnd}
                      onDragOver={(e) => handleItemDragOver(e, index)}
                      onDragLeave={handleItemDragLeave}
                      onDrop={(e) => handleItemDrop(e, index)}
                    >
                      <input
                        type="checkbox"
                        className="playlist-item-checkbox"
                        checked={selectedPlaylistItemIds.has(item.id)}
                        onChange={() => {}}
                        onClick={(e) => {
                          e.stopPropagation()
                          handlePlaylistItemSelect(item.id, index, e.nativeEvent.shiftKey)
                        }}
                        aria-label={t('playlist.selectItem', '选择')}
                      />
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
                        {isPlayableStatus(item.status) && (
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
                          disabled={removing === item.id || removing === -1}
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
              <div className="videos-controls">
                <div className="videos-search">
                  <input
                    value={videoSearch}
                    onChange={(e) => setVideoSearch(e.target.value)}
                    placeholder={t('playlist.searchPlaceholder', '搜索标题/URL/关键词...')}
                    aria-label={t('playlist.searchPlaceholder', '搜索标题/URL/关键词...')}
                  />
                  {videoSearch.trim() && (
                    <button
                      type="button"
                      className="videos-search-clear"
                      onClick={() => setVideoSearch('')}
                      title={t('playlist.clearSearch', '清除')}
                      aria-label={t('playlist.clearSearch', '清除')}
                    >
                      ×
                    </button>
                  )}
                </div>

                <div className="videos-actions">
                  <button className="select-all-button" onClick={handleSelectAll} disabled={filteredSourceVideos.length === 0}>
                    {filteredSourceVideos.length > 0 && filteredSourceVideos.every((v) => selectedVideoIds.has(v.id))
                      ? t('playlist.deselectAll')
                      : t('playlist.selectAll')}
                  </button>
                  <span className="selected-count">
                    {t('playlist.selectedCount', { count: selectedVideoIds.size })}{' '}
                    <span className="selected-count-muted">
                      ({filteredSourceVideos.length}/{sourceVideos.length})
                    </span>
                  </span>
                </div>
              </div>
            </div>
            {loadingVideos ? (
              <div className="empty-state">{t('app.loading')}</div>
            ) : videos.length === 0 ? (
              <div className="empty-state">{t('playlist.noVideos')}</div>
            ) : filteredSourceVideos.length === 0 ? (
              <div className="empty-state">{t('playlist.noSearchResults', '没有匹配的视频')}</div>
            ) : (
              <div className="videos-list">
                {filteredSourceVideos.map((video, index) => (
                  <div
                    key={video.id}
                    className={`video-item ${selectedVideoIds.has(video.id) ? 'selected' : ''} ${draggedVideoIds.has(video.id) ? 'dragging' : ''}`}
                    draggable
                    onDragStart={(e) => handleVideoDragStart(e, video.id)}
                    onDragEnd={handleVideoDragEnd}
                  >
                    <input
                      type="checkbox"
                      aria-label={`${t('playlist.selectVideo', '选择视频')} ${video.id}`}
                      checked={selectedVideoIds.has(video.id)}
                      className="video-checkbox"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleVideoSelectByIndex(index, e.nativeEvent.shiftKey)
                      }}
                      onChange={() => {}}
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
                    {isPlayableStatus(video.status) && (
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