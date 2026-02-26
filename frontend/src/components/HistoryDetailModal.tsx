import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
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
  faChevronRight,
} from '@fortawesome/free-solid-svg-icons'
import { historyApi, videoApi, playlistApi, HistoryDetail } from '../services/api'
import './HistoryPage.css'

function getReadCount(item: Pick<HistoryDetail, 'read_count'> | null | undefined): number {
  return item?.read_count ?? 0
}

function parseKeywords(keywords?: string): string[] {
  if (!keywords) return []
  return keywords.split(',').map((k) => k.trim()).filter((k) => k.length > 0)
}

function formatTextForMarkdown(text: string): string {
  if (!text) return ''
  if (
    text.includes('\n#') || text.includes('\n##') || text.includes('\n###') ||
    text.includes('\n-') || text.includes('\n*') || text.includes('\n1.') ||
    text.match(/\n#{1,6}\s/)
  ) {
    return text
  }
  let formatted = text
  formatted = formatted.replace(/([一二三四五六七八九十]+[、.])\s*([^\n]+)/g, '\n\n### $1 $2\n\n')
  formatted = formatted.replace(/(\d+[、.])\s*([^\n]+)/g, '\n\n#### $1 $2\n\n')
  formatted = formatted.replace(/([•\-*]|\d+\.)\s+([^\n]+)/g, '\n- $2')
  const protectedPatterns: string[] = []
  let patternIndex = 0
  formatted = formatted.replace(/(###?[^\n]+\n)/g, (match) => {
    protectedPatterns.push(match)
    return `__PROTECTED_${patternIndex++}__`
  })
  formatted = formatted.replace(/([。！？])\s*([^。！？\n])/g, '$1\n\n$2')
  formatted = formatted.replace(/([.!?])\s+([A-Z])/g, '$1\n\n$2')
  protectedPatterns.forEach((pattern, idx) => {
    formatted = formatted.replace(`__PROTECTED_${idx}__`, pattern)
  })
  formatted = formatted.replace(/\n{4,}/g, '\n\n\n').replace(/\n{3,}/g, '\n\n')
  formatted = formatted
    .split('\n')
    .map((line, index, array) => {
      const trimmed = line.trim()
      if (trimmed.match(/^#{1,6}\s/)) return trimmed
      if (trimmed.match(/^[-*•]\s/) && index > 0 && array[index - 1].trim().match(/^[-*•]\s/)) return trimmed
      return trimmed
    })
    .join('\n')
  formatted = formatted.replace(/(\n)(#{1,6}\s[^\n]+)(\n)([^\n#])/g, '$1$2$3\n$4')
  return formatted.trim()
}

export interface HistoryDetailModalProps {
  detail: HistoryDetail | null
  onClose: () => void
  prevId?: number | null
  nextId?: number | null
  onNavigate?: (id: number) => void
  onDeleted?: () => void
  /** If provided, called with updated detail after save and modal stays open; otherwise modal closes after save */
  onSaved?: (updated: HistoryDetail) => void
}

const HistoryDetailModal: React.FC<HistoryDetailModalProps> = ({
  detail,
  onClose,
  prevId = null,
  nextId = null,
  onNavigate,
  onDeleted,
  onSaved,
}) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [editTranscript, setEditTranscript] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState<number | null>(null)
  const [exporting, setExporting] = useState<number | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [addingToPlaylist, setAddingToPlaylist] = useState<number | null>(null)
  const [generatingKeywords, setGeneratingKeywords] = useState<number | null>(null)
  const [restartingTranscribe, setRestartingTranscribe] = useState<number | null>(null)
  const [restartingSummary, setRestartingSummary] = useState<number | null>(null)

  useEffect(() => {
    if (detail) {
      setEditTranscript(detail.transcript || '')
      setEditingId(null)
    }
  }, [detail?.id])

  if (!detail) return null

  const id = detail.id

  const handleEdit = () => {
    setEditingId(id)
    setEditTranscript(detail.transcript || '')
  }

  const handleCancelEdit = () => {
    setEditTranscript(detail.transcript || '')
    setEditingId(null)
  }

  const handleSave = async () => {
    setSaving(id)
    try {
      const updated = await historyApi.updateHistory(id, { transcript: editTranscript })
      setEditingId(null)
      alert(t('history.item.saveSuccess'))
      if (onSaved) {
        onSaved(updated)
      } else {
        onClose()
      }
    } catch (err) {
      console.error('Failed to save:', err)
      alert(t('history.item.saveFailed'))
    } finally {
      setSaving(null)
    }
  }

  const handleExport = async () => {
    setExporting(id)
    try {
      const blob = await historyApi.exportMarkdown(id, false)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = detail.title
        ? `${detail.title.replace(/[^a-z0-9]/gi, '_')}_${id}.md`
        : `video_${id}.md`
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

  const handleRetry = async () => {
    setRetrying(id)
    try {
      await videoApi.retry(id)
      onClose()
    } catch (err: any) {
      console.error('Failed to retry:', err)
      alert(err.response?.data?.detail || t('history.item.retryFailed'))
    } finally {
      setRetrying(null)
    }
  }

  const handleDelete = async () => {
    const confirmMessage = detail.title
      ? t('history.item.deleteConfirm', { title: detail.title })
      : t('history.item.deleteConfirmNoTitle')
    if (!window.confirm(confirmMessage)) return
    setDeleting(id)
    try {
      await historyApi.deleteHistory(id)
      onDeleted?.()
      onClose()
    } catch (err: any) {
      console.error('Failed to delete:', err)
      alert(err.response?.data?.detail || t('history.item.deleteFailed'))
    } finally {
      setDeleting(null)
    }
  }

  const handlePlay = () => navigate(`/player/${id}`)
  const handleAddToPlaylist = async () => {
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

  const handleGenerateKeywords = async () => {
    setGeneratingKeywords(id)
    try {
      await historyApi.generateKeywords(id)
      alert(t('history.item.generateKeywordsSuccess'))
      onClose()
    } catch (err: any) {
      console.error('Failed to generate keywords:', err)
      alert(err.response?.data?.detail || t('history.item.generateKeywordsFailed'))
    } finally {
      setGeneratingKeywords(null)
    }
  }

  const handleRestartTranscribe = async () => {
    setRestartingTranscribe(id)
    try {
      await videoApi.bulkRestartTranscribe([id])
      const updated = await historyApi.getDetail(id)
      onSaved?.(updated)
    } catch (err: any) {
      console.error('Failed to restart transcribe:', err)
      alert(err.response?.data?.detail || t('history.item.restartTranscribeFailed'))
    } finally {
      setRestartingTranscribe(null)
    }
  }

  const handleRestartSummary = async () => {
    setRestartingSummary(id)
    try {
      await videoApi.bulkRestartSummary([id])
      const updated = await historyApi.getDetail(id)
      onSaved?.(updated)
    } catch (err: any) {
      console.error('Failed to restart summary:', err)
      alert(err.response?.data?.detail || t('history.item.restartSummaryFailed'))
    } finally {
      setRestartingSummary(null)
    }
  }

  const markdownComponents = {
    code({ node, inline, className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className || '')
      return !inline && match ? (
        <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" {...props}>
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className={className} {...props}>{children}</code>
      )
    },
  }

  const transcriptMarkdownComponents = {
    ...markdownComponents,
    p: ({ children }: any) => <p style={{ marginBottom: '1rem', whiteSpace: 'pre-wrap' }}>{children}</p>,
    h1: ({ children }: any) => <h1 style={{ marginTop: '2rem', marginBottom: '1rem' }}>{children}</h1>,
    h2: ({ children }: any) => <h2 style={{ marginTop: '1.5rem', marginBottom: '0.75rem' }}>{children}</h2>,
    h3: ({ children }: any) => <h3 style={{ marginTop: '1.5rem', marginBottom: '0.75rem' }}>{children}</h3>,
    h4: ({ children }: any) => <h4 style={{ marginTop: '1.25rem', marginBottom: '0.5rem' }}>{children}</h4>,
    ul: ({ children }: any) => <ul style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>{children}</ul>,
    ol: ({ children }: any) => <ol style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>{children}</ol>,
    li: ({ children }: any) => <li style={{ marginBottom: '0.25rem' }}>{children}</li>,
  }

  return (
    <div className="modal-overlay modal-overlay-below-header" onClick={onClose}>
      <div className="modal-content modal-fullscreen" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title-ellipsis">{detail.title || detail.url}</h3>
          <span className="read-count-badge" title={t('history.item.readCountTitle')}>
            {t('history.item.readCount', { count: getReadCount(detail) })}
          </span>
          <div className="modal-actions">
            {onNavigate && (
              <>
                <button
                  type="button"
                  className="modal-action-button"
                  onClick={() => prevId !== null && onNavigate(prevId)}
                  disabled={prevId === null}
                  title={t('history.item.previous')}
                >
                  <FontAwesomeIcon icon={faChevronLeft} />
                </button>
                <button
                  type="button"
                  className="modal-action-button"
                  onClick={() => nextId !== null && onNavigate(nextId)}
                  disabled={nextId === null}
                  title={t('history.item.next')}
                >
                  <FontAwesomeIcon icon={faChevronRight} />
                </button>
              </>
            )}
            <a
              href={detail.url}
              target="_blank"
              rel="noopener noreferrer"
              className="modal-action-button"
              title={detail.url}
            >
              <FontAwesomeIcon icon={faExternalLinkAlt} />
            </a>
            {detail.status === 'failed' && (
              <button
                className="modal-action-button"
                onClick={handleRetry}
                disabled={retrying === id}
                title={retrying === id ? t('history.item.retrying') : t('history.item.retry')}
              >
                <FontAwesomeIcon icon={faRedo} spin={retrying === id} />
              </button>
            )}
            {detail.status === 'completed' && (
              <>
                <button className="modal-action-button" onClick={handlePlay} title={t('history.item.play')}>
                  <FontAwesomeIcon icon={faPlay} />
                </button>
                <button
                  className="modal-action-button"
                  onClick={handleRestartTranscribe}
                  disabled={restartingTranscribe === id || restartingSummary === id}
                  title={restartingTranscribe === id ? t('history.item.restartingTranscribe') : t('history.item.restartTranscribe')}
                >
                  <FontAwesomeIcon icon={faRedo} spin={restartingTranscribe === id} />
                </button>
                <button
                  className="modal-action-button"
                  onClick={handleRestartSummary}
                  disabled={restartingTranscribe === id || restartingSummary === id}
                  title={restartingSummary === id ? t('history.item.restartingSummary') : t('history.item.restartSummary')}
                >
                  <FontAwesomeIcon icon={faRedo} spin={restartingSummary === id} />
                </button>
                <button
                  className="modal-action-button"
                  onClick={handleAddToPlaylist}
                  disabled={addingToPlaylist === id}
                  title={addingToPlaylist === id ? t('history.item.addingToPlaylist') : t('history.item.addToPlaylist')}
                >
                  <FontAwesomeIcon icon={faPlus} spin={addingToPlaylist === id} />
                </button>
                <button
                  className="modal-action-button"
                  onClick={() => handleExport()}
                  disabled={exporting === id}
                  title={exporting === id ? t('history.item.exporting') : t('history.item.export')}
                >
                  <FontAwesomeIcon icon={faDownload} spin={exporting === id} />
                </button>
              </>
            )}
            <button
              className="modal-action-button"
              onClick={() => handleDelete()}
              disabled={deleting === id}
              title={t('history.item.deleteTitle')}
            >
              <FontAwesomeIcon icon={faTrash} />
            </button>
            <button className="modal-close-text" onClick={onClose}>
              {t('history.item.close')}
            </button>
            <button className="modal-close" onClick={onClose}>×</button>
          </div>
        </div>
        <div className="modal-body history-detail-modal-body">
          <div className="keywords-section">
            <div className="keywords-header">
              <h4>{t('history.item.keywords')}</h4>
              {!editingId && (
                <button
                  className="generate-keywords-button"
                  onClick={handleGenerateKeywords}
                  disabled={generatingKeywords === id || !detail.transcript}
                  title={t('history.item.generateKeywordsTitle')}
                >
                  {generatingKeywords === id ? t('history.item.generatingKeywords') : t('history.item.generateKeywords')}
                </button>
              )}
            </div>
            <div className="keywords-display">
              {parseKeywords(detail.keywords).length > 0 ? (
                parseKeywords(detail.keywords).map((keyword, idx) => (
                  <span key={idx} className="keyword-tag">{keyword}</span>
                ))
              ) : (
                <span className="no-keywords">{t('history.item.noKeywords')}</span>
              )}
            </div>
          </div>

          {detail.summary && (
            <div className="summary-section">
              <h4>{t('history.item.summary')}</h4>
              <div className="markdown-content summary-content">
                <ReactMarkdown components={markdownComponents}>{detail.summary}</ReactMarkdown>
              </div>
            </div>
          )}

          <div className="transcript-section">
            <div className="transcript-header">
              <h4>{t('history.item.content')}</h4>
              {!editingId && (
                <button className="edit-content-button" onClick={handleEdit}>
                  {t('history.item.edit')}
                </button>
              )}
            </div>
            {editingId === id ? (
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
                    <ReactMarkdown components={markdownComponents}>{editTranscript || '暂无内容'}</ReactMarkdown>
                  </div>
                </div>
                <div className="edit-actions">
                  <button className="save-button" onClick={handleSave} disabled={saving === id}>
                    {saving === id ? t('history.item.saving') : t('history.item.save')}
                  </button>
                  <button className="cancel-button" onClick={handleCancelEdit} disabled={saving === id}>
                    {t('history.item.cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="transcript-display">
                {detail.transcript ? (
                  <div className="markdown-content">
                    <ReactMarkdown components={transcriptMarkdownComponents}>
                      {formatTextForMarkdown(detail.transcript)}
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
  )
}

export default HistoryDetailModal
