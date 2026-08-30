import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadCloud, FileText, Loader2, RotateCcw, XCircle } from 'lucide-react'
import { uploadAndAnalyze, getJob, retryJob, getRun, isUnverifiedEmailError } from '../api'
import { useAnalysis } from '../context/AnalysisContext'
import VerifyEmailModal from '../components/VerifyEmailModal'

// Mirrors the backend's job stages (see app/routers/analysis.py) — kept
// as a flat lookup so adding/renaming a stage server-side only needs a
// one-line change here, not a restructure.
const STAGE_LABELS = {
  UPLOAD_VALIDATION: 'Validating your file…',
  DATA_PREPARATION: 'Preparing data…',
  FEATURE_ENGINEERING: 'Engineering features…',
  MODEL_TRAINING: 'Training model…',
  MODEL_EVALUATION: 'Evaluating model…',
  SHAP_ANALYSIS: 'Generating explanations…',
  CUSTOMER_SCORING: 'Scoring customers…',
  INSIGHT_GENERATION: 'Generating insights…',
  COMPLETED: 'Completed.',
}

const POLL_INTERVAL_MS = 1500

export default function UploadPage() {
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)
  const [job, setJob] = useState(null) // { id, status, stage, progress, error_message, ... }
  const [showVerifyModal, setShowVerifyModal] = useState(false)
  const { setResult } = useAnalysis()
  const navigate = useNavigate()
  const pollRef = useRef(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => () => stopPolling(), [])

  const pollJob = (jobId) => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const res = await getJob(jobId)
        setJob(res.data)
        if (res.data.status === 'COMPLETED') {
          stopPolling()
          const run = await getRun(res.data.analysis_run_id)
          setResult(run.data)
          navigate('/dashboard')
        } else if (res.data.status === 'FAILED' || res.data.status === 'CANCELLED') {
          stopPolling()
        }
      } catch (err) {
        stopPolling()
        setError('Lost connection while checking analysis status. Refresh and check Upload History.')
      }
    }, POLL_INTERVAL_MS)
  }

  const onDrop = useCallback((e) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }, [])

  const run = async () => {
    if (!file) return
    setError(null)
    setJob(null)
    try {
      const res = await uploadAndAnalyze(file)
      setJob(res.data)
      pollJob(res.data.id)
    } catch (err) {
      if (isUnverifiedEmailError(err)) {
        setShowVerifyModal(true)
        return
      }
      setError(err?.response?.data?.detail || 'Upload failed. Check the backend is running.')
    }
  }

  const retry = async () => {
    if (!job) return
    setError(null)
    try {
      const res = await retryJob(job.id)
      setJob(res.data)
      pollJob(res.data.id)
    } catch (err) {
      if (isUnverifiedEmailError(err)) {
        setShowVerifyModal(true)
        return
      }
      setError(err?.response?.data?.detail || 'Retry failed. You may need to re-upload the file.')
    }
  }

  const isBusy = job && (job.status === 'QUEUED' || job.status === 'PROCESSING')

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold">Upload & Analyze</h1>
      <p className="text-muted mt-1">
        CSV should follow the source schema: month-suffixed usage columns
        (e.g. <code className="font-mono text-sm bg-black/5 px-1 rounded">arpu_6</code>,{' '}
        <code className="font-mono text-sm bg-black/5 px-1 rounded">total_ic_mou_8</code>) for months 6–9,
        plus <code className="font-mono text-sm bg-black/5 px-1 rounded">aon</code> (age on network) and
        optionally <code className="font-mono text-sm bg-black/5 px-1 rounded">mobile_number</code>.
        If a <code className="font-mono text-sm bg-black/5 px-1 rounded">churn</code> column isn't present,
        it's derived from month-9 activity being zero.
      </p>
      <p className="text-xs text-muted mt-2">
        Uploads are processed in the background — you'll see live progress below, and can leave
        this page and come back; check Upload History if you navigate away mid-run.
      </p>

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className="mt-6 border-2 border-dashed border-black/15 rounded-xl p-10 text-center bg-card"
      >
        <UploadCloud className="mx-auto text-signal" size={32} />
        <p className="mt-3 text-sm text-muted">Drag a .csv file here, or</p>
        <label className="inline-block mt-2 text-signal font-medium cursor-pointer hover:underline">
          browse files
          <input
            type="file" accept=".csv" className="hidden" disabled={isBusy}
            onChange={(e) => setFile(e.target.files[0])}
          />
        </label>
        {file && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm font-medium">
            <FileText size={16} /> {file.name}
          </div>
        )}
      </div>

      {error && <div className="mt-4 text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-4 py-3">{error}</div>}

      {job && job.status === 'FAILED' && (
        <div className="mt-4 rounded-lg border border-tier-critical/30 bg-tier-critical/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-tier-critical">
            <XCircle size={16} /> Analysis failed
          </div>
          <div className="text-xs text-muted mt-1">{job.error_message}</div>
          {job.retry_count < 3 && (
            <button
              onClick={retry}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-signal hover:underline"
            >
              <RotateCcw size={14} /> Retry
            </button>
          )}
        </div>
      )}

      {isBusy && (
        <div className="mt-4">
          <div className="h-2 w-full bg-black/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-signal transition-all duration-500"
              style={{ width: `${job.progress || 5}%` }}
            />
          </div>
          <div className="text-xs text-muted mt-2">
            {STAGE_LABELS[job.stage] || 'Working…'} ({job.progress || 0}%)
          </div>
        </div>
      )}

      <button
        onClick={run}
        disabled={!file || isBusy}
        className="mt-6 w-full flex items-center justify-center gap-2 bg-ink text-white py-3 rounded-lg font-medium disabled:opacity-40 hover:bg-signal transition-colors"
      >
        {isBusy
          ? <><Loader2 className="animate-spin" size={16} /> {STAGE_LABELS[job.stage] || 'Working…'}</>
          : 'Run analysis'}
      </button>

      {showVerifyModal && <VerifyEmailModal onClose={() => setShowVerifyModal(false)} />}
    </div>
  )
}
