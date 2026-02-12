import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { 
  faPlay, 
  faPause, 
  faArrowLeft,
  faArrowRight,
  faExpand,
  faCompress
} from '@fortawesome/free-solid-svg-icons'
import { videoApi, playlistApi, PlaylistItemResponse } from '../services/api'
import './VideoPlayer.css'

interface VideoPlayerProps {
  onLogout: () => void
}

const PLAYABLE_STATUSES = new Set(['converting', 'transcribing', 'summarizing', 'completed'])
const isPlayableStatus = (status?: string) => !!status && PLAYABLE_STATUSES.has(status)

const VideoPlayer: React.FC<VideoPlayerProps> = () => {
  const { t } = useTranslation()
  const { videoId } = useParams<{ videoId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const from = searchParams.get('from') || 'history'
  
  const videoRef = useRef<HTMLVideoElement>(null)
  const fullscreenTargetRef = useRef<HTMLDivElement>(null)
  const [videoInfo, setVideoInfo] = useState<any>(null)
  const [playlistItems, setPlaylistItems] = useState<PlaylistItemResponse[]>([])
  const [currentIndex, setCurrentIndex] = useState(-1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (videoId) {
      loadVideo(parseInt(videoId))
    }
  }, [videoId])

  useEffect(() => {
    if (from === 'playlist') {
      loadPlaylist()
    }
  }, [from])

  useEffect(() => {
    const update = () => {
      const target = fullscreenTargetRef.current
      setIsFullscreen(!!target && document.fullscreenElement === target)
    }
    update()
    document.addEventListener('fullscreenchange', update)
    // Safari legacy event (harmless elsewhere)
    document.addEventListener('webkitfullscreenchange' as any, update)
    return () => {
      document.removeEventListener('fullscreenchange', update)
      document.removeEventListener('webkitfullscreenchange' as any, update)
    }
  }, [])

  useEffect(() => {
    if (from === 'playlist' && playlistItems.length > 0 && videoId) {
      const index = playlistItems.findIndex(item => item.video_record_id === parseInt(videoId))
      setCurrentIndex(index)
    }
  }, [playlistItems, videoId, from])

  const loadVideo = async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      // Count as a "read" when opening the player
      const status = await videoApi.getStatus(id, { countRead: true })
      setVideoInfo(status)
      
      // Allow playback while processing (e.g. converting/transcribing/summarizing) as long as stream is available.
      if (!isPlayableStatus(status.status)) {
        setError(t('player.videoNotReady'))
      }
    } catch (err: any) {
      console.error('Failed to load video:', err)
      setError(err.response?.data?.detail || t('player.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const loadPlaylist = async () => {
    try {
      const items = await playlistApi.getPlaylistItems()
      setPlaylistItems(items)
    } catch (err) {
      console.error('Failed to load playlist:', err)
    }
  }

  const handlePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause()
      } else {
        videoRef.current.play()
      }
      setIsPlaying(!isPlaying)
    }
  }

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
    }
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value)
    if (videoRef.current) {
      videoRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const handlePrevious = () => {
    if (from === 'playlist' && currentIndex > 0) {
      const prevItem = playlistItems[currentIndex - 1]
      navigate(`/player/${prevItem.video_record_id}?from=playlist`)
    }
  }

  const handleNext = () => {
    if (from === 'playlist' && currentIndex >= 0 && currentIndex < playlistItems.length - 1) {
      const nextItem = playlistItems[currentIndex + 1]
      navigate(`/player/${nextItem.video_record_id}?from=playlist`)
    }
  }

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

    // iOS Safari fallback: use native video fullscreen if available
    const v: any = videoRef.current
    if (v && typeof v.webkitEnterFullscreen === 'function') {
      v.webkitEnterFullscreen()
    }
  }

  const formatTime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  // MediaSession API for background playback
  useEffect(() => {
    if ('mediaSession' in navigator && videoInfo) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: videoInfo.title || 'Video',
        artist: 'YouTube Watcher',
      })

      navigator.mediaSession.setActionHandler('play', () => {
        videoRef.current?.play()
        setIsPlaying(true)
      })

      navigator.mediaSession.setActionHandler('pause', () => {
        videoRef.current?.pause()
        setIsPlaying(false)
      })

      if (from === 'playlist') {
        navigator.mediaSession.setActionHandler('previoustrack', handlePrevious)
        navigator.mediaSession.setActionHandler('nexttrack', handleNext)
      }
    }
  }, [videoInfo, from])

  if (loading) {
    return <div className="video-player-page">{t('app.loading')}</div>
  }

  if (error || !videoInfo) {
    return (
      <div className="video-player-page">
        <div className="error-message">
          {error || t('player.videoNotFound')}
        </div>
        <button onClick={() => navigate(-1)}>{t('player.goBack')}</button>
      </div>
    )
  }

  const streamUrl = videoApi.getStreamUrl(parseInt(videoId!))
  const canPlayPrevious = from === 'playlist' && currentIndex > 0
  const canPlayNext = from === 'playlist' && currentIndex >= 0 && currentIndex < playlistItems.length - 1

  return (
    <div className="video-player-page">
      <header className="player-header">
        <button
          className="back-button"
          onClick={() => navigate(-1)}
          title={t('player.goBack')}
          aria-label={t('player.goBack')}
        >
          <FontAwesomeIcon icon={faArrowLeft} />
        </button>
        <h2 className="player-title">{videoInfo.title || 'Video'}</h2>
        <div className="player-actions">
          {from === 'playlist' && (
            <>
              <button
                className="nav-button"
                onClick={handlePrevious}
                disabled={!canPlayPrevious}
                title={t('player.previous')}
              >
                <FontAwesomeIcon icon={faArrowLeft} />
              </button>
              <button
                className="nav-button"
                onClick={handleNext}
                disabled={!canPlayNext}
                title={t('player.next')}
              >
                <FontAwesomeIcon icon={faArrowRight} />
              </button>
            </>
          )}
          <button
            className="nav-button"
            onClick={() => void toggleFullscreen()}
            title={isFullscreen ? t('player.exitFullscreen') : t('player.fullscreen')}
            aria-label={isFullscreen ? t('player.exitFullscreen') : t('player.fullscreen')}
          >
            <FontAwesomeIcon icon={isFullscreen ? faCompress : faExpand} />
          </button>
        </div>
      </header>

      <div className="player-container" ref={fullscreenTargetRef}>
        <div className="video-container">
          <video
            ref={videoRef}
            src={streamUrl}
            playsInline
            crossOrigin="anonymous"
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => {
              setIsPlaying(false)
              if (from === 'playlist' && canPlayNext) {
                handleNext()
              }
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
      </div>
    </div>
  )
}

export default VideoPlayer