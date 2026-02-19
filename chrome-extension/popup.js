const STORAGE_KEYS = {
  baseUrl: 'backendBaseUrl',
  token: 'authToken',
  username: 'authUsername',
  userId: 'authUserId',
}

function chromeCall(fn, ...args) {
  return new Promise((resolve, reject) => {
    try {
      fn(...args, (result) => {
        const err = chrome.runtime?.lastError
        if (err) reject(new Error(err.message))
        else resolve(result)
      })
    } catch (e) {
      reject(e)
    }
  })
}

function setStatus(el, text, kind = '') {
  el.textContent = text || ''
  el.classList.remove('error', 'ok')
  if (kind) el.classList.add(kind)
}

function normalizeBaseUrl(input) {
  const trimmed = String(input || '').trim()
  if (!trimmed) return ''
  try {
    const u = new URL(trimmed)
    return u.origin
  } catch {
    return ''
  }
}

async function getSettings() {
  const data = await chrome.storage.sync.get([
    STORAGE_KEYS.baseUrl,
    STORAGE_KEYS.token,
    STORAGE_KEYS.username,
    STORAGE_KEYS.userId,
  ])
  return {
    baseUrl: data[STORAGE_KEYS.baseUrl] || 'http://localhost:8000',
    token: data[STORAGE_KEYS.token] || null,
    username: data[STORAGE_KEYS.username] || null,
    userId: data[STORAGE_KEYS.userId] || null,
  }
}

async function setSettings(partial) {
  await chrome.storage.sync.set(partial)
}

async function backendLogin(baseUrl, username, password) {
  const endpoint = `${baseUrl.replace(/\/$/, '')}/api/auth/login`
  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`Login failed ${resp.status}: ${text || resp.statusText}`)
  }
  return await resp.json()
}

async function ensureActiveTab() {
  const tabs = await chromeCall(chrome.tabs.query, { active: true, currentWindow: true })
  const tab = tabs[0]
  if (!tab?.id) throw new Error('No active tab')
  return tab
}

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

function isYouTubeVideoUrl(url) {
  try {
    const u = new URL(url)
    if (!isYouTubeUrl(u.href)) return false
    if (u.hostname === 'youtu.be') return Boolean(u.pathname && u.pathname !== '/')
    if (u.pathname.startsWith('/shorts/')) return true
    if (u.pathname === '/watch') return Boolean(u.searchParams.get('v'))
    return false
  } catch {
    return false
  }
}

function isYouTubeChannelPageUrl(url) {
  try {
    const u = new URL(url, 'https://www.youtube.com')
    if (!isYouTubeUrl(u.href)) return false
    if (u.pathname.startsWith('/channel/')) return true
    if (u.pathname.startsWith('/@')) return true
    if (u.pathname.startsWith('/c/')) return true
    return false
  } catch {
    return false
  }
}

async function ensureHostPermissionForBaseUrl(baseUrl) {
  const u = new URL(baseUrl)
  // Match patterns do not include port; grant all ports for this hostname.
  const originPattern = `${u.protocol}//${u.hostname}/*`

  const has = await chromeCall(chrome.permissions.contains, { origins: [originPattern] })
  if (has) return true

  return await chromeCall(chrome.permissions.request, { origins: [originPattern] })
}

function normalizeYouTubeUrl(raw) {
  try {
    const u = new URL(raw)
    if (!isYouTubeUrl(u.href)) return null
    // normalize shorts -> watch?v=
    if (u.pathname.startsWith('/shorts/')) {
      const id = u.pathname.split('/')[2]
      if (id) return `https://www.youtube.com/watch?v=${id}`
    }
    // normalize youtu.be -> watch?v=
    if (u.hostname === 'youtu.be') {
      const id = u.pathname.replace('/', '')
      if (id) return `https://www.youtube.com/watch?v=${id}`
    }
    // keep only relevant params for watch
    if (u.pathname === '/watch') {
      const v = u.searchParams.get('v')
      if (!v) return null
      return `https://www.youtube.com/watch?v=${v}`
    }
    // allow playlists page urls too (backend yt-dlp can handle)
    return u.href
  } catch {
    return null
  }
}

