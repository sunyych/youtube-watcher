const STORAGE_KEYS = {
  baseUrl: 'backendBaseUrl',
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

async function load() {
  const data = await chrome.storage.sync.get([STORAGE_KEYS.baseUrl])
  const baseUrl = data[STORAGE_KEYS.baseUrl] || 'http://localhost:8000'
  document.getElementById('baseUrl').value = baseUrl
}

async function save() {
  const el = document.getElementById('baseUrl')
  const status = document.getElementById('status')
  status.textContent = ''

  const baseUrl = normalizeBaseUrl(el.value)
  if (!baseUrl) {
    status.style.color = '#b91c1c'
    status.textContent = 'Invalid URL. Example: http://localhost:8000'
    return
  }

  await chrome.storage.sync.set({ [STORAGE_KEYS.baseUrl]: baseUrl })
  status.style.color = '#047857'
  status.textContent = 'Saved'
}

document.getElementById('btnSave').addEventListener('click', () => {
  void save()
})

void load()

