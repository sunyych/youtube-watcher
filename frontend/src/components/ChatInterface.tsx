import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { videoApi, historyApi, QueueStatus, playlistApi } from '../services/api'
import Header from './Header'
import LanguageSelector from './LanguageSelector'
import ProgressBar from './ProgressBar'
import QueueDisplay from './QueueDisplay'
import './ChatInterface.css'

interface ChatInterfaceProps {
  onLogout: () => void
}

interface Message {
  id: number
  url: string
  title?: string
  status: string
  progress: number
  summary?: string
  error?: string
  error_message?: string
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onLogout }) => {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [language, setLanguage] = useState('')
  const [addToPlaylist, setAddToPlaylist] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Poll queue status
    const interval = setInterval(async () => {
      try {
        const status = await videoApi.getQueue()
        setQueueStatus(status)
      } catch (err) {
        console.error('Failed to fetch queue status:', err)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // Poll message statuses
    const interval = setInterval(async () => {
      for (const message of messages) {
        if (message.status !== 'completed' && message.status !== 'failed') {
          try {
            const status = await videoApi.getStatus(message.id)
            const updated = {
              ...message,
              status: status.status,
              progress: status.progress,
              error_message: status.error_message,
            }
            
            // If completed, fetch summary
            if (status.status === 'completed' && !message.summary) {
              try {
                const detail = await historyApi.getDetail(message.id)
                updated.summary = detail.summary
              } catch (err) {
                console.error('Failed to fetch summary:', err)
              }
            }
            
            setMessages((prev) =>
              prev.map((m) => (m.id === message.id ? updated : m))
            )
          } catch (err) {
            console.error('Failed to fetch status:', err)
          }
        }
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [messages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim() || loading) return

    setLoading(true)
    try {
      const result = await videoApi.process(url, language || undefined)
      const newMessage: Message = {
        id: result.id,
        url: result.url,
        title: result.title,
        status: result.status,
        progress: result.progress,
      }
      setMessages((prev) => [...prev, newMessage])
      
      // If add to playlist is checked, add to playlist
      if (addToPlaylist) {
        try {
          await playlistApi.addItem(result.id)
        } catch (err: any) {
          console.error('Failed to add to playlist:', err)
          // Don't show error to user, just log it
        }
      }
      
      setUrl('')
      setAddToPlaylist(false)
    } catch (err: any) {
      alert(err.response?.data?.detail || t('chat.message.processingFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleRetry = async (id: number) => {
    setLoading(true)
    try {
      const result = await videoApi.retry(id)
      // Update the message in the list
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id
            ? {
                ...m,
                status: result.status,
                progress: result.progress,
                error: undefined,
                error_message: undefined,
              }
            : m
        )
      )
    } catch (err: any) {
      alert(err.response?.data?.detail || t('chat.message.processingFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-interface page-with-header">
      <Header title={t('chat.header.title')} onLogout={onLogout} />

      <div className="chat-content">
        {queueStatus && <QueueDisplay queueStatus={queueStatus} />}

        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state">
              <p>{t('chat.emptyState')}</p>
            </div>
          ) : (
            messages.map((message) => (
              <div key={message.id} className="message">
                <div className="message-header">
                  <a
                    href={message.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="message-url"
                  >
                    {message.title || message.url}
                  </a>
                </div>
                <ProgressBar progress={message.progress} status={message.status} />
                {message.status === 'completed' && message.summary && (
                  <div className="message-summary">
                    <h4>{t('chat.message.summary')}</h4>
                    <p>{message.summary}</p>
                  </div>
                )}
                {message.status === 'failed' && (
                  <div className="message-error-container">
                    <div className="message-error">
                      {t('chat.message.error')} {message.error || message.error_message || t('chat.message.processingFailed')}
                    </div>
                    <button
                      className="retry-button"
                      onClick={() => handleRetry(message.id)}
                      disabled={loading}
                    >
                      {t('chat.message.retry')}
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className="input-form" onSubmit={handleSubmit}>
          <div className="input-group">
            <input
              type="text"
              placeholder={t('chat.input.placeholder')}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={loading}
            />
            <LanguageSelector value={language} onChange={setLanguage} />
            <button type="submit" disabled={loading || !url.trim()}>
              {loading ? t('chat.input.processing') : t('chat.input.submit')}
            </button>
          </div>
          <div className="input-options">
            <label>
              <input
                type="checkbox"
                checked={addToPlaylist}
                onChange={(e) => setAddToPlaylist(e.target.checked)}
                disabled={loading}
              />
              {t('chat.input.addToPlaylist')}
            </label>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChatInterface
