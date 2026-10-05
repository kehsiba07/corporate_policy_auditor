import { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'

const SEVERITY_ORDER = { High: 3, Medium: 2, Low: 1 }

const COLUMNS = [
  { key: 'rank', label: 'Rank' },
  { key: 'severity', label: 'Severity' },
  { key: 'risk_score', label: 'Risk' },
  { key: 'policy_id', label: 'Policy' },
  { key: 'transaction_id', label: 'Transaction' },
  { key: 'amount', label: 'Amount' },
  { key: 'approver_role', label: 'Approver' },
]

function sortValue(v, key) {
  if (key === 'severity') return SEVERITY_ORDER[v.severity] || 0
  const value = v[key]
  return typeof value === 'string' ? value.toLowerCase() : value ?? 0
}

function formatPage(page) {
  return page ? ` (p. ${page})` : ''
}

export default function ReportViewer({ report }) {
  const [sort, setSort] = useState({ key: 'rank', dir: 'asc' })

  const violations = useMemo(() => {
    const rows = [...(report?.violations || [])]
    rows.sort((a, b) => {
      const av = sortValue(a, sort.key)
      const bv = sortValue(b, sort.key)
      if (av < bv) return sort.dir === 'asc' ? -1 : 1
      if (av > bv) return sort.dir === 'asc' ? 1 : -1
      return 0
    })
    return rows
  }, [report, sort])

  if (!report) return null

  const toggleSort = (key) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: key === 'rank' ? 'asc' : 'desc' }
    )

  const arrow = (key) => (sort.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '')

  return (
    <div className="report-viewer">
      <h2>3. Risk Assessment & Compliance Report</h2>

      <p className="report-meta">
        {report.policy_count} policies · {report.transaction_count} transactions ·{' '}
        {report.violations.length} violation(s) · {report.conflicts.length} policy conflict(s)
      </p>

      <div className="report-content">
        <ReactMarkdown>{report.report_markdown}</ReactMarkdown>
      </div>

      {report.warnings?.length > 0 && (
        <div className="warning-box">
          <h3>Extraction & verification warnings</h3>
          <ul>
            {report.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {report.conflicts?.length > 0 && (
        <div className="conflicts">
          <h3>Policy Conflicts (Z3 unsat core)</h3>
          <ul>
            {report.conflicts.map((c, i) => (
              <li key={i}>
                <strong>{c.policy_ids.join(' ↔ ')}</strong>: {c.reason}
                {c.unsat_core?.length > 0 && (
                  <div className="proof">Proof: {c.unsat_core.join(', ')}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {violations.length > 0 && (
        <div className="violations-table">
          <h3>Formal Logic Violations (Z3 Prover)</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {COLUMNS.map((col) => (
                    <th key={col.key}>
                      <button type="button" className="sort-btn" onClick={() => toggleSort(col.key)}>
                        {col.label}
                        {arrow(col.key)}
                      </button>
                    </th>
                  ))}
                  <th>Reasoning</th>
                  <th>Sources</th>
                </tr>
              </thead>
              <tbody>
                {violations.map((v) => (
                  <tr key={`${v.policy_id}-${v.transaction_id}`}>
                    <td>{v.rank}</td>
                    <td>
                      <span className={`badge badge-${v.severity.toLowerCase()}`}>{v.severity}</span>
                    </td>
                    <td>{v.risk_score}</td>
                    <td>{v.policy_id}</td>
                    <td>{v.transaction_id}</td>
                    <td>${Number(v.amount).toLocaleString()}</td>
                    <td>{v.approver_role || 'unknown'}</td>
                    <td>
                      <div>{v.explanation}</div>
                      {v.unsat_core?.length > 0 && (
                        <details className="proof">
                          <summary>Z3 proof (unsat core)</summary>
                          <ul>
                            {v.unsat_core.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </td>
                    <td className="citations">
                      <div>
                        <strong>Policy{formatPage(v.policy_page)}:</strong> “{v.policy_quote}”
                      </div>
                      <div>
                        <strong>Transaction{formatPage(v.transaction_page)}:</strong> “
                        {v.transaction_quote}”
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}