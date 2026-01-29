import { useState, useEffect } from 'react'
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
  faSync,
  faPlay,
  faPlus
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
  type HistoryTab = 'noSummary' | 'withSummary'
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
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(10)
  const [totalCount, setTotalCount] = useState(0)
  const [activeTab, setActiveTab] = useState<HistoryTab>('noSummary')

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
      const hasSummary = activeTab === 'withSummary'
      const [data, count] = await Promise.all([
        historyApi.getHistory(skip, pageSize, hasSummary),
        historyApi.getHistoryCount(hasSummary)
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
      const hasSummary = activeTab === 'withSummary'
      const [data, count] = await Promise.all([
        historyApi.searchHistory(searchQuery.trim(), skip, pageSize, hasSummary),
        historyApi.searchHistoryCount(searchQuery.trim(), hasSummary)
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

  const totalPages = Math.ceil(totalCount / pageSize)

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null)
      setExpandedDetail(null)
      setEditingId(null)
      return
    }

    try {
      const detail = await historyApi.getDetail(id)
      setExpandedId(id)
      setExpandedDetail(detail)
      setEditTranscript(detail.transcript || '')
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

  const openReprocessDialog = (id: number) => {
    setReprocessDialogOpen(id)
    setReprocessLanguage('')
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

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const language = localStorage.getItem('language') || 'en'
    return date.toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US')
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

  const renderHistoryItem = (item: HistoryItem) => (
    <div key={item.id} className="history-tile">
      <div className="history-tile-thumbnail" onClick={() => handleExpand(item.id)}>
        {item.thumbnail_path ? (
          <img 
            src={videoApi.getThumbnailUrl(item.id)} 
            alt={item.title || 'Video thumbnail'}
            className="thumbnail-image"
            onError={(e) => {
              // Fallback to placeholder if image fails to load
              (e.target as HTMLImageElement).style.display = 'none'
              const placeholder = (e.target as HTMLImageElement).nextElementSibling as HTMLElement
              if (placeholder) placeholder.style.display = 'flex'
            }}
          />
        ) : null}
        <div className="thumbnail-placeholder" style={{ display: item.thumbnail_path ? 'none' : 'flex' }}>
          <FontAwesomeIcon icon={faPlay} />
        </div>
        <div className="thumbnail-overlay">
          <span className={`status-badge status-${item.status}`}>
            {item.status}
          </span>
        </div>
      </div>
      <div className="history-tile-content">
        <h3
          className="history-tile-title"
          onClick={() => handleExpand(item.id)}
          title={item.title || item.url}
        >
          {item.title || item.url}
        </h3>
        <div className="history-tile-meta">
          {item.upload_date && (
            <span className="history-tile-upload-date">
              {formatUploadDate(item.upload_date)}
            </span>
          )}
          {item.language && (
            <span className="history-tile-language">{item.language}</span>
          )}
        </div>
        {expandedId !== item.id && item.keywords && (
          <div className="history-tile-keywords">
            {parseKeywords(item.keywords).slice(0, 3).map((keyword, idx) => (
              <span key={idx} className="keyword-tag-small">{keyword}</span>
            ))}
            {parseKeywords(item.keywords).length > 3 && (
              <span className="keyword-more">+{parseKeywords(item.keywords).length - 3}</span>
            )}
          </div>
        )}
        <div className="history-tile-actions">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="tile-action-button"
            onClick={(e) => e.stopPropagation()}
            title={item.url}
          >
            <FontAwesomeIcon icon={faExternalLinkAlt} />
          </a>
          {item.status === 'failed' && (
            <button
              className="tile-action-button"
              onClick={(e) => {
                e.stopPropagation()
                handleRetry(item.id)
              }}
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
                onClick={(e) => {
                  e.stopPropagation()
                  handlePlay(item.id)
                }}
                title={t('history.item.play')}
              >
                <FontAwesomeIcon icon={faPlay} />
              </button>
              <button
                className="tile-action-button"
                onClick={(e) => {
                  e.stopPropagation()
                  handleAddToPlaylist(item.id)
                }}
                disabled={addingToPlaylist === item.id}
                title={addingToPlaylist === item.id ? t('history.item.addingToPlaylist') : t('history.item.addToPlaylist')}
              >
                <FontAwesomeIcon icon={faPlus} spin={addingToPlaylist === item.id} />
              </button>
              <button
                className="tile-action-button"
                onClick={(e) => {
                  e.stopPropagation()
                  handleExport(item.id, item.title)
                }}
                disabled={exporting === item.id}
                title={exporting === item.id ? t('history.item.exporting') : t('history.item.export')}
              >
                <FontAwesomeIcon icon={faDownload} spin={exporting === item.id} />
              </button>
            </>
          )}
          <button
            className="tile-action-button"
            onClick={(e) => {
              e.stopPropagation()
              handleDelete(item.id, item.title)
            }}
            disabled={deleting === item.id}
            title={t('history.item.deleteTitle')}
          >
            <FontAwesomeIcon icon={faTrash} />
          </button>
        </div>
      </div>
      {expandedId === item.id && expandedDetail && (
        <div className="history-item-detail">
          {/* Keywords Display (read-only) */}
          <div className="keywords-section">
            <div className="keywords-header">
              <h4>{t('history.item.keywords')}</h4>
              {!editingId && expandedDetail && (
                <button
                  className="generate-keywords-button"
                  onClick={() => handleGenerateKeywords(item.id)}
                  disabled={generatingKeywords === item.id || !expandedDetail.transcript}
                  title={t('history.item.generateKeywordsTitle')}
                >
                  {generatingKeywords === item.id ? t('history.item.generatingKeywords') : t('history.item.generateKeywords')}
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
                  onClick={() => handleEdit(item.id)}
                >
                  {t('history.item.edit')}
                </button>
              )}
            </div>
            {editingId === item.id ? (
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
                    onClick={() => handleSave(item.id)}
                    disabled={saving === item.id}
                  >
                    {saving === item.id ? t('history.item.saving') : t('history.item.save')}
                  </button>
                  <button
                    className="cancel-button"
                    onClick={handleCancelEdit}
                    disabled={saving === item.id}
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
      )}
    </div>
  )


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
          <div className="tabs-list">
            <button
              className={`tabs-trigger ${activeTab === 'noSummary' ? 'tabs-trigger-active' : ''}`}
              onClick={() => handleTabChange('noSummary')}
              type="button"
            >
              {t('history.tabs.noTranscript')}
            </button>
            <button
              className={`tabs-trigger ${activeTab === 'withSummary' ? 'tabs-trigger-active' : ''}`}
              onClick={() => handleTabChange('withSummary')}
              type="button"
            >
              {t('history.tabs.withSummary')}
            </button>
          </div>
          <div className="history-tab-panel">
            {history.length === 0 ? (
              <div className="empty-state-tab">
                {searchQuery ? t('history.emptyState.noResults') : t('history.emptyState.noHistory')}
              </div>
            ) : (
              <div className="history-list">
                {history.map(renderHistoryItem)}
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
