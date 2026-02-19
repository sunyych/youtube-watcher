import fs from 'node:fs/promises'
import path from 'node:path'

const projectRoot = path.resolve(new URL('.', import.meta.url).pathname, '..') // frontend/
const workspaceRoot = path.resolve(projectRoot, '..') // repo root
const src = path.join(workspaceRoot, 'chrome-extension.crx')
const distDir = path.join(projectRoot, 'dist')
const publicDir = path.join(projectRoot, 'public')
const destDist = path.join(distDir, 'chrome-extension.crx')
const destPublic = path.join(publicDir, 'chrome-extension.crx')

async function copyToDest(srcPath, destPath, label) {
  await fs.mkdir(path.dirname(destPath), { recursive: true })
  await fs.copyFile(srcPath, destPath)
  console.log(`[copy-extension-crx] ${label}: ${destPath}`)
}

async function main() {
  try {
    await fs.access(src)
  } catch {
    console.warn(`[copy-extension-crx] Source not found: ${src}`)
    return
  }

  try {
    await copyToDest(src, destDist, 'dist')
    await copyToDest(src, destPublic, 'public (for dev server)')
  } catch (err) {
    console.error('[copy-extension-crx] Failed to copy', err)
    process.exitCode = 1
  }
}

await main()
