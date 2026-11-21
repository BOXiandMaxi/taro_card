// Store only reading IDs. Private access stays in the per-reading HttpOnly cookie.
const KEY = 'tarot-guest-history'
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const LIMIT = 300

export function guestReadingIds() {
  let ids = []
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]')
    ids = Array.isArray(saved) ? saved.filter(id => typeof id === 'string' && UUID_V4.test(id)) : []
  } catch { /* Keep the current reading available if stored history is malformed. */ }
  try {
    if (sessionStorage.getItem('tarot-identity') === 'guest') {
      const pending = JSON.parse(sessionStorage.getItem('tarot-pending-reading') || 'null')
      if (pending?.id && UUID_V4.test(pending.id)) ids.unshift(pending.id)
    }
  } catch { /* Saved history still remains available. */ }
  return [...new Set(ids)].slice(0, LIMIT)
}

export function rememberGuestReading(id) {
  if (!UUID_V4.test(id)) return
  try {
    const ids = [id, ...guestReadingIds().filter(saved => saved !== id)].slice(0, LIMIT)
    localStorage.setItem(KEY, JSON.stringify(ids))
  } catch { /* Reading access still works in this tab if storage is unavailable. */ }
}

export function forgetGuestReading(id) {
  try {
    const pending = JSON.parse(sessionStorage.getItem('tarot-pending-reading') || 'null')
    if (pending?.id === id) sessionStorage.removeItem('tarot-pending-reading')
    localStorage.setItem(KEY, JSON.stringify(guestReadingIds().filter(saved => saved !== id)))
  } catch { /* The server remains authoritative for deleted or expired readings. */ }
}
