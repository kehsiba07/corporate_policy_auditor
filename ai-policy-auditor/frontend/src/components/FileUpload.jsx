import { useState } from 'react'
import { uploadPolicy } from '../services/api'

export default function FileUpload({ disabled, onUploadStart, onUploadSuccess, onUploadError }) {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file || disabled || loading) return

    setLoading(true)
    onUploadStart?.()
    try {
      const data = await uploadPolicy(file)
      onUploadSuccess?.(data.job_id)
    } catch (err) {
      onUploadError?.(err.message || 'Upload failed.')
    } finally {
      setLoading(false)
    }
  }

  const blocked = disabled || loading

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <h2>1. Upload Policy & Organizational Data (PDF)</h2>
      <input
        type="file"
        accept=".pdf,application/pdf"
        onChange={(e) => setFile(e.target.files[0] || null)}
        disabled={blocked}
        required
      />
      <button type="submit" disabled={blocked || !file}>
        {loading ? 'Uploading...' : disabled ? 'Audit running...' : 'Start Audit'}
      </button>
    </form>
  )
}