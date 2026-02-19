// Inject a "Transcribe" item into YouTube's in-page 3-dot menu, then send to backend.
// MV3 content script (runs on https://www.youtube.com/*).

function isYouTubeUrl(url) {
  try {
    const u = new URL(url)
    return (
      u.hostname === 'www.youtube.com' ||
      u.hostname === 'youtube.com' ||
      u.hostname === 'm.youtube.com' ||
      u.hostname === 'youtu.be'
    )
  } catch {
    return false
  }
}

function normalizeYouTubeUrl(raw) {
  try {
    // Avoid relying on the page's `location` proxy; use a stable base.
    const u = new URL(raw, 'https://www.youtube.com')
    if (!isYouTubeUrl(u.href)) return null

    // normalize shorts -> watch?v=
    if (u.hostname.includes('youtube.com') && u.pathname.startsWith('/shorts/')) {
      const id = u.pathname.split('/')[2]
      if (id) return `https://www.youtube.com/watch?v=${id}`
    }

    // normalize youtu.be -> watch?v=
    if (u.hostname === 'youtu.be') {
      const id = u.pathname.replace('/', '')
      if (id) return `https://www.youtube.com/watch?v=${id}`
    }

    if (u.pathname === '/watch') {
      const v = u.searchParams.get('v')
      if (!v) return null
      return `https://www.youtube.com/watch?v=${v}`
    }

    // Fallback: keep as-is (backend yt-dlp can handle many youtube urls)
    return u.href
  } catch {
    return null
  }
}

