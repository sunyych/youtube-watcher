const STORAGE_KEYS = {
  baseUrl: 'backendBaseUrl',
  token: 'authToken',
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

function setBadge(tabId, text, color) {
  if (!tabId) return
  chrome.action.setBadgeText({ tabId, text: text || '' })
  if (color) chrome.action.setBadgeBackgroundColor({ tabId, color })
  if (text) setTimeout(() => chrome.action.setBadgeText({ tabId, text: '' }), 4000)
}

async function getSettings() {
  const data = await chrome.storage.sync.get([STORAGE_KEYS.baseUrl, STORAGE_KEYS.token])
  return {
    baseUrl: data[STORAGE_KEYS.baseUrl] || 'http://localhost:8000',
    token: data[STORAGE_KEYS.token] || null,
  }
}

async function ensureHostPermissionForUrl(url) {
  const u = new URL(url)
  const originPattern = `${u.protocol}//${u.hostname}/*`

  const has = await chromeCall(chrome.permissions.contains, { origins: [originPattern] })
  if (has) return true

  return await chromeCall(chrome.permissions.request, { origins: [originPattern] })
}

async function sendToBackendProcess(url, language) {
  const { baseUrl, token } = await getSettings()
  const granted = await ensureHostPermissionForUrl(baseUrl)
  if (!granted) throw new Error('Permission denied for backend host')

  const endpoint = `${baseUrl.replace(/\/$/, '')}/api/video/process`

  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify({ url, language: language || null }),
  })

  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`Backend error ${resp.status}: ${text || resp.statusText}`)
  }
  return await resp.json()
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: 'ytw_send_current',
      title: 'YouTube Watcher: send this page to backend download',
      contexts: ['page', 'link'],
    })
  })
})

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== 'ytw_send_current') return

  const url = info.linkUrl || tab?.url
  if (!url) return

  if (!isYouTubeUrl(url)) {
    setBadge(tab?.id, 'REC', '#6b7280')
    return
  }

  try {
    await sendToBackendProcess(url, null)
    setBadge(tab?.id, 'OK', '#047857')
  } catch (e) {
    setBadge(tab?.id, 'ERR', '#b91c1c')
  }
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== 'object') return false

  if (message.type === 'backend.processUrl') {
    ;(async () => {
      try {
        const result = await sendToBackendProcess(message.url, message.language)
        sendResponse({ ok: true, result })
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message || e) })
      }
    })()
    return true
  }

  if (message.type === 'backend.transcribeUrl') {
    ;(async () => {
      try {
        // Current backend pipeline already includes transcription (Whisper) as part of /api/video/process.
        const result = await sendToBackendProcess(message.url, message.language)
        sendResponse({ ok: true, result })
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message || e) })
      }
    })()
    return true
  }

  if (message.type === 'backend.ping') {
    ;(async () => {
      try {
        const { baseUrl } = await getSettings()
        sendResponse({ ok: true, baseUrl })
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message || e) })
      }
    })()
    return true
  }

  return false
})

