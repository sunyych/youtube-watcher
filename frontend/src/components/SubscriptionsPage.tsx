import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import Header from './Header'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faEdit,
  faTrash,
  faChevronDown,
  faChevronRight,
  faList,
  faPlay,
} from '@fortawesome/free-solid-svg-icons'
import {
  subscriptionsApi,
  SubscriptionItem,
  HistoryItem,
  HistoryDetail,
  playlistApi,
  PlaylistResponse,
  historyApi,
} from '../services/api'
import HistoryDetailModal from './HistoryDetailModal'
import './SubscriptionsPage.css'

interface SubscriptionsPageProps {
  onLogout: () => void
}

const SubscriptionsPage: React.FC<SubscriptionsPageProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [addUrl, setAddUrl] = useState('')
  const [adding, setAdding] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [videos, setVideos] = useState<HistoryItem[]>([])
  const [videosLoading, setVideosLoading] = useState(false)
  const [videosSkip, setVideosSkip] = useState(0)
  const VIDEOS_PAGE_SIZE = 100
  const [selectedVideoIds, setSelectedVideoIds] = useState<Set<number>>(new Set())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editUrl, setEditUrl] = useState('')
  const [updating, setUpdating] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [playlistModalOpen, setPlaylistModalOpen] = useState(false)
  const [playlists, setPlaylists] = useState<PlaylistResponse[]>([])
  const [addingToPlaylist, setAddingToPlaylist] = useState(false)
  const [targetPlaylistId, setTargetPlaylistId] = useState<number | null>(null)
  const [autoPlaylistModalSubId, setAutoPlaylistModalSubId] = useState<number | null>(null)
  const [autoPlaylistSelectedId, setAutoPlaylistSelectedId] = useState<number | null>(null)
  const [updatingAutoPlaylist, setUpdatingAutoPlaylist] = useState(false)
  const [detailData, setDetailData] = useState<HistoryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const openVideoDetail = async (videoId: number) => {
    setDetailLoading(true)
    try {
      const d = await historyApi.getDetail(videoId, { countRead: true })
      setDetailData(d)
    } catch (err) {
      console.error('Failed to load video detail:', err)
      alert(t('history.item.loadDetailFailed'))
    } finally {
      setDetailLoading(false)
    }
  }

  const loadSubscriptions = async () => {
    setLoading(true)
    try {
      const data = await subscriptionsApi.list()
      setSubscriptions(data)
    } catch (err) {
      console.error('Failed to load subscriptions:', err)
      alert(t('subscriptions.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSubscriptions()
  }, [])

  useEffect(() => {
    playlistApi.getPlaylists().then(setPlaylists).catch(() => setPlaylists([]))
  }, [])

  const loadVideosForExpanded = useCallback(() => {
    if (expandedId === null) return
    setVideosLoading(true)
    subscriptionsApi
      .getVideos(expandedId, 0, VIDEOS_PAGE_SIZE)
      .then((data) => {
        setVideos(data)
        setSelectedVideoIds(new Set())
        setVideosSkip(data.length)
      })
      .catch((err) => {
        console.error('Failed to load subscription videos:', err)
        alert(t('subscriptions.videosLoadFailed'))
      })
      .finally(() => setVideosLoading(false))
  }, [expandedId, t])

  useEffect(() => {
    if (expandedId !== null) {
      loadVideosForExpanded()
    } else {
      setVideos([])
      setSelectedVideoIds(new Set())
      setVideosSkip(0)
    }
  }, [expandedId, loadVideosForExpanded])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const url = addUrl.trim()
    if (!url) return
    setAdding(true)
    try {
      await subscriptionsApi.subscribe(url)
      setAddUrl('')
      await loadSubscriptions()
    } catch (err: unknown) {
      const message = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      alert(message || t('subscriptions.addFailed'))
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (sub: SubscriptionItem) => {
    if (!window.confirm(t('subscriptions.deleteConfirm', { title: sub.channel_title || sub.channel_url }))) return
    setDeletingId(sub.id)
    try {
      await subscriptionsApi.unsubscribe(sub.id)
      if (expandedId === sub.id) setExpandedId(null)
      await loadSubscriptions()
    } catch (err) {
      console.error('Failed to delete subscription:', err)
      alert(t('subscriptions.deleteFailed'))
    } finally {
      setDeletingId(null)
    }
  }

  const startEdit = (sub: SubscriptionItem) => {
    setEditingId(sub.id)
    setEditUrl(sub.channel_url)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditUrl('')
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (editingId === null) return
    const url = editUrl.trim()
    if (!url) return
    setUpdating(true)
    try {
      await subscriptionsApi.update(editingId, { channel_url: url })
      cancelEdit()
      await loadSubscriptions()
    } catch (err: unknown) {
      const message = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      alert(message || t('subscriptions.updateFailed'))
    } finally {
      setUpdating(false)
    }
  }

  const toggleVideoSelection = (id: number) => {
    setSelectedVideoIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleToggleSelectAll = () => {
    setSelectedVideoIds((prev) => {
      if (videos.length === 0) return new Set()
      if (prev.size === videos.length) {
        return new Set()
      }
      return new Set(videos.map((v) => v.id))
    })
  }

  const handleLoadMoreVideos = async () => {
    if (expandedId === null) return
    setVideosLoading(true)
    try {
      const more = await subscriptionsApi.getVideos(expandedId, videosSkip, VIDEOS_PAGE_SIZE)
      if (more.length > 0) {
        setVideos((prev) => [...prev, ...more])
        setVideosSkip((prev) => prev + more.length)
      }
    } catch (err) {
      console.error('Failed to load more subscription videos:', err)
      alert(t('subscriptions.videosLoadFailed'))
    } finally {
      setVideosLoading(false)
    }
  }

  const openPlaylistModal = () => {
    if (selectedVideoIds.size === 0) {
      alert(t('subscriptions.noVideosSelected'))
      return
    }
    setPlaylistModalOpen(true)
    setTargetPlaylistId(null)
    playlistApi.getPlaylists().then(setPlaylists).catch(() => setPlaylists([]))
  }

  const handleAddToPlaylist = async () => {
    if (targetPlaylistId === null || selectedVideoIds.size === 0) return
    setAddingToPlaylist(true)
    let success = 0
    let fail = 0
    for (const videoRecordId of selectedVideoIds) {
      try {
        await playlistApi.addItem(videoRecordId, targetPlaylistId)
        success++
      } catch {
        fail++
      }
    }
    setAddingToPlaylist(false)
    setPlaylistModalOpen(false)
    setTargetPlaylistId(null)
    if (fail === 0) {
      alert(t('playlist.addSelectedSuccess', { count: success }))
    } else {
      alert(t('playlist.addSelectedPartial', { success, fail }))
    }
  }

  const openAutoPlaylistModal = (sub: SubscriptionItem) => {
    setAutoPlaylistModalSubId(sub.id)
    setAutoPlaylistSelectedId(sub.auto_playlist_id ?? null)
  }

  const handleSaveAutoPlaylist = async () => {
    if (autoPlaylistModalSubId === null) return
    setUpdatingAutoPlaylist(true)
    try {
      await subscriptionsApi.update(autoPlaylistModalSubId, { auto_playlist_id: autoPlaylistSelectedId })
      await loadSubscriptions()
      setAutoPlaylistModalSubId(null)
      setAutoPlaylistSelectedId(null)
      alert(t('subscriptions.autoPlaylistUpdated'))
    } catch (err) {
      console.error('Failed to update auto-playlist:', err)
      alert(t('subscriptions.updateFailed'))
    } finally {
      setUpdatingAutoPlaylist(false)
    }
  }

  const getPlaylistName = (id: number) => playlists.find((p) => p.id === id)?.name ?? ''

  const formatDate = (s: string | null) => {
    if (!s) return '—'
    try {
      const d = new Date(s)
      return d.toLocaleDateString(undefined, { dateStyle: 'short' })
    } catch {
      return s
    }
  }

  const allVideosSelected =
    videos.length > 0 && selectedVideoIds.size === videos.length

  return (
    <div className="subscriptions-page page-with-header">
      <Header title={t('subscriptions.title')} onLogout={onLogout} />

      <div className="subscriptions-content">
        <section className="subscriptions-add">
          <form onSubmit={handleAdd} className="subscriptions-add-form">
            <input
              type="url"
              className="subscriptions-add-input"
              placeholder={t('subscriptions.addPlaceholder')}
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              disabled={adding}
            />
            <button type="submit" className="subscriptions-add-button" disabled={adding}>
              {adding ? t('subscriptions.adding') : t('subscriptions.add')}
            </button>
          </form>
        </section>

        {loading ? (
          <div className="subscriptions-loading">{t('app.loading')}</div>
        ) : subscriptions.length === 0 ? (
          <div className="subscriptions-empty">{t('subscriptions.emptyState')}</div>
        ) : (
          <ul className="subscriptions-list">
            {subscriptions.map((sub) => (
              <li key={sub.id} className="subscriptions-list-item">
                <div
                  className="subscriptions-list-item-header"
                  onClick={() => setExpandedId((id) => (id === sub.id ? null : sub.id))}
                >
                  <span className="subscriptions-list-item-chevron">
                    <FontAwesomeIcon icon={expandedId === sub.id ? faChevronDown : faChevronRight} />
                  </span>
                  <div className="subscriptions-list-item-info">
                    <span className="subscriptions-list-item-title">
                      {sub.status === 'pending'
                        ? t('subscriptions.pendingResolve')
                        : (sub.channel_title || sub.channel_id || t('subscriptions.unknownChannel'))}
                    </span>
                    <span className="subscriptions-list-item-meta">
                      {sub.channel_url} · {t('subscriptions.created')} {formatDate(sub.created_at)}
                      {sub.status === 'resolved' && sub.last_check_at && ` · ${t('subscriptions.lastCheck')} ${formatDate(sub.last_check_at)}`}
                      {sub.status === 'pending' && (
                        <> · <span className="subscriptions-list-item-pending">{t('subscriptions.statusPending')}</span></>
                      )}
                      {sub.auto_playlist_id != null && (
                        <> · <span className="subscriptions-auto-playlist-badge">{t('subscriptions.autoPlaylistSet', { name: getPlaylistName(sub.auto_playlist_id) })}</span></>
                      )}
                    </span>
                  </div>
                  <div className="subscriptions-list-item-actions" onClick={(e) => e.stopPropagation()}>
                    {editingId === sub.id ? (
                      <form
                        className="subscriptions-edit-form"
                        onSubmit={handleUpdate}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="url"
                          className="subscriptions-edit-input"
                          value={editUrl}
                          onChange={(e) => setEditUrl(e.target.value)}
                          placeholder={t('subscriptions.addPlaceholder')}
                          disabled={updating}
                        />
                        <button type="submit" className="subscriptions-edit-save" disabled={updating}>
                          {updating ? t('history.item.saving') : t('history.item.save')}
                        </button>
                        <button type="button" className="subscriptions-edit-cancel" onClick={cancelEdit}>
                          {t('history.item.cancel')}
                        </button>
                      </form>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="subscriptions-btn subscriptions-btn-autoplaylist"
                          onClick={(e) => { e.stopPropagation(); openAutoPlaylistModal(sub) }}
                          title={t('subscriptions.autoPlaylist')}
                        >
                          <FontAwesomeIcon icon={faList} /> <span className="subscriptions-btn-autoplaylist-label">{t('subscriptions.autoPlaylist')}</span>
                        </button>
                        <button
                          type="button"
                          className="subscriptions-btn subscriptions-btn-edit"
                          onClick={() => startEdit(sub)}
                          title={t('subscriptions.edit')}
                        >
                          <FontAwesomeIcon icon={faEdit} />
                        </button>
                        <button
                          type="button"
                          className="subscriptions-btn subscriptions-btn-delete"
                          onClick={() => handleDelete(sub)}
                          disabled={deletingId === sub.id}
                          title={t('subscriptions.delete')}
                        >
                          {deletingId === sub.id ? t('history.item.deleting') : <FontAwesomeIcon icon={faTrash} />}
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {expandedId === sub.id && (
                  <div className="subscriptions-videos">
                    <div className="subscriptions-videos-toolbar">
                      <span className="subscriptions-videos-title">
                        <FontAwesomeIcon icon={faList} /> {t('subscriptions.channelContent')}
                      </span>
                      <div className="subscriptions-videos-actions">
                        <button
                          type="button"
                          className="subscriptions-select-all-btn"
                          onClick={handleToggleSelectAll}
                          disabled={videos.length === 0}
                        >
                          {allVideosSelected ? t('playlist.deselectAll') : t('playlist.selectAll')}
                        </button>
                        <button
                          type="button"
                          className="subscriptions-add-to-playlist-btn"
                          onClick={openPlaylistModal}
                          disabled={selectedVideoIds.size === 0}
                        >
                          {t('subscriptions.addToPlaylist')} {selectedVideoIds.size > 0 && `(${selectedVideoIds.size})`}
                        </button>
                      </div>
                    </div>
                    {videosLoading ? (
                      <div className="subscriptions-videos-loading">{t('app.loading')}</div>
                    ) : videos.length === 0 ? (
                      <div className="subscriptions-videos-empty">{t('subscriptions.noVideos')}</div>
                    ) : (
                      <>
                        <ul className="subscriptions-videos-list">
                          {videos.map((v) => (
                            <li key={v.id} className="subscriptions-video-row">
                              <label className="subscriptions-video-checkbox" title={t('playlist.selectItem')}>
                                <input
                                  type="checkbox"
                                  aria-label={t('playlist.selectItem')}
                                  checked={selectedVideoIds.has(v.id)}
                                  onChange={() => toggleVideoSelection(v.id)}
                                />
                              </label>
                              <button
                                type="button"
                                className="subscriptions-video-title subscriptions-video-title-button"
                                title={v.title || undefined}
                                onClick={(e) => { e.stopPropagation(); openVideoDetail(v.id) }}
                                disabled={detailLoading}
                              >
                                {v.title || v.url}
                              </button>
                              <span className="subscriptions-video-status">{v.status}</span>
                              <button
                                type="button"
                                className="subscriptions-video-play"
                                onClick={() => navigate(`/player/${v.id}`)}
                                title={t('history.item.play')}
                              >
                                <FontAwesomeIcon icon={faPlay} />
                              </button>
                            </li>
                          ))}
                        </ul>
                        {videos.length >= VIDEOS_PAGE_SIZE && (
                          <div className="subscriptions-videos-load-more">
                            <button
                              type="button"
                              className="subscriptions-videos-load-more-btn"
                              onClick={handleLoadMoreVideos}
                              disabled={videosLoading}
                            >
                              {videosLoading ? t('app.loading') : t('subscriptions.loadMoreChannel')}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {playlistModalOpen && (
        <div className="subscriptions-modal-overlay" onClick={() => !addingToPlaylist && setPlaylistModalOpen(false)}>
          <div className="subscriptions-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t('subscriptions.selectPlaylist')}</h3>
            {playlists.length === 0 ? (
              <p>{t('playlist.noPlaylists')}</p>
            ) : (
              <ul className="subscriptions-playlist-picker">
                {playlists.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className={`subscriptions-playlist-picker-item ${targetPlaylistId === p.id ? 'active' : ''}`}
                      onClick={() => setTargetPlaylistId(p.id)}
                    >
                      {p.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="subscriptions-modal-actions">
              <button
                type="button"
                className="subscriptions-modal-cancel"
                onClick={() => setPlaylistModalOpen(false)}
                disabled={addingToPlaylist}
              >
                {t('history.item.cancel')}
              </button>
              <button
                type="button"
                className="subscriptions-modal-confirm"
                onClick={handleAddToPlaylist}
                disabled={targetPlaylistId === null || addingToPlaylist}
              >
                {addingToPlaylist ? t('history.item.addingToPlaylist') : t('subscriptions.addToPlaylist')}
              </button>
            </div>
          </div>
        </div>
      )}

      {autoPlaylistModalSubId !== null && (
        <div className="subscriptions-modal-overlay" onClick={() => !updatingAutoPlaylist && setAutoPlaylistModalSubId(null)}>
          <div className="subscriptions-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t('subscriptions.autoPlaylistTitle')}</h3>
            <ul className="subscriptions-playlist-picker">
              <li>
                <button
                  type="button"
                  className={`subscriptions-playlist-picker-item ${autoPlaylistSelectedId === null ? 'active' : ''}`}
                  onClick={() => setAutoPlaylistSelectedId(null)}
                >
                  {t('subscriptions.autoPlaylistNone')}
                </button>
              </li>
              {playlists.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className={`subscriptions-playlist-picker-item ${autoPlaylistSelectedId === p.id ? 'active' : ''}`}
                    onClick={() => setAutoPlaylistSelectedId(p.id)}
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
            <div className="subscriptions-modal-actions">
              <button
                type="button"
                className="subscriptions-modal-cancel"
                onClick={() => setAutoPlaylistModalSubId(null)}
                disabled={updatingAutoPlaylist}
              >
                {t('history.item.cancel')}
              </button>
              <button
                type="button"
                className="subscriptions-modal-confirm"
                onClick={handleSaveAutoPlaylist}
                disabled={updatingAutoPlaylist}
              >
                {updatingAutoPlaylist ? t('history.item.saving') : t('history.item.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      <HistoryDetailModal
        detail={detailData}
        onClose={() => setDetailData(null)}
        onDeleted={loadVideosForExpanded}
        onSaved={setDetailData}
      />
    </div>
  )
}

export default SubscriptionsPage
