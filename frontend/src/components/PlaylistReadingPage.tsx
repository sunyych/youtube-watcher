import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import Header from './Header'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowLeft, faArrowRight, faBookOpen, faCircleInfo } from '@fortawesome/free-solid-svg-icons'
import { historyApi, HistoryDetail, HistoryItem, playlistApi, PlaylistItemResponse } from '../services/api'
import './PlaylistReadingPage.css'

interface PlaylistReadingPageProps {
  onLogout: () => void
}

const toDateLabel = (iso?: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString()
}

const parseKeywords = (s?: string) =>
  (s || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)

const PlaylistReadingPage: React.FC<PlaylistReadingPageProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { playlistId } = useParams<{ playlistId: string }>()

  const pid = useMemo(() => {
    const n = Number(playlistId)
    return Number.isFinite(n) ? n : null
  }, [playlistId])

  const [items, setItems] = useState<PlaylistItemResponse[]>([])
  const [meta, setMeta] = useState<Map<number, HistoryItem>>(new Map())
  const [loading, setLoading] = useState(true)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<HistoryDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const [filterQuery, setFilterQuery] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)

  useEffect(() => {
    if (pid === null) return
    ;(async () => {
      setLoading(true)
      try {
        const pls = await playlistApi.getPlaylistItems(pid)
        setItems(pls)

        const ids = pls.map((p) => p.video_record_id)
        const history = ids.length ? await historyApi.getBatch(ids) : []
        const m = new Map<number, HistoryItem>()
        for (const it of history) m.set(it.id, it)
        setMeta(m)

        if (!selectedId && ids.length) {
          setSelectedId(ids[0])
        }
      } catch (e) {
        console.error('Failed to load reading list:', e)
      } finally {
        setLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid])

  // Sort by video publish date DESC (newest first); fallback to created_at
  const orderedIds = useMemo(() => {
    const withMeta = items.map((item) => ({
      id: item.video_record_id,
      meta: meta.get(item.video_record_id),
    }))
    const sorted = [...withMeta].sort((a, b) => {
      const dateA = a.meta?.upload_date || a.meta?.created_at || ''
      const dateB = b.meta?.upload_date || b.meta?.created_at || ''
      return dateB.localeCompare(dateA)
    })
    return sorted.map((x) => x.id)
  }, [items, meta])

  const filteredOrderedIds = useMemo(() => {
    const q = filterQuery.trim().toLowerCase()
    return orderedIds.filter((id) => {
      const m = meta.get(id)
      if (unreadOnly && (m?.read_count ?? 0) > 0) return false
      if (!q) return true
      const title = (m?.title || '').toLowerCase()
      const kw = (m?.keywords || '').toLowerCase()
      return title.includes(q) || kw.includes(q)
    })
  }, [orderedIds, meta, filterQuery, unreadOnly])

  const selectedIndex = useMemo(() => (selectedId ? filteredOrderedIds.indexOf(selectedId) : -1), [filteredOrderedIds, selectedId])
  const canPrev = selectedIndex > 0
  const canNext = selectedIndex >= 0 && selectedIndex < filteredOrderedIds.length - 1

  useEffect(() => {
    if (filteredOrderedIds.length === 0) return
    if (selectedId !== null && !filteredOrderedIds.includes(selectedId)) {
      setSelectedId(filteredOrderedIds[0])
    }
  }, [filteredOrderedIds, selectedId])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    ;(async () => {
      setLoadingDetail(true)
      try {
        // Opening a reading page counts as "read"
        const d = await historyApi.getDetail(selectedId, { countRead: true })
        setDetail(d)
        // Sync meta read_count if present
        setMeta((prev) => {
          const next = new Map(prev)
          const cur = next.get(d.id)
          if (cur) next.set(d.id, { ...cur, read_count: d.read_count })
          return next
        })
      } catch (e) {
        console.error('Failed to load reading detail:', e)
        setDetail(null)
      } finally {
        setLoadingDetail(false)
      }
    })()
  }, [selectedId])

  const keywords = useMemo(() => parseKeywords(detail?.keywords || meta.get(selectedId || -1)?.keywords), [detail, meta, selectedId])

  const goPrev = () => {
    if (!canPrev) return
    setSelectedId(filteredOrderedIds[selectedIndex - 1])
  }

  const goNext = () => {
    if (!canNext) return
    setSelectedId(filteredOrderedIds[selectedIndex + 1])
  }

  if (pid === null) {
    return <div className="playlist-reading-page">{t('playlist.reading.title', 'Reading')}</div>
  }

  return (
    <div className="playlist-reading-page page-with-header">
      <Header title={t('playlist.reading.title', 'Reading')} onLogout={onLogout} />

      {loading ? (
        <div className="playlist-reading-loading">{t('app.loading')}</div>
      ) : (
        <div className="playlist-reading-layout">
          <aside className="reading-sidebar" aria-label={t('playlist.reading.list', 'Reading list')}>
            <div className="reading-sidebar-header">
              <button
                className="reading-back"
                onClick={() => navigate('/playlist')}
                title={t('playlist.backToPlaylist', 'Back to playlist')}
                aria-label={t('playlist.backToPlaylist', 'Back to playlist')}
              >
                <FontAwesomeIcon icon={faBookOpen} />
              </button>
              <div className="reading-sidebar-title">{t('playlist.reading.list', 'Reading list')}</div>
              <div className="reading-sidebar-count">
                {filteredOrderedIds.length}{filterQuery || unreadOnly ? ` / ${orderedIds.length}` : ''}
              </div>
            </div>

            <div className="reading-sidebar-filter">
              <input
                type="text"
                className="reading-filter-input"
                placeholder={t('playlist.reading.filterPlaceholder', '筛选标题/关键词...')}
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                aria-label={t('playlist.reading.filterPlaceholder', '筛选标题/关键词...')}
              />
              <label className="reading-filter-unread">
                <input
                  type="checkbox"
                  checked={unreadOnly}
                  onChange={(e) => setUnreadOnly(e.target.checked)}
                  aria-label={t('playlist.reading.unreadOnly', '仅未读')}
                />
                <span>{t('playlist.reading.unreadOnly', '仅未读')}</span>
              </label>
            </div>

            <div className="reading-list">
              {filteredOrderedIds.length === 0 ? (
                <div className="reading-empty">
                  {orderedIds.length === 0 ? t('playlist.emptyState') : t('playlist.reading.noFilterMatch', '无匹配项')}
                </div>
              ) : (
                filteredOrderedIds.map((id) => {
                  const m = meta.get(id)
                  const title = m?.title || items.find((x) => x.video_record_id === id)?.title || String(id)
                  const date = toDateLabel(m?.upload_date || m?.created_at)
                  const active = id === selectedId
                  return (
                    <button
                      key={id}
                      type="button"
                      className={`reading-item ${active ? 'active' : ''}`}
                      onClick={() => setSelectedId(id)}
                      title={title}
                    >
                      <div className="reading-item-title">{title}</div>
                      <div className="reading-item-meta">
                        <span className="reading-item-date">{date}</span>
                        {typeof m?.read_count === 'number' && <span className="reading-item-read">👁 {m.read_count}</span>}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </aside>

          <main className="reading-main">
            <div className="reading-top">
              <div className="reading-keywords">
                {keywords.length ? (
                  keywords.map((k) => (
                    <span key={k} className="keyword-chip">
                      {k}
                    </span>
                  ))
                ) : (
                  <span className="keyword-empty">{t('playlist.reading.noKeywords', 'No keywords')}</span>
                )}
              </div>

              <div className="reading-actions">
                <button className="nav-btn" onClick={goPrev} disabled={!canPrev} title={t('player.previous')}>
                  <FontAwesomeIcon icon={faArrowLeft} />
                </button>
                <button className="nav-btn" onClick={goNext} disabled={!canNext} title={t('player.next')}>
                  <FontAwesomeIcon icon={faArrowRight} />
                </button>
                <button
                  className="detail-btn"
                  onClick={() => setShowDetailModal(true)}
                  disabled={!detail}
                  title={t('playlist.reading.openDetail', 'Open detail')}
                >
                  <FontAwesomeIcon icon={faCircleInfo} />
                </button>
              </div>
            </div>

            <div className="reading-content">
              {loadingDetail ? (
                <div className="reading-loading-detail">{t('app.loading')}</div>
              ) : !detail ? (
                <div className="reading-empty-detail">{t('history.item.loadDetailFailed')}</div>
              ) : (
                <>
                  <h2 className="reading-title">{detail.title || detail.url}</h2>
                  <div className="reading-summary markdown-content">
                    <ReactMarkdown
                      components={{
                        code({ node, inline, className, children, ...props }: { node?: unknown; inline?: boolean; className?: string; children?: React.ReactNode }) {
                          const match = /language-(\w+)/.exec(className || '')
                          return !inline && match ? (
                            <SyntaxHighlighter
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              {...props}
                            >
                              {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                          ) : (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          )
                        }
                      }}
                    >
                      {detail.summary || t('playlist.reading.noSummary', 'No summary')}
                    </ReactMarkdown>
                  </div>
                </>
              )}
            </div>
          </main>
        </div>
      )}

      {showDetailModal && detail && (
        <div className="reading-modal-overlay" onClick={() => setShowDetailModal(false)} role="presentation">
          <div className="reading-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="reading-modal-header">
              <div className="reading-modal-title">{detail.title || detail.url}</div>
              <button className="reading-modal-close" onClick={() => setShowDetailModal(false)}>
                ×
              </button>
            </div>
            <div className="reading-modal-body">
              <div className="reading-modal-section">
                <div className="reading-modal-label">URL</div>
                <a href={detail.url} target="_blank" rel="noreferrer">
                  {detail.url}
                </a>
              </div>
              <div className="reading-modal-section">
                <div className="reading-modal-label">{t('history.item.transcript', 'Transcript')}</div>
                <pre className="reading-modal-pre">{detail.transcript || ''}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PlaylistReadingPage

