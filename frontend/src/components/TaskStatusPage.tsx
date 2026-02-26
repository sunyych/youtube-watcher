import { useEffect, useMemo, useState } from 'react'
import Header from './Header'
import { historyApi, videoApi, TaskItem, HistoryDetail } from '../services/api'
import HistoryDetailModal from './HistoryDetailModal'
import './TaskStatusPage.css'

type TabKey =
  | 'all'
  | 'pending'
  | 'downloading'
  | 'converting'
  | 'transcribing'
  | 'summarizing'
  | 'completed'
  | 'failed'
  | 'unavailable'

interface TaskStatusPageProps {
  onLogout: () => void
}

const ALL_STATUSES = ['pending', 'downloading', 'converting', 'transcribing', 'summarizing', 'completed', 'failed', 'unavailable']

const TAB_DEFS: Array<{ key: TabKey; label: string; statuses: string[] }> = [
  { key: 'all', label: '全部', statuses: ALL_STATUSES },
  { key: 'pending', label: '排队中', statuses: ['pending'] },
  { key: 'downloading', label: '下载中', statuses: ['downloading'] },
  { key: 'converting', label: '转码中', statuses: ['converting'] },
  { key: 'transcribing', label: '转写中', statuses: ['transcribing'] },
  { key: 'summarizing', label: '总结中', statuses: ['summarizing'] },
  { key: 'completed', label: '已完成', statuses: ['completed'] },
  { key: 'failed', label: '失败', statuses: ['failed'] },
  { key: 'unavailable', label: '无法下载', statuses: ['unavailable'] },
]

const PAGE_SIZE = 50

const STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  downloading: '下载中',
  converting: '转码中',
  transcribing: '转写中',
  summarizing: '总结中',
  completed: '已完成',
  failed: '失败',
  unavailable: '无法下载',
}

function formatApiError(e: any): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors are usually an array of objects like {loc, msg, type, ...}
    return detail
      .map((d) => (typeof d?.msg === 'string' ? d.msg : typeof d === 'string' ? d : JSON.stringify(d)))
      .filter(Boolean)
      .join('; ')
  }
  if (detail != null) return typeof detail === 'object' ? JSON.stringify(detail) : String(detail)
  return e?.message || 'Failed to load tasks'
}

