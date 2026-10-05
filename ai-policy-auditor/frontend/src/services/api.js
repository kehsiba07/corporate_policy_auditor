const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

export async function uploadPolicy(file) {
  const formData = new FormData()
  formData.append('file', file)

  let res
  try {
    res = await fetch(`${API_URL}/api/audit`, { method: 'POST', body: formData })
  } catch {
    throw new Error('Cannot reach the server. Is the backend running?')
  }

  if (!res.ok) {
    let detail = `Upload failed (HTTP ${res.status}).`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json()
}

/**
 * Opens a subscription to a job. Returns { close }.
 * close() is safe to call while the socket is still connecting (React StrictMode).
 */
export function openAuditSocket(jobId, { onMessage, onError, onClose }) {
  const socket = new WebSocket(`${WS_URL}/ws/audit/${jobId}`)

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data && typeof data.type === 'string') onMessage?.(data)
    } catch {
      onMessage?.({ type: 'error', message: 'Received a malformed message from the server.' })
    }
  }
  socket.onerror = (event) => onError?.(event)
  socket.onclose = (event) => onClose?.(event)

  return {
    close() {
      socket.onmessage = null
      if (socket.readyState === WebSocket.CONNECTING) {
        socket.onopen = () => socket.close()
      } else if (socket.readyState === WebSocket.OPEN) {
        socket.close()
      }
    },
  }
}