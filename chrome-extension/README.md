## YouTube Watcher Chrome Extension (MV3)

### What it does
- **YouTube**: scan current page for video links, select, then send to your backend `POST /api/video/process` (yt-dlp download).
- **Other sites**: record the **current tab video + tab audio** via `tabCapture`, then save as `.webm`.

### Install (unpacked)
1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select this folder: `youtube-watcher/chrome-extension/`

### Configure backend
- Click the extension icon → set **Base URL** (default `http://localhost:8000`)
- Login with your backend username/password (uses `/api/auth/login`)
- The extension will ask permission for your backend host (via optional host permissions).

### Notes / limitations
- Some sites (especially **DRM/protected** content) may record black screen or silent audio — this is a browser limitation.
