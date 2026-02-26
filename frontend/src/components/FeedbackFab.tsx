import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import html2canvas from 'html2canvas'
import { authApi, feedbackApi } from '../services/api'
import './FeedbackFab.css'

export default function FeedbackFab() {
  const { t } = useTranslation()
  const location = useLocation()
  const [showFeedbackButton, setShowFeedbackButton] = useState(true)
  const [open, setOpen] = useState(false)
  const [displayDescription, setDisplayDescription] = useState('')
  const [comment, setComment] = useState('')
  const [includeScreenshot, setIncludeScreenshot] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    authApi.getProfile().then((profile) => {
      setShowFeedbackButton(profile.show_feedback_button ?? true)
    }).catch(() => {
      setShowFeedbackButton(true)
    })
  }, [])

  const captureScreenshot = useCallback((): Promise<string | null> => {
    return html2canvas(document.body, {
      useCORS: true,
      allowTaint: true,
      logging: false,
      scale: window.devicePixelRatio || 1,
    }).then((canvas) => {
      const dataUrl = canvas.toDataURL('image/png')
      const base64 = dataUrl.replace(/^data:image\/png;base64,/, '')
      return base64
    }).catch(() => null)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = comment.trim()
    if (!trimmed) return
    setSubmitting(true)
    setMessage(null)
    try {
      let screenshot_base64: string | null = null
      if (includeScreenshot) {
        screenshot_base64 = await captureScreenshot()
      }
      await feedbackApi.submit({
        page: location.pathname,
        display_description: displayDescription.trim() || undefined,
        comment: trimmed,
        screenshot_base64: screenshot_base64 ?? undefined,
      })
      setMessage({ type: 'success', text: t('feedback.success') })
      setComment('')
      setDisplayDescription('')
      setTimeout(() => {
        setOpen(false)
        setMessage(null)
      }, 1500)
    } catch {
      setMessage({ type: 'error', text: t('feedback.failed') })
    } finally {
      setSubmitting(false)
    }
  }

  const handleOpen = () => setOpen(true)
  const handleClose = () => {
    if (!submitting) setOpen(false)
  }

  if (!showFeedbackButton) return null

  return (
    <>
      <button
        type="button"
        className="feedback-fab"
        onClick={handleOpen}
        aria-label={t('feedback.title')}
        title={t('feedback.title')}
      >
        <span className="feedback-fab-icon" aria-hidden="true">💬</span>
      </button>

      {open && (
        <div
          className="feedback-modal-overlay"
          onClick={handleClose}
          role="presentation"
        >
          <div
            className="feedback-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-modal-title"
          >
            <div className="feedback-modal-header">
              <h2 id="feedback-modal-title">{t('feedback.title')}</h2>
              <button
                type="button"
                className="feedback-modal-close"
                onClick={handleClose}
                disabled={submitting}
                aria-label={t('history.item.close')}
              >
                ×
              </button>
            </div>
            <form onSubmit={handleSubmit} className="feedback-modal-body">
              <div className="feedback-field">
                <label htmlFor="feedback-page">{t('feedback.page')}</label>
                <input
                  id="feedback-page"
                  type="text"
                  value={location.pathname}
                  readOnly
                  className="feedback-input feedback-input-readonly"
                />
              </div>
              <div className="feedback-field">
                <label htmlFor="feedback-display">{t('feedback.displayDescription')}</label>
                <input
                  id="feedback-display"
                  type="text"
                  value={displayDescription}
                  onChange={(e) => setDisplayDescription(e.target.value)}
                  placeholder={t('feedback.displayDescriptionPlaceholder')}
                  className="feedback-input"
                />
              </div>
              <div className="feedback-field">
                <label htmlFor="feedback-comment">{t('feedback.comment')}</label>
                <textarea
                  id="feedback-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder={t('feedback.commentPlaceholder')}
                  className="feedback-textarea"
                  rows={4}
                  required
                />
              </div>
              <label className="feedback-checkbox">
                <input
                  type="checkbox"
                  checked={includeScreenshot}
                  onChange={(e) => setIncludeScreenshot(e.target.checked)}
                />
                <span>{t('feedback.includeScreenshot')}</span>
              </label>
              {message && (
                <p className={`feedback-message feedback-message-${message.type}`}>
                  {message.text}
                </p>
              )}
              <div className="feedback-actions">
                <button
                  type="button"
                  className="feedback-btn feedback-btn-secondary"
                  onClick={handleClose}
                  disabled={submitting}
                >
                  {t('history.item.cancel')}
                </button>
                <button
                  type="submit"
                  className="feedback-btn feedback-btn-primary"
                  disabled={submitting || !comment.trim()}
                >
                  {submitting ? t('feedback.submitting') : t('feedback.submit')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