const TaskStatusPage: React.FC<TaskStatusPageProps> = ({ onLogout }) => {
  const [activeTab, setActiveTab] = useState<TabKey>('all')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [items, setItems] = useState<TaskItem[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)

  const [selected, setSelected] = useState<Record<number, boolean>>({})
  const [detailData, setDetailData] = useState<HistoryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const openVideoDetail = async (id: number) => {
    setDetailLoading(true)
    try {
      const d = await historyApi.getDetail(id, { countRead: true })
      setDetailData(d)
    } catch (e: any) {
      console.error('Failed to load detail:', e)
      alert(formatApiError(e))
    } finally {
      setDetailLoading(false)
    }
  }

  const tab = useMemo(() => TAB_DEFS.find((t) => t.key === activeTab)!, [activeTab])
  const selectedIds = useMemo(() => Object.keys(selected).filter((k) => selected[Number(k)]).map(Number), [selected])

  const allOnPageSelected = useMemo(() => {
    if (items.length === 0) return false
    return items.every((it) => selected[it.id])
  }, [items, selected])

  const selectedCountOnPage = useMemo(() => items.filter((it) => selected[it.id]).length, [items, selected])

  const load = async (nextSkip: number) => {
    setLoading(true)
    setError(null)
    try {
      const res = await videoApi.getTasks(tab.statuses, nextSkip, PAGE_SIZE)
      setItems(res.items)
      setTotal(res.total)
      setSkip(res.skip)
      setSelected({})
    } catch (e: any) {
      setError(formatApiError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setSkip(0)
    load(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  const toggleSelectAllOnPage = () => {
    if (allOnPageSelected) {
      const next = { ...selected }
      items.forEach((it) => {
        delete next[it.id]
      })
      setSelected(next)
      return
    }

    const next = { ...selected }
    items.forEach((it) => {
      next[it.id] = true
    })
    setSelected(next)
  }

  const toggleOne = (id: number) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const runBulk = async (action: 'retry' | 'restart_transcribe' | 'restart_summary') => {
    if (selectedIds.length === 0) return
    setLoading(true)
    setError(null)
    try {
      if (action === 'retry') {
        await videoApi.bulkRetry(selectedIds)
      } else if (action === 'restart_transcribe') {
        await videoApi.bulkRestartTranscribe(selectedIds)
      } else {
        await videoApi.bulkRestartSummary(selectedIds)
      }
      await load(skip)
    } catch (e: any) {
      setError(formatApiError(e))
      setLoading(false)
    }
  }

  const runDeleteSelected = async () => {
    if (selectedIds.length === 0) return
    const ok = window.confirm(`确定要删除选中的 ${selectedIds.length} 条记录吗？此操作不可撤销，并会删除相关文件。`)
    if (!ok) return

    setLoading(true)
    setError(null)
    try {
      // Reuse /api/history/{id} delete: it deletes the VideoRecord + associated files
      await Promise.allSettled(selectedIds.map((id) => historyApi.deleteHistory(id)))
      await load(skip)
    } catch (e: any) {
      setError(formatApiError(e))
      setLoading(false)
    }
  }

  const canPrev = skip > 0
  const canNext = skip + PAGE_SIZE < total
  const canRestart = activeTab === 'completed'

  return (
    <div className="task-status-page page-with-header">
      <Header title="处理状态" onLogout={onLogout} />

      <div className="task-toolbar">
        <div className="task-tabs">
          <span className="task-meta">状态筛选：</span>
          {TAB_DEFS.map((t) => (
            <button
              key={t.key}
              className={`task-tab ${activeTab === t.key ? 'active' : ''}`}
              onClick={() => setActiveTab(t.key)}
              disabled={loading}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="task-actions">
          <div className="left">
            <label>
              <input
                type="checkbox"
                checked={allOnPageSelected}
                onChange={toggleSelectAllOnPage}
                disabled={loading || items.length === 0}
              />{' '}
              全选本页
            </label>
            <span className="task-meta">
              本页已选 {selectedCountOnPage} / {items.length}，总数 {total}
            </span>
            {loading && <span className="task-meta">加载中…</span>}
            {error && <span className="task-error">{error}</span>}
          </div>

          <div className="right">
            <button disabled={selectedIds.length === 0 || loading} onClick={() => runBulk('retry')}>
              重试（重新入队）
            </button>

            <button className="task-danger" disabled={selectedIds.length === 0 || loading} onClick={runDeleteSelected}>
              删除所选
            </button>

            {canRestart && (
              <>
                <button disabled={selectedIds.length === 0 || loading} onClick={() => runBulk('restart_transcribe')}>
                  重新 Transcribe
                </button>
                <button disabled={selectedIds.length === 0 || loading} onClick={() => runBulk('restart_summary')}>
                  重新总结
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <table className="task-table">
        <thead>
          <tr>
            <th className="task-col-check" />
            <th>视频</th>
            <th className="task-col-status">状态</th>
            <th className="task-col-progress">进度</th>
            <th className="task-col-time">时间</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="task-meta">
                {loading ? '加载中…' : '没有数据'}
              </td>
            </tr>
          ) : (
            items.map((it) => (
              <tr key={it.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`选择任务 ${it.id}`}
                    checked={!!selected[it.id]}
                    onChange={() => toggleOne(it.id)}
                    disabled={loading}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="task-title-button"
                    onClick={(e) => { e.preventDefault(); openVideoDetail(it.id) }}
                    disabled={detailLoading}
                    title="查看详情"
                  >
                    <div className="task-title">
                      #{it.id} {it.title || '(无标题)'}
                    </div>
                    <div className="task-url">{it.url}</div>
                  </button>
                  {it.error_message && <div className="task-error">{it.error_message}</div>}
                </td>
                <td>
                  {(() => {
                    const key = String(it.status || '').toLowerCase()
                    const label = STATUS_LABELS[key] || it.status || '-'
                    return <span title={it.status}>{label}</span>
                  })()}
                </td>
                <td>{Math.round(Number.isFinite(it.progress) ? it.progress : 0)}%</td>
                <td className="task-meta">
                  <div>created: {it.created_at || '-'}</div>
                  <div>updated: {it.updated_at || '-'}</div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div className="task-pagination">
        <button disabled={!canPrev || loading} onClick={() => load(Math.max(0, skip - PAGE_SIZE))}>
          上一页
        </button>
        <span className="task-meta">
          {skip + 1}-{Math.min(skip + PAGE_SIZE, total)} / {total}
        </span>
        <button disabled={!canNext || loading} onClick={() => load(skip + PAGE_SIZE)}>
          下一页
        </button>
      </div>

      <HistoryDetailModal
        detail={detailData}
        onClose={() => setDetailData(null)}
        onDeleted={() => load(skip)}
        onSaved={setDetailData}
      />
    </div>
  )
}

export default TaskStatusPage

