const localHostnames = new Set(['127.0.0.1', 'localhost'])
const defaultApiBase =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ||
  (typeof window !== 'undefined' && localHostnames.has(window.location.hostname)
    ? 'http://127.0.0.1:8080'
    : '')

function resolveUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path
  }
  return defaultApiBase ? `${defaultApiBase}${path}` : path
}

export async function apiFetch(path, options = {}) {
  const response = await fetch(resolveUrl(path), options)
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const message = payload?.msg || payload?.message || response.statusText
    throw new Error(message)
  }

  if (payload?.code !== undefined && payload.code !== 0) {
    throw new Error(payload.msg || 'Request failed')
  }

  return payload?.data !== undefined ? payload.data : payload
}
