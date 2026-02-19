import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faArrowLeft,
  faArrowRight,
  faChevronLeft,
  faChevronRight,
  faCompress,
  faExpand,
  faList,
  faPause,
  faPlay,
} from '@fortawesome/free-solid-svg-icons'
import { playlistApi, PlaylistItemResponse, videoApi, VideoStatus } from '../services/api'
import './PlaylistPlayerPage.css'

interface PlaylistPlayerPageProps {
  onLogout: () => void
}

const PLAYABLE_STATUSES = new Set(['converting', 'transcribing', 'summarizing', 'completed'])
const isPlayableStatus = (status?: string) => !!status && PLAYABLE_STATUSES.has(status)

const PlaylistPlayerPage: React.FC<PlaylistPlayerPageProps> = () => {
  const { t } = useTranslation()
  const { playlistId, videoId } = useParams<{ playlistId: string; videoId?: string }>()
  const navigate = useNavigate()

  const pid = useMemo(() => {
    const n = Number(playlistId)
    return Number.isFinite(n) ? n : null
  }, [playlistId])

  const vid = useMemo(() => {
    if (!videoId) return null
    const n = Number(videoId)
    return Number.isFinite(n) ? n : null
  }, [videoId])

  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const fullscreenTargetRef = useRef<HTMLDivElement>(null)
  const [items, setItems] = useState<PlaylistItemResponse[]>([])
  const [loadingItems, setLoadingItems] = useState(true)
  const [videoInfo, setVideoInfo] = useState<VideoStatus | null>(null)
  const [loadingVideo, setLoadingVideo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [playbackMode, setPlaybackMode] = useState<'video' | 'audio'>('video')
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isPlaylistCollapsed, setIsPlaylistCollapsed] = useState(() => {
    try {
      return localStorage.getItem('playlist_player_collapsed') === '1'
    } catch {
      return false
    }
  })
  const desiredPlayingRef = useRef(false)

  useEffect(() => {
    try {
      localStorage.setItem('playlist_player_collapsed', isPlaylistCollapsed ? '1' : '0')
    } catch {
      // ignore
    }
  }, [isPlaylistCollapsed])

  useEffect(() => {
    const update = () => {
      const target = fullscreenTargetRef.current
      setIsFullscreen(!!target && document.fullscreenElement === target)
    }
    update()
    document.addEventListener('fullscreenchange', update)
    document.addEventListener('webkitfullscreenchange' as any, update)
    return () => {
      document.removeEventListener('fullscreenchange', update)
      document.removeEventListener('webkitfullscreenchange' as any, update)
    }
  }, [])

  useEffect(() => {
    if (pid === null) return
    ;(async () => {
      setLoadingItems(true)
      try {
        const next = await playlistApi.getPlaylistItems(pid)
        setItems(next)
      } catch (e) {
        console.error('Failed to load playlist items:', e)
      } finally {
        setLoadingItems(false)
      }
    })()
  }, [pid])

  // If route is /playlist/:playlistId/play, auto-navigate to first item.
  useEffect(() => {
    if (pid === null) return
    if (vid !== null) return
    if (loadingItems) return
    if (!items.length) return

    const firstPlayable = items.find((it) => isPlayableStatus(it.status)) ?? items[0]
    navigate(`/playlist/${pid}/play/${firstPlayable.video_record_id}`, { replace: true })
  }, [pid, vid, loadingItems, items, navigate])

  useEffect(() => {
    if (vid === null) return
    ;(async () => {
      setLoadingVideo(true)
      setError(null)
      try {
        // Count as a "read" when opening the player
        const status = await videoApi.getStatus(vid, { countRead: true })
        setVideoInfo(status)
        if (!isPlayableStatus(status.status)) {
          setError(t('player.videoNotReady'))
        }
      } catch (err: any) {
        console.error('Failed to load video:', err)
        setVideoInfo(null)
        setError(err.response?.data?.detail || t('player.loadFailed'))
      } finally {
        setLoadingVideo(false)
      }
    })()
  }, [vid, t])

  const currentIndex = useMemo(() => {
    if (vid === null) return -1
    return items.findIndex((it) => it.video_record_id === vid)
  }, [items, vid])

  const canPlayPrevious = currentIndex > 0
  const canPlayNext = currentIndex >= 0 && currentIndex < items.length - 1

  const streamUrl = vid !== null ? videoApi.getStreamUrl(vid) : ''

  const getActiveMedia = () => (playbackMode === 'audio' ? audioRef.current : videoRef.current)

  const handlePlay = async () => {
    const el = getActiveMedia()
    if (!el) return
    try {
      await el.play()
      desiredPlayingRef.current = true
      setIsPlaying(true)
    } catch (e) {
      console.warn('Play failed:', e)
    }
  }

  const handlePause = () => {
    const el = getActiveMedia()
    if (!el) return
    el.pause()
    desiredPlayingRef.current = false
    setIsPlaying(false)
  }

  const handlePlayPause = () => {
    if (isPlaying) {
      handlePause()
    } else {
      void handlePlay()
    }
  }

  const handleTimeUpdate = () => {
    const el = getActiveMedia()
    if (!el) return
    setCurrentTime(el.currentTime || 0)
  }

  const handleLoadedMetadata = () => {
    const el = getActiveMedia()
    if (!el) return
    setDuration(el.duration || 0)
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = Number(e.target.value)
    const el = getActiveMedia()
    if (!el) return
    el.currentTime = newTime
    setCurrentTime(newTime)
  }

  const formatTime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const goToVideo = (recordId: number) => {
    if (pid === null) return
    navigate(`/playlist/${pid}/play/${recordId}`)
  }

  const handlePrevious = () => {
    if (!canPlayPrevious) return
    goToVideo(items[currentIndex - 1].video_record_id)
  }

  const handleNext = () => {
    if (!canPlayNext) return
    goToVideo(items[currentIndex + 1].video_record_id)
  }

  // MediaSession for lockscreen/background controls (best-effort).
  useEffect(() => {
    if (!('mediaSession' in navigator) || !videoInfo) return
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: videoInfo.title || 'Video',
        artist: 'YouTube Watcher',
      })

      navigator.mediaSession.setActionHandler('play', () => {
        void handlePlay()
      })
      navigator.mediaSession.setActionHandler('pause', () => {
        handlePause()
      })
      navigator.mediaSession.setActionHandler('previoustrack', handlePrevious)
      navigator.mediaSession.setActionHandler('nexttrack', handleNext)
    } catch (e) {
      console.warn('Failed to set MediaSession handlers:', e)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoInfo, playbackMode, pid, vid, items.length])

  const switchToAudioIfNeeded = async () => {
    if (playbackMode === 'audio') return
    const v = videoRef.current
    const a = audioRef.current
    if (!v || !a) return
    a.currentTime = v.currentTime || 0
    try {
      await a.play()
      setPlaybackMode('audio')
      v.pause()
      setIsPlaying(true)
    } catch (e) {
      console.warn('Audio background play failed:', e)
    }
  }

  const switchBackToVideoIfNeeded = async () => {
    if (playbackMode === 'video') return
    const v = videoRef.current
    const a = audioRef.current
    if (!v || !a) return
    v.currentTime = a.currentTime || 0
    try {
      await v.play()
      setPlaybackMode('video')
      a.pause()
      setIsPlaying(true)
    } catch (e) {
      console.warn('Switch back to video failed:', e)
    }
  }

  // Best-effort: keep playing when screen locks / tab hidden pauses video.
  useEffect(() => {
    const onVisibility = () => {
      if (!desiredPlayingRef.current) return
      if (document.hidden) {
        void switchToAudioIfNeeded()
      } else {
        void switchBackToVideoIfNeeded()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbackMode, streamUrl])

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onPause = () => {
      if (document.hidden && desiredPlayingRef.current) {
        void switchToAudioIfNeeded()
      }
    }
    v.addEventListener('pause', onPause)
    return () => v.removeEventListener('pause', onPause)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbackMode, streamUrl])

  const toggleFullscreen = async () => {
    const target = fullscreenTargetRef.current
    if (!target) return

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
        return
      }
      if (target.requestFullscreen) {
        await target.requestFullscreen()
        return
      }
    } catch (e) {
      console.warn('Fullscreen API failed, falling back:', e)
    }

    const v: any = videoRef.current
    if (v && typeof v.webkitEnterFullscreen === 'function') {
      v.webkitEnterFullscreen()
    }
  }

  const togglePlaylistCollapsed = () => {
    setIsPlaylistCollapsed((v) => !v)
  }

  if (pid === null) {
    return <div className="playlist-player-page">{t('player.videoNotFound')}</div>
  }

  if (loadingItems || (vid === null && items.length > 0)) {
    return <div className="playlist-player-page">{t('app.loading')}</div>
  }

  return (
    <div className="playlist-player-page">
      <header className="playlist-player-header">
        <button
          className="back-button"
          onClick={() => navigate('/playlist')}
          title={t('playlist.backToPlaylist', 'Back to playlist')}
          aria-label={t('playlist.backToPlaylist', 'Back to playlist')}
        >
          <FontAwesomeIcon icon={faArrowLeft} />
        </button>
        <h2 className="player-title">{videoInfo?.title || videoInfo?.url || t('player.title')}</h2>
        <div className="player-actions">
          <button
            className="nav-button"
            onClick={handlePrevious}
            disabled={!canPlayPrevious}
            title={t('player.previous')}
            aria-label={t('player.previous')}
          >
            <FontAwesomeIcon icon={faArrowLeft} />
          </button>
          <button
            className="nav-button"
            onClick={handleNext}
            disabled={!canPlayNext}
            title={t('player.next')}
            aria-label={t('player.next')}
          >
            <FontAwesomeIcon icon={faArrowRight} />
          </button>
          <button
            className="nav-button"
            onClick={() => void toggleFullscreen()}
            title={isFullscreen ? t('player.exitFullscreen') : t('player.fullscreen')}
            aria-label={isFullscreen ? t('player.exitFullscreen') : t('player.fullscreen')}
          >
            <FontAwesomeIcon icon={isFullscreen ? faCompress : faExpand} />
          </button>
          <button
            className="nav-button"
            onClick={togglePlaylistCollapsed}
            title={isPlaylistCollapsed ? t('playlist.showPlaylist', 'Show playlist') : t('playlist.hidePlaylist', 'Hide playlist')}
            aria-label={isPlaylistCollapsed ? t('playlist.showPlaylist', 'Show playlist') : t('playlist.hidePlaylist', 'Hide playlist')}
          >
            <FontAwesomeIcon icon={isPlaylistCollapsed ? faChevronLeft : faChevronRight} />
          </button>
        </div>
      </header>

      <div className="playlist-player-layout">
        <div className="playlist-player-left" ref={fullscreenTargetRef}>
          {loadingVideo ? (
            <div className="playlist-player-loading">{t('app.loading')}</div>
          ) : error || !videoInfo ? (
            <div className="error-message">{error || t('player.videoNotFound')}</div>
          ) : (
            <>
              <audio
                ref={audioRef}
                src={streamUrl}
                preload="auto"
                className="playlist-player-audio"
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
                onPlay={() => {
                  desiredPlayingRef.current = true
                  setPlaybackMode('audio')
                  setIsPlaying(true)
                }}
                onPause={() => {
                  if (playbackMode === 'audio') setIsPlaying(false)
                }}
                onEnded={() => {
                  setIsPlaying(false)
                  if (canPlayNext) handleNext()
                }}
              />
              <div className="video-container">
                <video
                  ref={videoRef}
                  src={streamUrl}
                  playsInline
                  crossOrigin="anonymous"
                  onTimeUpdate={handleTimeUpdate}
                  onLoadedMetadata={handleLoadedMetadata}
                  onPlay={() => {
                    desiredPlayingRef.current = true
                    setPlaybackMode('video')
                    setIsPlaying(true)
                  }}
                  onPause={() => {
                    if (playbackMode === 'video') setIsPlaying(false)
                  }}
                  onEnded={() => {
                    setIsPlaying(false)
                    if (canPlayNext) handleNext()
                  }}
                  className="video-element"
                />
              </div>

              <div className="player-controls">
                <button
                  className="play-pause-button"
                  onClick={handlePlayPause}
                  disabled={!isPlayableStatus(videoInfo.status)}
                  title={isPlaying ? t('player.pause') : t('player.play')}
                  aria-label={isPlaying ? t('player.pause') : t('player.play')}
                >
                  <FontAwesomeIcon icon={isPlaying ? faPause : faPlay} />
                </button>

                <div className="progress-container">
                  <input
                    type="range"
                    min="0"
                    max={duration || 0}
                    value={currentTime}
                    onChange={handleSeek}
                    className="progress-bar"
                    disabled={!isPlayableStatus(videoInfo.status)}
                    title={t('player.seek')}
                    aria-label={t('player.seek')}
                  />
                  <div className="time-display">
                    <span>{formatTime(currentTime)}</span>
                    <span>/</span>
                    <span>{formatTime(duration)}</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {!isPlaylistCollapsed && (
          <aside className="playlist-player-right" aria-label={t('playlist.playlist', 'Playlist')}>
            <div className="playlist-panel-header">
              <div className="playlist-panel-title">
                <FontAwesomeIcon icon={faList} />
                <span>{t('playlist.playlist', 'Playlist')}</span>
              </div>
              <div className="playlist-panel-count">{items.length}</div>
            </div>
            <div className="playlist-panel-list">
              {items.map((it) => {
                const active = vid !== null && it.video_record_id === vid
                const playable = isPlayableStatus(it.status)
                return (
                  <button
                    key={it.id}
                    type="button"
                    className={`playlist-panel-item ${active ? 'active' : ''}`}
                    onClick={() => goToVideo(it.video_record_id)}
                    disabled={!playable}
                    title={it.title || it.url}
                  >
                    <div className="playlist-panel-item-main">
                      <div className="playlist-panel-item-title">{it.title || it.url}</div>
                      <div className="playlist-panel-item-meta">
                        <span className={`status status-${it.status}`}>{it.status}</span>
                        <span className="playlist-panel-item-id">#{it.video_record_id}</span>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}

export default PlaylistPlayerPage