async function scanYouTubePage(tabId) {
  const injected = await chromeCall(chrome.scripting.executeScript, {
    target: { tabId },
    func: () => {
      const items = []

      const push = (url, title) => {
        if (!url) return
        items.push({ url, title: title || '' })
      }

      push(location.href, document.title || '')

      // Watch page video title anchor
      document.querySelectorAll('a#video-title, a#video-title-link, a[href*="watch?v="]').forEach((a) => {
        const href = a.getAttribute('href')
        if (!href) return
        const url = href.startsWith('http') ? href : new URL(href, location.origin).href
        const title =
          (a.getAttribute('title') || a.textContent || '')
            .replace(/\s+/g, ' ')
            .trim()
        push(url, title)
      })

      return items
    },
  })
  const result = injected?.[0]?.result

  const seen = new Set()
  const out = []
  for (const it of result || []) {
    try {
      const url = new URL(it.url, 'https://www.youtube.com').href
      seen.add(url)
    } catch {
      // ignore
    }
  }

  for (const it of result || []) {
    const normalized = (() => {
      try {
        const u = new URL(it.url, 'https://www.youtube.com')
        // normalize youtu.be
        if (u.hostname === 'youtu.be') {
          const id = u.pathname.replace('/', '')
          if (id) return `https://www.youtube.com/watch?v=${id}`
        }
        // normalize shorts
        if (u.hostname.includes('youtube.com') && u.pathname.startsWith('/shorts/')) {
          const id = u.pathname.split('/')[2]
          if (id) return `https://www.youtube.com/watch?v=${id}`
        }
        if (u.pathname === '/watch') {
          const v = u.searchParams.get('v')
          if (!v) return null
          return `https://www.youtube.com/watch?v=${v}`
        }
        return u.href
      } catch {
        return null
      }
    })()

    if (!normalized) continue
    if (seen.has(`__picked__${normalized}`)) continue
    seen.add(`__picked__${normalized}`)
    out.push({ url: normalized, title: it.title || '' })
  }

  // De-dupe while preserving order (prefer longer/meaningful titles)
  const map = new Map()
  for (const it of out) {
    const existing = map.get(it.url)
    if (!existing) map.set(it.url, it)
    else if ((it.title || '').length > (existing.title || '').length) map.set(it.url, it)
  }

  return Array.from(map.values())
}

function renderVideoList(container, videos) {
  container.innerHTML = ''
  if (!videos.length) {
    container.textContent = 'No YouTube links found on this page.'
    return
  }

  for (const v of videos) {
    const row = document.createElement('div')
    row.className = 'item'

    const cb = document.createElement('input')
    cb.type = 'checkbox'
    cb.checked = true
    cb.dataset.url = v.url
    cb.dataset.title = v.title || ''

    const meta = document.createElement('div')
    meta.className = 'meta'

    const name = document.createElement('div')
    name.className = 'name'
    name.textContent = v.title || '(no title)'

    const url = document.createElement('div')
    url.className = 'url'
    url.textContent = v.url

    meta.appendChild(name)
    meta.appendChild(url)

    row.appendChild(cb)
    row.appendChild(meta)

    container.appendChild(row)
  }
}

