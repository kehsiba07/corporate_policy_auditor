import { useState, useEffect } from 'react'
import FileUpload from './components/FileUpload'
import AuditConsole from './components/AuditConsole'
import ReportViewer from './components/ReportViewer'
import { openAuditSocket } from './services/api'

function App() {
  const [jobId, setJobId] = useState(null)
  const [logs, setLogs] = useState([])
  const [report, setReport] = useState(null)
  const [status, setStatus] = useState('idle') // idle | uploading | running | done | error
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!jobId) return undefined

    let active = true // false after cleanup, so a StrictMode-discarded socket is ignored
    let finished = false

    setLogs([])
    setReport(null)
    setError(null)
    setStatus('running')

    const socket = openAuditSocket(jobId, {
      onMessage: (msg) => {
        if (!active) return
        if (msg.type === 'log') {
          setLogs((prev) => [...prev, msg])
        } else if (msg.type === 'error') {
          finished = true
          setLogs((prev) => [...prev, msg])
          setError(msg.message)
          setStatus('error')
        } else if (msg.type === 'report') {
          finished = true
          setReport(msg.report)
          setStatus('done')
        }
      },
      onError: () => {
        if (!active || finished) return
        finished = true
        setError('Could not connect to the audit stream. Is the backend running?')
        setStatus('error')
      },
      onClose: () => {
        if (!active || finished) return
        finished = true
        setError('The connection to the server was lost before the audit finished.')
        setStatus('error')
      },
    })

    return () => {
      active = false
      socket.close()
    }
  }, [jobId])

  const busy = status === 'uploading' || status === 'running'

  const handleUploadStart = () => {
    setStatus('uploading')
    setError(null)
  }

  const handleUploadSuccess = (id) => {
    setJobId(id)
  }

  const handleUploadError = (message) => {
    setError(message)
    setStatus('error')
  }

  return (
    <div className="app-container">
      <header>
        <h1>AI Corporate Policy Auditor</h1>
        <p>Neuro-Symbolic Compliance Verification System (FOL + Z3 + LLM)</p>
      </header>

      <main>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        <section className="upload-section">
          <FileUpload
            disabled={busy}
            onUploadStart={handleUploadStart}
            onUploadSuccess={handleUploadSuccess}
            onUploadError={handleUploadError}
          />
        </section>

        <section className="console-section">
          <AuditConsole logs={logs} running={status === 'running'} />
        </section>

        <section className="report-section">
          <ReportViewer report={report} />
        </section>
      </main>
    </div>
  )
}

export default App