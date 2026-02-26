import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Header from './Header'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { 
  faExternalLinkAlt, 
  faDownload, 
  faRedo, 
  faTrash, 
  faPlay,
  faPlus,
  faChevronLeft,
  faChevronRight
} from '@fortawesome/free-solid-svg-icons'
import { historyApi, videoApi, HistoryItem, HistoryDetail, playlistApi } from '../services/api'
import { useNavigate } from 'react-router-dom'
import LanguageSelector from './LanguageSelector'
import './HistoryPage.css'

interface HistoryPageProps {
  onLogout: () => void
}

const HistoryPage: React.FC<HistoryPageProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  type HistoryTab = 'noSummary' | 'withSummary' | 'fromSubscription'
  type HistoryDisplayMode = 'compact' | 'standard'
  type HistorySort = 'dateDesc' | 'dateAsc' | 'readDesc' | 'titleAsc'

  const HISTORY_SORT_KEY = 'history_sort_v1'
  const HISTORY_UNREAD_ONLY_KEY = 'history_unread_only_v1'

  const [history, setHistory] = useState<HistoryItem[]>([])
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<HistoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState<number | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editTranscript, setEditTranscript] = useState('')
  const [saving, setSaving] = useState<number | null>(null)
  const [generatingKeywords, setGeneratingKeywords] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [reprocessingId, setReprocessingId] = useState<number | null>(null)
  const [reprocessDialogOpen, setReprocessDialogOpen] = useState<number | null>(null)
  const [reprocessLanguage, setReprocessLanguage] = useState<string>('')
  const [addingToPlaylist, setAddingToPlaylist] = useState<number | null>(null)
  const [restartingTranscribe, setRestartingTranscribe] = useState<number | null>(null)
  const [restartingSummary, setRestartingSummary] = useState<number | null>(null)
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(12)
  const [totalCount, setTotalCount] = useState(0)
  // Default to showing items WITH summary
  const [activeTab, setActiveTab] = useState<HistoryTab>('withSummary')
  const [displayMode, setDisplayMode] = useState<HistoryDisplayMode>(() => {
    if (typeof window === 'undefined') return 'standard'
    const saved = localStorage.getItem('history_display_mode') as HistoryDisplayMode | null
    if (saved === 'compact' || saved === 'standard') return saved
    // Default to compact on small screens (better for mobile reading)
    return window.innerWidth <= 768 ? 'compact' : 'standard'
  })
  const [sortBy, setSortBy] = useState<HistorySort>(() => {
    if (typeof window === 'undefined') return 'dateDesc'
    const saved = localStorage.getItem(HISTORY_SORT_KEY) as HistorySort | null
    if (saved === 'dateDesc' || saved === 'dateAsc' || saved === 'readDesc' || saved === 'titleAsc') return saved
    return 'dateDesc'
  })
  const [unreadOnly, setUnreadOnly] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    const saved = localStorage.getItem(HISTORY_UNREAD_ONLY_KEY)
    if (saved === '1') return true
    if (saved === '0') return false
    return false
  })

  useEffect(() => {
    if (!searchQuery.trim()) {
      loadHistory()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, activeTab])

  const loadHistory = async (page?: number) => {
    setLoading(true)
    try {
      const pageToUse = page !== undefined ? page : currentPage
      const skip = (pageToUse - 1) * pageSize
      const hasSummary = activeTab === 'fromSubscription' ? undefined : activeTab === 'withSummary'
      const source = activeTab === 'fromSubscription' ? 'subscription' : undefined
      const [data, count] = await Promise.all([
        historyApi.getHistory(skip, pageSize, hasSummary, source),
        historyApi.getHistoryCount(hasSummary, source)
      ])
      setHistory(data)
      setTotalCount(count)
      if (page !== undefined) {
        setCurrentPage(page)
      }
      setSearchQuery('') // Clear search when loading history
    } catch (err) {
      console.error('Failed to load history:', err)
      alert(t('history.item.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async (page: number = 1) => {
    if (!searchQuery.trim()) {
      setCurrentPage(1)
      loadHistory()
      setIsSearching(false)
      return
    }

    setIsSearching(true)
    try {
      const skip = (page - 1) * pageSize
      const hasSummary = activeTab === 'fromSubscription' ? undefined : activeTab === 'withSummary'
      const source = activeTab === 'fromSubscription' ? 'subscription' : undefined
      const [data, count] = await Promise.all([
        historyApi.searchHistory(searchQuery.trim(), skip, pageSize, hasSummary, source),
        historyApi.searchHistoryCount(searchQuery.trim(), hasSummary, source)
      ])
      setHistory(data)
      setTotalCount(count)
      setCurrentPage(page)
    } catch (err) {
      console.error('Failed to search:', err)
      alert(t('history.item.searchFailed'))
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearchKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch(1)
    }
  }

  const handlePageChange = (page: number) => {
    setCurrentPage(page)
    if (searchQuery.trim()) {
      handleSearch(page)
    }
    // Scroll to top when page changes
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleTabChange = (tab: HistoryTab) => {
    if (tab === activeTab) return
    setActiveTab(tab)
    setCurrentPage(1)
    setSearchQuery('')
  }

  const handleDisplayModeChange = (mode: HistoryDisplayMode) => {
    setDisplayMode(mode)
    try {
      localStorage.setItem('history_display_mode', mode)
    } catch {
      // ignore storage errors
    }
  }

  const totalPages = Math.ceil(totalCount / pageSize)

  const closeDetailModal = () => {
    setExpandedId(null)
    setExpandedDetail(null)
    setEditingId(null)
  }

  const getReadCount = (item: Pick<HistoryItem, 'read_count'> | null | undefined) => item?.read_count ?? 0

  const handleSortChange = (next: HistorySort) => {
    setSortBy(next)
    try {
      localStorage.setItem(HISTORY_SORT_KEY, next)
    } catch {
      // ignore storage errors
    }
  }

  const handleUnreadOnlyChange = (next: boolean) => {
    setUnreadOnly(next)
    try {
      localStorage.setItem(HISTORY_UNREAD_ONLY_KEY, next ? '1' : '0')
    } catch {
      // ignore storage errors
    }
  }

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      closeDetailModal()
      return
    }

    try {
      // Count as a "read" when opening the detail/summary view
      const detail = await historyApi.getDetail(id, { countRead: true })
      setExpandedId(id)
      setExpandedDetail(detail)
      setEditTranscript(detail.transcript || '')
      setEditingId(null)
      // Sync list read_count with the updated detail response
      setHistory((prev) => prev.map((it) => (it.id === id ? { ...it, read_count: detail.read_count } : it)))
    } catch (err) {
      console.error('Failed to load detail:', err)
      alert(t('history.item.loadDetailFailed'))
    }
  }

  const handleEdit = (id: number) => {
    if (expandedDetail && expandedId === id) {
      setEditingId(id)
      setEditTranscript(expandedDetail.transcript || '')
      // Don't edit keywords anymore, only edit transcript/markdown content
    }
  }

  const handleCancelEdit = () => {
    if (expandedDetail) {
      setEditTranscript(expandedDetail.transcript || '')
    }
    setEditingId(null)
  }

  const handleSave = async (id: number) => {
    setSaving(id)
    try {
      // Only save transcript (markdown content), not keywords
      const updated = await historyApi.updateHistory(id, {
        transcript: editTranscript,
      })
      setExpandedDetail(updated)
      setEditingId(null)
      // Reload history to refresh the list
      await loadHistory()
      alert(t('history.item.saveSuccess'))
    } catch (err) {
      console.error('Failed to save:', err)
      alert(t('history.item.saveFailed'))
    } finally {
      setSaving(null)
    }
  }

  const handleGenerateKeywords = async (id: number) => {
    setGeneratingKeywords(id)
    try {
      const updated = await historyApi.generateKeywords(id)
      setExpandedDetail(updated)
      await loadHistory()
      alert(t('history.item.generateKeywordsSuccess'))
    } catch (err: any) {
      console.error('Failed to generate keywords:', err)
      alert(err.response?.data?.detail || t('history.item.generateKeywordsFailed'))
    } finally {
      setGeneratingKeywords(null)
    }
  }

  const handleExport = async (id: number, title?: string) => {
    setExporting(id)
    try {
      const blob = await historyApi.exportMarkdown(id, false)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const filename = title
        ? `${title.replace(/[^a-z0-9]/gi, '_')}_${id}.md`
        : `video_${id}.md`
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to export:', err)
      alert(t('history.item.exportFailed'))
    } finally {
      setExporting(null)
    }
  }

  const handleRetry = async (id: number) => {
    setRetrying(id)
    try {
      await videoApi.retry(id)
      // Reload history to show updated status
      if (searchQuery.trim()) {
        await handleSearch(currentPage)
      } else {
        await loadHistory()
      }
    } catch (err: any) {
      console.error('Failed to retry:', err)
      alert(err.response?.data?.detail || t('history.item.retryFailed'))
    } finally {
      setRetrying(null)
    }
  }

  const handleRestartTranscribe = async (id: number) => {
    setRestartingTranscribe(id)
    try {
      await videoApi.bulkRestartTranscribe([id])
      const updated = await historyApi.getDetail(id)
      setExpandedDetail(updated)
      if (searchQuery.trim()) {
        await handleSearch(currentPage)
      } else {
        await loadHistory()
      }
    } catch (err: any) {
      console.error('Failed to restart transcribe:', err)
      alert(err.response?.data?.detail || t('history.item.restartTranscribeFailed'))
    } finally {
      setRestartingTranscribe(null)
    }
  }

  const handleRestartSummary = async (id: number) => {
    setRestartingSummary(id)
    try {
      await videoApi.bulkRestartSummary([id])
      const updated = await historyApi.getDetail(id)
      setExpandedDetail(updated)
      if (searchQuery.trim()) {
        await handleSearch(currentPage)
      } else {
        await loadHistory()
      }
    } catch (err: any) {
      console.error('Failed to restart summary:', err)
      alert(err.response?.data?.detail || t('history.item.restartSummaryFailed'))
    } finally {
      setRestartingSummary(null)
    }
  }

  const handleDelete = async (id: number, title?: string) => {
    const confirmMessage = title 
      ? t('history.item.deleteConfirm', { title })
      : t('history.item.deleteConfirmNoTitle')
    
    if (!window.confirm(confirmMessage)) {
      return
    }
    
    setDeleting(id)
    try {
      await historyApi.deleteHistory(id)
      // If the deleted item was expanded, close it
      if (expandedId === id) {
        setExpandedId(null)
        setExpandedDetail(null)
        setEditingId(null)
      }
      // Reload history to remove the deleted item
      // If we're on a page that might become empty, adjust page number
      const newTotalCount = totalCount - 1
      const newTotalPages = Math.ceil(newTotalCount / pageSize)
      if (currentPage > newTotalPages && newTotalPages > 0) {
        // If current page would be beyond total pages, go to last page
        await loadHistory(newTotalPages)
      } else if (searchQuery.trim()) {
        // If searching, reload search results
        await handleSearch(currentPage)
      } else {
        await loadHistory()
      }
      alert(t('history.item.deleteSuccess'))
    } catch (err: any) {
      console.error('Failed to delete:', err)
      alert(err.response?.data?.detail || t('history.item.deleteFailed'))
    } finally {
      setDeleting(null)
    }
  }

  const handleReprocess = async (id: number, url: string) => {
    setReprocessingId(id)
    try {
      await videoApi.process(url, reprocessLanguage || undefined)
      setReprocessDialogOpen(null)
      setReprocessLanguage('')
      // Reload history to show updated status
      if (searchQuery.trim()) {
        await handleSearch(currentPage)
      } else {
        await loadHistory()
      }
      alert(t('history.item.reprocessSuccess'))
    } catch (err: any) {
      console.error('Failed to reprocess:', err)
      alert(err.response?.data?.detail || t('history.item.reprocessFailed'))
    } finally {
      setReprocessingId(null)
    }
  }

  const closeReprocessDialog = () => {
    setReprocessDialogOpen(null)
    setReprocessLanguage('')
  }

  const handlePlay = (id: number) => {
    navigate(`/player/${id}?from=history`)
  }

  const handleAddToPlaylist = async (id: number) => {
    setAddingToPlaylist(id)
    try {
      await playlistApi.addItem(id)
      alert(t('history.item.addedToPlaylist'))
    } catch (err: any) {
      console.error('Failed to add to playlist:', err)
      alert(err.response?.data?.detail || t('history.item.addToPlaylistFailed'))
    } finally {
      setAddingToPlaylist(null)
    }
  }

  const formatUploadDate = (dateString?: string) => {
    if (!dateString) return null
    const date = new Date(dateString)
    const language = localStorage.getItem('language') || 'en'
    return date.toLocaleDateString(language === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  const formatDisplayDate = (item: HistoryItem) => {
    return formatUploadDate(item.upload_date) || formatUploadDate(item.created_at) || null
  }

  const getSortDateMs = (item: HistoryItem) => {
    const raw = item.upload_date || item.created_at
    const ms = new Date(raw).getTime()
    return Number.isFinite(ms) ? ms : 0
  }

  const sortedHistory = useMemo(() => {
    const items = [...history]
    items.sort((a, b) => {
      if (sortBy === 'dateDesc') {
        const diff = getSortDateMs(b) - getSortDateMs(a)
        if (diff !== 0) return diff
        return b.id - a.id
      }
      if (sortBy === 'dateAsc') {
        const diff = getSortDateMs(a) - getSortDateMs(b)
        if (diff !== 0) return diff
        return a.id - b.id
      }
      if (sortBy === 'readDesc') {
        const diff = getReadCount(b) - getReadCount(a)
        if (diff !== 0) return diff
        // tie-breaker by date desc
        const dateDiff = getSortDateMs(b) - getSortDateMs(a)
        if (dateDiff !== 0) return dateDiff
        return b.id - a.id
      }
      // titleAsc
      const at = (a.title || a.url || '').toLowerCase()
      const bt = (b.title || b.url || '').toLowerCase()
      if (at < bt) return -1
      if (at > bt) return 1
      return a.id - b.id
    })
    return items
  }, [history, sortBy])

  const visibleHistory = useMemo(() => {
    if (!unreadOnly) return sortedHistory
    // When unreadOnly is enabled, keep the currently opened item visible in the modal
    // even after we increment its read_count, so navigation remains stable.
    return sortedHistory.filter((it) => {
      if (expandedId !== null && it.id === expandedId) return true
      return getReadCount(it) === 0
    })
  }, [sortedHistory, unreadOnly, expandedId])

  const currentVisibleIndex = useMemo(() => {
    if (expandedId === null) return -1
    return visibleHistory.findIndex((it) => it.id === expandedId)
  }, [visibleHistory, expandedId])

  const prevVisibleId = currentVisibleIndex > 0 ? visibleHistory[currentVisibleIndex - 1]?.id : null
  const nextVisibleId =
    currentVisibleIndex >= 0 && currentVisibleIndex < visibleHistory.length - 1
      ? visibleHistory[currentVisibleIndex + 1]?.id
      : null

  const parseKeywords = (keywords?: string): string[] => {
    if (!keywords) return []
    return keywords.split(',').map(k => k.trim()).filter(k => k.length > 0)
  }

  // Format plain text for better markdown rendering
  const formatTextForMarkdown = (text: string): string => {
    if (!text) return ''
    
    // If text already has markdown formatting (headers, lists, etc.), return as is
    if (text.includes('\n#') || text.includes('\n##') || text.includes('\n###') || 
        text.includes('\n-') || text.includes('\n*') || text.includes('\n1.') ||
        text.match(/\n#{1,6}\s/)) {
      return text
    }
    
    let formatted = text
    
    // Try to detect and format common patterns
    
    // 1. Detect numbered sections (一、二、三、1. 2. etc.)
    formatted = formatted.replace(/([一二三四五六七八九十]+[、\.])\s*([^\n]+)/g, '\n\n### $1 $2\n\n')
    formatted = formatted.replace(/(\d+[、\.])\s*([^\n]+)/g, '\n\n#### $1 $2\n\n')
    
    // 2. Detect list items (•、-、*、数字.)
    formatted = formatted.replace(/([•\-*]|\d+\.)\s+([^\n]+)/g, '\n- $2')
    
    // 3. Add line breaks after sentence endings, but preserve structure
    // First, protect existing patterns
    const protectedPatterns: string[] = []
    let patternIndex = 0
    
    formatted = formatted.replace(/(###?[^\n]+\n)/g, (match) => {
      protectedPatterns.push(match)
      return `__PROTECTED_${patternIndex++}__`
    })
    
    // Add paragraph breaks after sentence endings
    formatted = formatted.replace(/([。！？])\s*([^。！？\n])/g, '$1\n\n$2')
    formatted = formatted.replace(/([.!?])\s+([A-Z])/g, '$1\n\n$2')
    
    // Restore protected patterns
    protectedPatterns.forEach((pattern, idx) => {
      formatted = formatted.replace(`__PROTECTED_${idx}__`, pattern)
    })
    
    // 4. Clean up excessive line breaks
    formatted = formatted.replace(/\n{4,}/g, '\n\n\n')
    formatted = formatted.replace(/\n{3,}/g, '\n\n')
    
    // 5. Trim each line but preserve structure
    formatted = formatted.split('\n').map((line, index, array) => {
      const trimmed = line.trim()
      // Don't add extra breaks before headers
      if (trimmed.match(/^#{1,6}\s/)) {
        return trimmed
      }
      // Don't add breaks before list items if previous line is also a list item
      if (trimmed.match(/^[-*•]\s/) && index > 0 && array[index - 1].trim().match(/^[-*•]\s/)) {
        return trimmed
      }
      return trimmed
    }).join('\n')
    
    // 6. Ensure proper spacing around headers
    formatted = formatted.replace(/(\n)(#{1,6}\s[^\n]+)(\n)([^\n#])/g, '$1$2$3\n$4')
    
    return formatted.trim()
  }

  const renderHistoryItemCompact = (item: HistoryItem) => (
    <button
      key={item.id}
      type="button"
      className="history-row"
      onClick={() => handleExpand(item.id)}
      title={item.title || item.url}
    >
      <div className="history-row-title">
        {item.title || item.url}
      </div>
      <div className="history-row-meta">
        {formatDisplayDate(item) && (
          <span className="history-row-date">{formatDisplayDate(item)}</span>
        )}
        <span className="read-count-badge" title={t('history.item.readCountTitle')}>
          {t('history.item.readCount', { count: getReadCount(item) })}
        </span>
      </div>
      {item.keywords && (
        <div className="history-row-tags">
          {parseKeywords(item.keywords).slice(0, 5).map((keyword, idx) => (
            <span key={idx} className="keyword-tag-small">{keyword}</span>
          ))}
          {parseKeywords(item.keywords).length > 5 && (
            <span className="keyword-more">+{parseKeywords(item.keywords).length - 5}</span>
          )}
        </div>
      )}
    </button>
  )

  const renderHistoryItemStandard = (item: HistoryItem) => (
    <div key={item.id} className="history-card">
      <button
        type="button"
        className="history-card-open"
        onClick={() => handleExpand(item.id)}
        title={item.title || item.url}
      >
        <div className="history-card-content">
          <h3 className="history-card-title">
            {item.title || item.url}
          </h3>
          <div className="history-card-meta">
            {formatDisplayDate(item) && (
              <span className="history-card-date">{formatDisplayDate(item)}</span>
            )}
            <span className="read-count-badge" title={t('history.item.readCountTitle')}>
              {t('history.item.readCount', { count: getReadCount(item) })}
            </span>
            {item.language && (
              <span className="history-card-language">{item.language}</span>
            )}
            <span className={`status-badge-inline status-${item.status}`}>
              {item.status}
            </span>
          </div>
          {expandedId !== item.id && item.keywords && (
            <div className="history-card-keywords">
              {parseKeywords(item.keywords).slice(0, 3).map((keyword, idx) => (
                <span key={idx} className="keyword-tag-small">{keyword}</span>
              ))}
              {parseKeywords(item.keywords).length > 3 && (
                <span className="keyword-more">+{parseKeywords(item.keywords).length - 3}</span>
              )}
            </div>
          )}
        </div>
      </button>

      <div className="history-card-actions">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="tile-action-button"
          title={item.url}
        >
          <FontAwesomeIcon icon={faExternalLinkAlt} />
        </a>
          {item.status === 'failed' && (
            <button
              className="tile-action-button"
              onClick={() => handleRetry(item.id)}
              disabled={retrying === item.id}
              title={retrying === item.id ? t('history.item.retrying') : t('history.item.retry')}
            >
              <FontAwesomeIcon icon={faRedo} spin={retrying === item.id} />
            </button>
          )}
          {item.status === 'completed' && (
            <>
              <button
                className="tile-action-button"
                onClick={() => handlePlay(item.id)}
                title={t('history.item.play')}
              >
                <FontAwesomeIcon icon={faPlay} />
              </button>
              <button
                className="tile-action-button"
                onClick={() => handleAddToPlaylist(item.id)}
                disabled={addingToPlaylist === item.id}
                title={addingToPlaylist === item.id ? t('history.item.addingToPlaylist') : t('history.item.addToPlaylist')}
              >
                <FontAwesomeIcon icon={faPlus} spin={addingToPlaylist === item.id} />
              </button>
              <button
                className="tile-action-button"
                onClick={() => handleExport(item.id, item.title)}
                disabled={exporting === item.id}
                title={exporting === item.id ? t('history.item.exporting') : t('history.item.export')}
              >
                <FontAwesomeIcon icon={faDownload} spin={exporting === item.id} />
              </button>
            </>
          )}
          <button
            className="tile-action-button"
            onClick={() => handleDelete(item.id, item.title)}
            disabled={deleting === item.id}
            title={t('history.item.deleteTitle')}
          >
            <FontAwesomeIcon icon={faTrash} />
          </button>
      </div>
    </div>
  )

  const renderHistoryItem = (item: HistoryItem) => {
    if (displayMode === 'compact') return renderHistoryItemCompact(item)
    return renderHistoryItemStandard(item)
  }


  if (loading) {
    return <div className="history-page">{t('app.loading')}</div>
  }

  return (
    <div className="history-page page-with-header">
      <Header title={t('history.title')} onLogout={onLogout} />

      <div className="history-content">
        {/* Search Bar */}
        <div className="search-bar">
          <input
            type="text"
            placeholder={t('history.search.placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={handleSearchKeyPress}
            className="search-input"
          />
          <button onClick={() => handleSearch(1)} disabled={isSearching} className="search-button">
            {isSearching ? t('history.search.searching') : t('history.search.button')}
          </button>
          {searchQuery && (
            <button onClick={() => { 
              setSearchQuery('')
              setCurrentPage(1)
              loadHistory()
              setIsSearching(false)
            }} className="clear-button">
              {t('history.search.clear')}
            </button>
          )}
        </div>

        <div className="history-tabs">
          <div className="history-toolbar">
            <div className="tabs-list">
              <button
                className={`tabs-trigger ${activeTab === 'withSummary' ? 'tabs-trigger-active' : ''}`}
                onClick={() => handleTabChange('withSummary')}
                type="button"
              >
                {t('history.tabs.withSummary')}
              </button>
              <button
                className={`tabs-trigger ${activeTab === 'noSummary' ? 'tabs-trigger-active' : ''}`}
                onClick={() => handleTabChange('noSummary')}
                type="button"
              >
                {t('history.tabs.noTranscript')}
              </button>
              <button
                className={`tabs-trigger ${activeTab === 'fromSubscription' ? 'tabs-trigger-active' : ''}`}
                onClick={() => handleTabChange('fromSubscription')}
                type="button"
              >
                {t('history.tabs.fromSubscription')}
              </button>
            </div>

              <div className="sort-control">
                <span className="sort-control-label">{t('history.sort.label')}</span>
                <select
                  className="sort-select"
                  value={sortBy}
                  onChange={(e) => handleSortChange(e.target.value as HistorySort)}
                  aria-label={t('history.sort.label')}
                  title={t('history.sort.label')}
                >
                  <option value="dateDesc">{t('history.sort.dateDesc')}</option>
                  <option value="dateAsc">{t('history.sort.dateAsc')}</option>
                  <option value="readDesc">{t('history.sort.readDesc')}</option>
                  <option value="titleAsc">{t('history.sort.titleAsc')}</option>
                </select>
              </div>

            <label className="filter-control" title={t('history.filter.unreadOnly')}>
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={(e) => handleUnreadOnlyChange(e.target.checked)}
                className="filter-checkbox"
              />
              <span className="filter-control-label">{t('history.filter.unreadOnly')}</span>
            </label>

            <div className="view-toggle">
              <span className="view-toggle-label">{t('history.view.label')}</span>
              <div className="view-toggle-buttons">
                <button
                  type="button"
                  className={`view-toggle-button ${displayMode === 'compact' ? 'view-toggle-button-active' : ''}`}
                  onClick={() => handleDisplayModeChange('compact')}
                >
                  {t('history.view.compact')}
                </button>
                <button
                  type="button"
                  className={`view-toggle-button ${displayMode === 'standard' ? 'view-toggle-button-active' : ''}`}
                  onClick={() => handleDisplayModeChange('standard')}
                >
                  {t('history.view.standard')}
                </button>
              </div>
            </div>
          </div>
          <div className="history-tab-panel">
            {history.length === 0 ? (
              <div className="empty-state-tab">
                {searchQuery ? t('history.emptyState.noResults') : t('history.emptyState.noHistory')}
              </div>
            ) : (
              <div className={`history-list ${displayMode === 'compact' ? 'history-list-compact' : ''}`}>
                {visibleHistory.map(renderHistoryItem)}
              </div>
            )}
          </div>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="pagination-button"
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1 || loading || isSearching}
            >
              {t('history.pagination.previous')}
            </button>
            <div className="pagination-info">
              {t('history.pagination.pageInfo', {
                current: currentPage,
                total: totalPages,
                count: totalCount
              })}
            </div>
            <button
              className="pagination-button"
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages || loading || isSearching}
            >
              {t('history.pagination.next')}
            </button>
          </div>
        )}
      </div>

      {/* Reprocess Dialog */}
      {/* Detail Modal */}
      {expandedId !== null && expandedDetail && (
        <div className="modal-overlay modal-overlay-below-header" onClick={closeDetailModal}>
          <div className="modal-content modal-fullscreen" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title-ellipsis">{expandedDetail.title || expandedDetail.url}</h3>
              <span className="read-count-badge" title={t('history.item.readCountTitle')}>
                {t('history.item.readCount', { count: getReadCount(expandedDetail) })}
              </span>
              <div className="modal-actions">
                <button
                  type="button"
                  className="modal-action-button"
                  onClick={() => prevVisibleId !== null && handleExpand(prevVisibleId)}
                  disabled={prevVisibleId === null}
                  title={t('history.item.previous')}
                >
                  <FontAwesomeIcon icon={faChevronLeft} />
                </button>
                <button
                  type="button"
                  className="modal-action-button"
                  onClick={() => nextVisibleId !== null && handleExpand(nextVisibleId)}
                  disabled={nextVisibleId === null}
                  title={t('history.item.next')}
                >
                  <FontAwesomeIcon icon={faChevronRight} />
                </button>
                <a
                  href={expandedDetail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="modal-action-button"
                  title={expandedDetail.url}
                >
                  <FontAwesomeIcon icon={faExternalLinkAlt} />
                </a>
                {expandedDetail.status === 'failed' && (
                  <button
                    className="modal-action-button"
                    onClick={() => handleRetry(expandedId)}
                    disabled={retrying === expandedId}
                    title={retrying === expandedId ? t('history.item.retrying') : t('history.item.retry')}
                  >
                    <FontAwesomeIcon icon={faRedo} spin={retrying === expandedId} />
                  </button>
                )}
                {expandedDetail.status === 'completed' && (
                  <>
                    <button
                      className="modal-action-button"
                      onClick={() => handlePlay(expandedId)}
                      title={t('history.item.play')}
                    >
                      <FontAwesomeIcon icon={faPlay} />
                    </button>
                    <button
                      className="modal-action-button"
                      onClick={() => handleRestartTranscribe(expandedId)}
                      disabled={restartingTranscribe === expandedId || restartingSummary === expandedId}
                      title={restartingTranscribe === expandedId ? t('history.item.restartingTranscribe') : t('history.item.restartTranscribe')}
                    >
                      <FontAwesomeIcon icon={faRedo} spin={restartingTranscribe === expandedId} />
                    </button>
                    <button
                      className="modal-action-button"
                      onClick={() => handleRestartSummary(expandedId)}
                      disabled={restartingTranscribe === expandedId || restartingSummary === expandedId}
                      title={restartingSummary === expandedId ? t('history.item.restartingSummary') : t('history.item.restartSummary')}
                    >
                      <FontAwesomeIcon icon={faRedo} spin={restartingSummary === expandedId} />
                    </button>
                    <button
                      className="modal-action-button"
                      onClick={() => handleAddToPlaylist(expandedId)}
                      disabled={addingToPlaylist === expandedId}
                      title={addingToPlaylist === expandedId ? t('history.item.addingToPlaylist') : t('history.item.addToPlaylist')}
                    >
                      <FontAwesomeIcon icon={faPlus} spin={addingToPlaylist === expandedId} />
                    </button>
                    <button
                      className="modal-action-button"
                      onClick={() => handleExport(expandedId, expandedDetail.title)}
                      disabled={exporting === expandedId}
                      title={exporting === expandedId ? t('history.item.exporting') : t('history.item.export')}
                    >
                      <FontAwesomeIcon icon={faDownload} spin={exporting === expandedId} />
                    </button>
                  </>
                )}
                <button
                  className="modal-action-button"
                  onClick={() => handleDelete(expandedId, expandedDetail.title)}
                  disabled={deleting === expandedId}
                  title={t('history.item.deleteTitle')}
                >
                  <FontAwesomeIcon icon={faTrash} />
                </button>
                <button className="modal-close-text" onClick={closeDetailModal}>
                  {t('history.item.close')}
                </button>
                <button className="modal-close" onClick={closeDetailModal}>×</button>
              </div>
            </div>
            <div className="modal-body history-detail-modal-body">
              {/* Keywords Display (read-only) */}
              <div className="keywords-section">
                <div className="keywords-header">
                  <h4>{t('history.item.keywords')}</h4>
                  {!editingId && (
                    <button
                      className="generate-keywords-button"
                      onClick={() => handleGenerateKeywords(expandedId)}
                      disabled={generatingKeywords === expandedId || !expandedDetail.transcript}
                      title={t('history.item.generateKeywordsTitle')}
                    >
                      {generatingKeywords === expandedId ? t('history.item.generatingKeywords') : t('history.item.generateKeywords')}
                    </button>
                  )}
                </div>
                <div className="keywords-display">
                  {parseKeywords(expandedDetail.keywords).length > 0 ? (
                    parseKeywords(expandedDetail.keywords).map((keyword, idx) => (
                      <span key={idx} className="keyword-tag">{keyword}</span>
                    ))
                  ) : (
                    <span className="no-keywords">{t('history.item.noKeywords')}</span>
                  )}
                </div>
              </div>

              {/* Summary Display */}
              {expandedDetail.summary && (
                <div className="summary-section">
                  <h4>{t('history.item.summary')}</h4>
                  <div className="markdown-content summary-content">
                    <ReactMarkdown
                      components={{
                        code({ node, inline, className, children, ...props }: any) {
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
                      {expandedDetail.summary}
                    </ReactMarkdown>
                  </div>
                </div>
              )}

              {/* Transcript/Markdown Content Display/Edit */}
              <div className="transcript-section">
                <div className="transcript-header">
                  <h4>{t('history.item.content')}</h4>
                  {!editingId && (
                    <button
                      className="edit-content-button"
                      onClick={() => handleEdit(expandedId)}
                    >
                      {t('history.item.edit')}
                    </button>
                  )}
                </div>
                {editingId === expandedId ? (
                  <div className="transcript-edit">
                    <textarea
                      value={editTranscript}
                      onChange={(e) => setEditTranscript(e.target.value)}
                      className="transcript-textarea"
                      rows={25}
                      placeholder={t('history.item.editPlaceholder')}
                    />
                    <div className="transcript-preview">
                      <h5>{t('history.item.markdownPreview')}</h5>
                      <div className="markdown-content">
                        <ReactMarkdown
                          components={{
                            code({ node, inline, className, children, ...props }: any) {
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
                          {editTranscript || '暂无内容'}
                        </ReactMarkdown>
                      </div>
                    </div>
                    <div className="edit-actions">
                      <button
                        className="save-button"
                        onClick={() => handleSave(expandedId)}
                        disabled={saving === expandedId}
                      >
                        {saving === expandedId ? t('history.item.saving') : t('history.item.save')}
                      </button>
                      <button
                        className="cancel-button"
                        onClick={handleCancelEdit}
                        disabled={saving === expandedId}
                      >
                        {t('history.item.cancel')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="transcript-display">
                    {expandedDetail.transcript ? (
                      <div className="markdown-content">
                        <ReactMarkdown
                          components={{
                            code({ node, inline, className, children, ...props }: any) {
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
                            },
                            p: ({ children }: any) => {
                              // Ensure paragraphs have proper spacing
                              return <p style={{ marginBottom: '1rem', whiteSpace: 'pre-wrap' }}>{children}</p>
                            },
                            h1: ({ children }: any) => <h1 style={{ marginTop: '2rem', marginBottom: '1rem' }}>{children}</h1>,
                            h2: ({ children }: any) => <h2 style={{ marginTop: '1.5rem', marginBottom: '0.75rem' }}>{children}</h2>,
                            h3: ({ children }: any) => <h3 style={{ marginTop: '1.5rem', marginBottom: '0.75rem' }}>{children}</h3>,
                            h4: ({ children }: any) => <h4 style={{ marginTop: '1.25rem', marginBottom: '0.5rem' }}>{children}</h4>,
                            ul: ({ children }: any) => <ul style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>{children}</ul>,
                            ol: ({ children }: any) => <ol style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>{children}</ol>,
                            li: ({ children }: any) => <li style={{ marginBottom: '0.25rem' }}>{children}</li>
                          }}
                        >
                          {formatTextForMarkdown(expandedDetail.transcript)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="no-transcript">{t('history.item.noContent')}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {reprocessDialogOpen !== null && (
        <div className="modal-overlay" onClick={closeReprocessDialog}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('history.item.reprocessTitle')}</h3>
              <button className="modal-close" onClick={closeReprocessDialog}>×</button>
            </div>
            <div className="modal-body">
              <p>{t('history.item.reprocessDescription')}</p>
              <div className="form-group">
                <label>{t('history.item.selectLanguage')}</label>
                <LanguageSelector
                  value={reprocessLanguage}
                  onChange={setReprocessLanguage}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="button-secondary"
                onClick={closeReprocessDialog}
                disabled={reprocessingId !== null}
              >
                {t('history.item.cancel')}
              </button>
              <button
                className="button-primary"
                onClick={() => {
                  const item = history.find(i => i.id === reprocessDialogOpen)
                  if (item) {
                    handleReprocess(item.id, item.url)
                  }
                }}
                disabled={reprocessingId !== null}
              >
                {reprocessingId !== null ? t('history.item.reprocessing') : t('history.item.reprocess')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default HistoryPage