async function sendSelected(videosContainer, ytInfoEl) {
  const selected = Array.from(videosContainer.querySelectorAll('input[type="checkbox"]'))
    .filter((cb) => cb.checked)
    .map((cb) => cb.dataset.url)
    .filter(Boolean)

  if (selected.length === 0) {
    setStatus(ytInfoEl, 'No videos selected.', 'error')
    return
  }

  setStatus(ytInfoEl, `Sending ${selected.length} item(s) to backend...`)

  const results = []
  for (const url of selected) {
    const res = await chromeCall(chrome.runtime.sendMessage, { type: 'backend.processUrl', url, language: null })
    results.push({ url, res })
  }

  const okCount = results.filter((r) => r.res?.ok).length
  const failCount = results.length - okCount
  const lines = [`Done. OK=${okCount}, Failed=${failCount}`]
  for (const r of results) {
    if (!r.res?.ok) lines.push(`- ${r.url}: ${r.res?.error || 'unknown error'}`)
  }
  setStatus(ytInfoEl, lines.join('\n'), failCount ? 'error' : 'ok')
}

// Recording
let recorder = null
let recordChunks = []
let recordStream = null

function getTimestamp() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(
    d.getMinutes()
  )}-${pad(d.getSeconds())}`
}

async function startRecording(recStatusEl) {
  if (recorder) {
    setStatus(recStatusEl, 'Already recording.', 'error')
    return
  }

  setStatus(recStatusEl, 'Requesting tab capture...')
  const stream = await chromeCall(chrome.tabCapture.capture, { audio: true, video: true })
  if (!stream) throw new Error('Failed to capture tab')

  recordStream = stream
  recordChunks = []

  const mimeTypeCandidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ]
  const mimeType = mimeTypeCandidates.find((t) => MediaRecorder.isTypeSupported(t)) || ''

  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) recordChunks.push(e.data)
  }
  recorder.onstop = () => {
    // stop tracks after final data is available
    try {
      for (const t of recordStream?.getTracks?.() || []) t.stop()
    } catch {
      // ignore
    }
    recordStream = null
  }

  recorder.start(1000)
  setStatus(recStatusEl, 'Recording tab... (click “Stop & save” to finish)', 'ok')
}

async function stopRecording(recStatusEl) {
  if (!recorder) {
    setStatus(recStatusEl, 'Not recording.', 'error')
    return
  }

  setStatus(recStatusEl, 'Stopping...')
  await new Promise((resolve) => {
    recorder.addEventListener('stop', resolve, { once: true })
    recorder.stop()
  })

  const blob = new Blob(recordChunks, { type: 'video/webm' })
  recorder = null
  recordChunks = []

  if (!blob.size) {
    setStatus(recStatusEl, 'Recorded file is empty (可能是 DRM/保护内容限制)。', 'error')
    return
  }

  const filename = `recording_${getTimestamp()}.webm`
  const url = URL.createObjectURL(blob)
  try {
    await chromeCall(chrome.downloads.download, { url, filename, saveAs: true })
    setStatus(recStatusEl, `Saved: ${filename}`, 'ok')
  } finally {
    // Give the download a moment to start before revoking
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
}

function setBackendLoggedInUi({ loggedIn, username }) {
  const backendFieldsEl = document.getElementById('backendFields')
  const btnLoginEl = document.getElementById('btnLogin')
  const btnLogoutEl = document.getElementById('btnLogout')
  const optionsLinkEl = document.getElementById('backendOptionsLink')
  const usernameEl = document.getElementById('username')
  const passwordEl = document.getElementById('password')

  if (loggedIn) {
    if (backendFieldsEl) backendFieldsEl.style.display = 'none'
    if (btnLoginEl) btnLoginEl.style.display = 'none'
    if (optionsLinkEl) optionsLinkEl.style.display = 'none'
    if (btnLogoutEl) btnLogoutEl.style.display = ''
    if (passwordEl) passwordEl.value = ''
  } else {
    if (backendFieldsEl) backendFieldsEl.style.display = ''
    if (btnLoginEl) btnLoginEl.style.display = ''
    if (optionsLinkEl) optionsLinkEl.style.display = ''
    if (btnLogoutEl) btnLogoutEl.style.display = 'none'
    if (usernameEl && username) usernameEl.value = username
  }
}

async function init() {
  const authStatusEl = document.getElementById('authStatus')
  const ytInfoEl = document.getElementById('ytInfo')
  const recStatusEl = document.getElementById('recStatus')
  const baseUrlEl = document.getElementById('baseUrl')
  const usernameEl = document.getElementById('username')
  const passwordEl = document.getElementById('password')
  const videoListEl = document.getElementById('videoList')
  const btnSendCurrentTabEl = document.getElementById('btnSendCurrentTab')

  const { baseUrl, token, username } = await getSettings()
  baseUrlEl.value = baseUrl
  usernameEl.value = username || ''
  passwordEl.value = ''

  setStatus(authStatusEl, token ? `Logged in as ${username || '(unknown)'}` : 'Not logged in.', token ? 'ok' : '')
  setBackendLoggedInUi({ loggedIn: Boolean(token), username: username || '' })

  // If current tab is a YouTube video page, show "Send current tab"
  const channelSubscribeCard = document.getElementById('channelSubscribeCard')
  const btnSubscribeChannel = document.getElementById('btnSubscribeChannel')
  const subscribeStatusEl = document.getElementById('subscribeStatus')
  try {
    const tab = await ensureActiveTab()
    const normalized = tab.url ? normalizeYouTubeUrl(tab.url) : null
    if (tab.url && normalized && isYouTubeVideoUrl(tab.url)) {
      btnSendCurrentTabEl.style.display = ''
      btnSendCurrentTabEl.dataset.url = normalized
    } else {
      btnSendCurrentTabEl.style.display = 'none'
      btnSendCurrentTabEl.dataset.url = ''
    }
    if (tab.url && isYouTubeChannelPageUrl(tab.url)) {
      channelSubscribeCard.style.display = ''
      channelSubscribeCard.dataset.channelUrl = tab.url
    } else {
      channelSubscribeCard.style.display = 'none'
      channelSubscribeCard.dataset.channelUrl = ''
    }
  } catch {
    btnSendCurrentTabEl.style.display = 'none'
    btnSendCurrentTabEl.dataset.url = ''
    channelSubscribeCard.style.display = 'none'
    channelSubscribeCard.dataset.channelUrl = ''
  }

  btnSubscribeChannel.addEventListener('click', async () => {
    const channelUrl = channelSubscribeCard.dataset.channelUrl
    if (!channelUrl) {
      setStatus(subscribeStatusEl, 'Current tab is not a YouTube channel page.', 'error')
      return
    }
    const { baseUrl, token } = await getSettings()
    if (!token) {
      setStatus(subscribeStatusEl, 'Please log in first.', 'error')
      return
    }
    const granted = await ensureHostPermissionForBaseUrl(baseUrl)
    if (!granted) {
      setStatus(subscribeStatusEl, 'Permission denied for backend host.', 'error')
      return
    }
    setStatus(subscribeStatusEl, 'Subscribing...')
    try {
      const endpoint = `${baseUrl.replace(/\/$/, '')}/api/subscriptions`
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ channel_url: channelUrl }),
      })
      const data = await resp.json().catch(() => ({}))
      if (resp.status === 200) {
        setStatus(subscribeStatusEl, 'Already subscribed to this channel.', 'ok')
      } else if (resp.status === 201) {
        setStatus(subscribeStatusEl, 'Subscribed. New videos will be auto-downloaded twice daily.', 'ok')
      } else {
        setStatus(subscribeStatusEl, data.detail || `Error ${resp.status}`, 'error')
      }
    } catch (e) {
      setStatus(subscribeStatusEl, String(e?.message || e), 'error')
    }
  })

  btnSendCurrentTabEl.addEventListener('click', async () => {
    try {
      const url = btnSendCurrentTabEl.dataset.url
      if (!url) {
        setStatus(ytInfoEl, 'Current tab is not a YouTube video page.', 'error')
        return
      }

      const { baseUrl } = await getSettings()
      const granted = await ensureHostPermissionForBaseUrl(baseUrl)
      if (!granted) {
        setStatus(ytInfoEl, 'Permission denied for backend host.', 'error')
        return
      }

      setStatus(ytInfoEl, 'Sending current tab to backend...')
      const res = await chromeCall(chrome.runtime.sendMessage, { type: 'backend.processUrl', url, language: null })
      if (res?.ok) setStatus(ytInfoEl, 'Sent current tab.', 'ok')
      else setStatus(ytInfoEl, res?.error || 'Failed to send current tab.', 'error')
    } catch (e) {
      setStatus(ytInfoEl, String(e?.message || e), 'error')
    }
  })

  document.getElementById('btnLogin').addEventListener('click', async () => {
    try {
      setStatus(authStatusEl, 'Logging in...')

      const normalized = normalizeBaseUrl(baseUrlEl.value) || 'http://localhost:8000'
      baseUrlEl.value = normalized

      const granted = await ensureHostPermissionForBaseUrl(normalized)
      if (!granted) {
        setStatus(authStatusEl, 'Permission denied for backend host.', 'error')
        return
      }

      const u = String(usernameEl.value || '').trim()
      const p = String(passwordEl.value || '')
      if (!u || !p) {
        setStatus(authStatusEl, 'Username and password required.', 'error')
        return
      }

      const res = await backendLogin(normalized, u, p)
      await setSettings({
        [STORAGE_KEYS.baseUrl]: normalized,
        [STORAGE_KEYS.token]: res.access_token,
        [STORAGE_KEYS.username]: res.username,
        [STORAGE_KEYS.userId]: res.user_id,
      })
      passwordEl.value = ''
      setStatus(authStatusEl, `Logged in as ${res.username}`, 'ok')
      setBackendLoggedInUi({ loggedIn: true, username: res.username })
    } catch (e) {
      setStatus(authStatusEl, String(e?.message || e), 'error')
    }
  })

  document.getElementById('btnLogout').addEventListener('click', async () => {
    await setSettings({
      [STORAGE_KEYS.token]: null,
      [STORAGE_KEYS.username]: null,
      [STORAGE_KEYS.userId]: null,
    })
    setStatus(authStatusEl, 'Logged out.')
    setBackendLoggedInUi({ loggedIn: false, username: '' })
  })

  document.getElementById('btnScan').addEventListener('click', async () => {
    try {
      const tab = await ensureActiveTab()
      if (!tab.url || !isYouTubeUrl(tab.url)) {
        setStatus(ytInfoEl, 'Not a YouTube page. Use recording below for other sites.', 'error')
        renderVideoList(videoListEl, [])
        return
      }

      setStatus(ytInfoEl, 'Scanning...')
      const videos = await scanYouTubePage(tab.id)
      renderVideoList(videoListEl, videos)
      setStatus(ytInfoEl, `Found ${videos.length} link(s).`, 'ok')
    } catch (e) {
      setStatus(ytInfoEl, String(e?.message || e), 'error')
    }
  })

  document.getElementById('btnSendSelected').addEventListener('click', async () => {
    try {
      const { baseUrl } = await getSettings()
      const granted = await ensureHostPermissionForBaseUrl(baseUrl)
      if (!granted) {
        setStatus(ytInfoEl, 'Permission denied for backend host.', 'error')
        return
      }
      await sendSelected(videoListEl, ytInfoEl)
    } catch (e) {
      setStatus(ytInfoEl, String(e?.message || e), 'error')
    }
  })

  document.getElementById('btnStartRec').addEventListener('click', async () => {
    try {
      await startRecording(recStatusEl)
    } catch (e) {
      setStatus(recStatusEl, String(e?.message || e), 'error')
    }
  })

  document.getElementById('btnStopRec').addEventListener('click', async () => {
    try {
      await stopRecording(recStatusEl)
    } catch (e) {
      setStatus(recStatusEl, String(e?.message || e), 'error')
    }
  })
}

void init()