function toast(text, kind) {
  const id = 'ytw_transcribe_toast'
  const old = document.getElementById(id)
  if (old) old.remove()

  const el = document.createElement('div')
  el.id = id
  el.textContent = text
  el.style.position = 'fixed'
  el.style.zIndex = '2147483647'
  el.style.right = '16px'
  el.style.bottom = '16px'
  el.style.maxWidth = '360px'
  el.style.padding = '10px 12px'
  el.style.borderRadius = '10px'
  el.style.fontSize = '13px'
  el.style.lineHeight = '1.35'
  el.style.boxShadow = '0 10px 25px rgba(0,0,0,0.25)'
  el.style.color = '#fff'
  el.style.background = kind === 'error' ? '#b91c1c' : '#047857'
  el.style.fontFamily =
    'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"'

  document.documentElement.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

function absoluteUrlFromHref(href) {
  try {
    // Use a stable base instead of `location.origin` (YouTube uses lots of proxies/isolations).
    return new URL(href, 'https://www.youtube.com').href
  } catch {
    return null
  }
}

function isYouTubeVideoPageUrl(raw) {
  try {
    const u = new URL(raw, 'https://www.youtube.com')
    if (!isYouTubeUrl(u.href)) return false
    if (u.hostname === 'youtu.be') return Boolean(u.pathname && u.pathname !== '/')
    if (u.pathname.startsWith('/shorts/')) return true
    if (u.pathname === '/watch') return Boolean(u.searchParams.get('v'))
    return false
  } catch {
    return false
  }
}

function findAssociatedVideoUrl(fromEl) {
  if (!fromEl) return null

  const linkSelectors = [
    'a#thumbnail[href]',
    'a#video-title-link[href]',
    'a#video-title[href]',
    'a[href*="watch?v="]',
    'a[href^="/shorts/"]',
    'a[href^="https://youtu.be/"]',
  ]

  const findLinkIn = (root) => {
    if (!root?.querySelector) return null
    for (const sel of linkSelectors) {
      const a = root.querySelector(sel)
      const href = a?.getAttribute?.('href')
      if (href) return absoluteUrlFromHref(href)
    }
    return null
  }

  // Common containers for a video card/row. (Feed uses ytd-rich-grid-media)
  const container =
    fromEl.closest?.('ytd-rich-grid-media') ||
    fromEl.closest?.('ytd-rich-item-renderer') ||
    fromEl.closest?.('ytd-video-renderer') ||
    fromEl.closest?.('ytd-grid-video-renderer') ||
    fromEl.closest?.('ytd-compact-video-renderer') ||
    fromEl.closest?.('ytd-playlist-video-renderer') ||
    fromEl.closest?.('ytd-reel-item-renderer') ||
    fromEl.closest?.('ytd-reel-video-renderer') ||
    fromEl.closest?.('ytd-watch-next-secondary-results-renderer') ||
    fromEl.closest?.('ytd-watch-flexy') ||
    fromEl

  // Try within the nearest container.
  const direct = findLinkIn(container)
  if (direct) return direct

  // Fallback: walk up a few ancestors and try again (YouTube DOM varies a lot).
  let cur = container
  for (let i = 0; i < 12 && cur; i++) {
    const found = findLinkIn(cur)
    if (found) return found
    cur = cur.parentElement
  }

  return null
}

let lastMenuVideoUrl = null

function captureMenuTriggerUrl(e) {
  const t = e.target
  if (!t) return

  // Heuristic: YouTube 3-dot "action menu" button lives inside ytd-menu-renderer.
  const inMenuRenderer = t.closest?.('ytd-menu-renderer')
  if (!inMenuRenderer) return

  // Reduce false positives: only when clicking on an icon button-ish element.
  const clickedButtonish =
    t.closest?.('button') ||
    t.closest?.('yt-icon-button') ||
    t.closest?.('tp-yt-paper-icon-button') ||
    t.closest?.('[role="button"]')
  if (!clickedButtonish) return

  // Use composedPath to cross shadow DOM boundaries.
  const path = typeof e.composedPath === 'function' ? e.composedPath() : []
  const candidates = [clickedButtonish, t, ...path].filter(Boolean)

  for (const node of candidates) {
    if (!(node instanceof Element)) continue
    const url = findAssociatedVideoUrl(node)
    const normalized = url ? normalizeYouTubeUrl(url) : null
    if (normalized && isYouTubeVideoPageUrl(normalized)) {
      lastMenuVideoUrl = normalized
      return
    }
  }
}

// Capture early: YouTube often opens menus on pointerdown.
document.addEventListener('pointerdown', captureMenuTriggerUrl, true)
document.addEventListener('click', captureMenuTriggerUrl, true)
document.addEventListener(
  'keydown',
  (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    captureMenuTriggerUrl(e)
  },
  true
)

function makeTranscribeItem(templateItem) {
  const item = templateItem.cloneNode(true)
  item.setAttribute('data-ytw-transcribe', '1')

  const titleEl = item.querySelector?.('span.yt-list-item-view-model__title')
  if (titleEl) titleEl.textContent = 'Transcribe'

  // Ensure clickable.
  item.setAttribute('role', 'menuitem')
  item.setAttribute('tabindex', '0')

  const onActivate = async (evt) => {
    // Keep menu behavior; but avoid triggering YouTube's original action if we cloned one.
    evt.stopPropagation()
    evt.preventDefault()

    // Only fall back to current page when it is actually a video page.
    const fallback = isYouTubeVideoPageUrl(location.href) ? normalizeYouTubeUrl(location.href) : null
    const url = lastMenuVideoUrl || fallback
    if (!url) {
      toast('No matching video URL found for this menu item.', 'error')
      return
    }

    toast(`Sending to backend…\n${url}`)
    try {
      const res = await chrome.runtime.sendMessage({ type: 'backend.transcribeUrl', url, language: null })
      if (res?.ok) toast('Queued for transcription.', 'ok')
      else toast(res?.error || 'Failed to queue transcription.', 'error')
    } catch (err) {
      toast(String(err?.message || err), 'error')
    }
  }

  item.addEventListener('click', onActivate, true)
  item.addEventListener(
    'keydown',
    (evt) => {
      if (evt.key === 'Enter' || evt.key === ' ') void onActivate(evt)
    },
    true
  )

  return item
}

function tryInject() {
  const listbox = document.querySelector('ytd-popup-container tp-yt-iron-dropdown yt-list-view-model[role="listbox"]')
  if (!listbox) return
  if (listbox.querySelector('[data-ytw-transcribe="1"]')) return

  const templateItem = listbox.querySelector('yt-list-item-view-model')
  if (!templateItem) return

  const item = makeTranscribeItem(templateItem)
  // Insert near the top for visibility.
  listbox.insertBefore(item, listbox.firstChild)
}

// Observe DOM changes since the menu is rendered dynamically.
const observer = new MutationObserver(() => {
  tryInject()
})
observer.observe(document.documentElement, { childList: true, subtree: true })

// Initial attempt (in case menu already exists)
tryInject()

