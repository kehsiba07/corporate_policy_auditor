import { useEffect, useRef } from 'react'

export default function AuditConsole({ logs, running }) {
  const consoleEndRef = useRef(null)

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="console">
      <h2>
        2. Audit Pipeline Console (Live)
        {running && (
          <span className="running-indicator" aria-label="Audit in progress">
            <span className="spinner" /> Running
          </span>
        )}
      </h2>
      <div className="console-body" role="log" aria-live="polite" aria-relevant="additions">
        {logs.length === 0 && <div className="log-info">Waiting for audit to start...</div>}
        {logs.map((log, i) => (
          <div key={i} className={log.type === 'error' ? 'log-error' : 'log-info'}>
            {`> ${log.type === 'error' ? 'ERROR: ' : ''}${log.message}`}
          </div>
        ))}
        <div ref={consoleEndRef} />
      </div>
    </div>
  )
}