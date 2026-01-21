import { useTranslation } from 'react-i18next'
import { QueueStatus } from '../services/api'
import './QueueDisplay.css'

interface QueueDisplayProps {
  queueStatus: QueueStatus
}

const QueueDisplay: React.FC<QueueDisplayProps> = ({ queueStatus }) => {
  const { t } = useTranslation()
  
  if (queueStatus.queue_size === 0 && queueStatus.processing === 0) {
    return null
  }

  return (
    <div className="queue-display">
      <h3>{t('queue.title')}</h3>
      <div className="queue-stats">
        <div className="queue-stat">
          <span className="stat-label">{t('queue.waiting')}</span>
          <span className="stat-value">{queueStatus.queue_size}</span>
        </div>
        <div className="queue-stat">
          <span className="stat-label">{t('queue.processing')}</span>
          <span className="stat-value">{queueStatus.processing}</span>
        </div>
      </div>
      {queueStatus.processing_tasks.length > 0 && (
        <div className="processing-tasks">
          {queueStatus.processing_tasks.map((task) => (
            <div key={task.id} className="processing-task">
              {t('queue.task', { id: task.id, status: task.status })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default QueueDisplay
