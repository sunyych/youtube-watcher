import { useTranslation } from 'react-i18next'
import './ProgressBar.css'

interface ProgressBarProps {
  progress: number
  status: string
  stages?: Array<{ name: string; progress: number }>
}

const ProgressBar: React.FC<ProgressBarProps> = ({ progress, status, stages }) => {
  const { t } = useTranslation()
  
  const getStatusText = (status: string) => {
    const statusKey = `progress.status.${status}`
    return t(statusKey, { defaultValue: status })
  }

  return (
    <div className="progress-container">
      <div className="progress-header">
        <span className="progress-status">{getStatusText(status)}</span>
        <span className="progress-percent">{Math.round(progress)}%</span>
      </div>
      <div className="progress-bar-wrapper">
        <div
          className="progress-bar"
          style={{ width: `${progress}%` }}
        />
      </div>
      {stages && (
        <div className="progress-stages">
          {stages.map((stage, index) => (
            <div
              key={index}
              className={`progress-stage ${stage.progress >= 100 ? 'completed' : ''}`}
            >
              {stage.name}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ProgressBar
