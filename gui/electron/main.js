const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const { exec, execFile, spawn } = require('child_process')

// __dirname is gui/electron, so the repo root is two levels up.
const repoRoot = path.resolve(__dirname, '..', '..')
const dataDir = path.join(repoRoot, 'data')
const profilesDir = path.join(dataDir, 'profiles')

let setupChild = null

function createWindow () {
  const win = new BrowserWindow({
    width: 720,
    height: 560,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    }
  })

  win.loadFile(path.join(__dirname, 'index.html'))
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit()
})

function pythonBin () {
  return process.platform === 'win32' ? 'python' : 'python3'
}

function runPythonScript (script, args) {
  return new Promise((resolve) => {
    execFile(pythonBin(), [script, ...args], { cwd: repoRoot }, (err, stdout, stderr) => {
      if (err) {
        resolve({ ok: false, error: (stderr || String(err)).trim().slice(0, 2000) })
      } else {
        resolve({ ok: true, stdout: (stdout || '').trim().slice(0, 8000), stderr: (stderr || '').trim().slice(0, 2000) })
      }
    })
  })
}

function validateProfileName (name) {
  if (typeof name !== 'string') return 'Profile name must be text.'
  const trimmed = name.trim()
  if (!trimmed) return 'Profile name cannot be empty.'
  if (trimmed.includes('/') || trimmed.includes('\\')) return 'Profile name cannot contain path separators.'
  if (trimmed === '.' || trimmed === '..' || trimmed.includes('..')) return 'Profile name cannot contain traversal segments.'
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(trimmed) || trimmed.endsWith('.')) {
    return 'Use letters, digits, dashes, underscores, and internal periods; start with a letter or digit.'
  }
  const reserved = new Set(['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'])
  if (reserved.has(trimmed.split('.')[0].toUpperCase())) return 'That name is reserved by Windows.'
  return null
}

function listProfilesLocal () {
  try {
    if (!fs.existsSync(profilesDir)) return []
    return fs.readdirSync(profilesDir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => ({ name: d.name, path: path.join(profilesDir, d.name) }))
      .sort((a, b) => a.name.localeCompare(b.name))
  } catch (e) {
    return { error: String(e) }
  }
}

function getActiveProfile () {
  try {
    const p = path.join(dataDir, 'active-profile.json')
    if (!fs.existsSync(p)) return null
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'))
    return typeof raw.active === 'string' ? raw.active : null
  } catch {
    return null
  }
}

function tailFile (filePath, maxLines = 30, maxBytes = 16 * 1024) {
  try {
    if (!fs.existsSync(filePath)) return { exists: false, path: filePath, lines: null, message: `Not found: ${path.basename(filePath)}` }
    const stat = fs.statSync(filePath)
    const fd = fs.openSync(filePath, 'r')
    const toRead = Math.min(stat.size, maxBytes)
    const buf = Buffer.alloc(toRead)
    fs.readSync(fd, buf, 0, toRead, Math.max(stat.size - toRead, 0))
    fs.closeSync(fd)
    const lines = buf.toString('utf8').split(/\r?\n/).slice(-maxLines)
    return { exists: true, path: filePath, lines, size: stat.size, truncated: stat.size > maxBytes }
  } catch (e) {
    return { exists: false, path: filePath, lines: null, message: `Cannot read ${path.basename(filePath)}: ${e.message}` }
  }
}

function findRuntimeDir () {
  const runtimesRoot = path.join(repoRoot, '.cache', 'runtimes')
  try {
    if (!fs.existsSync(runtimesRoot)) {
      return process.platform === 'win32'
        ? path.join(runtimesRoot, 'windows-x64')
        : path.join(runtimesRoot, 'linux-x64')
    }
    const dirs = fs.readdirSync(runtimesRoot).map((n) => path.join(runtimesRoot, n))
    const want = process.platform === 'win32' ? 'windows' : (process.platform === 'darwin' ? 'macos' : 'linux')
    const match = dirs.find((d) => d.toLowerCase().includes(want))
    return match || dirs[0]
  } catch {
    return path.join(runtimesRoot, 'windows-x64')
  }
}

ipcMain.handle('launch-hermes', async (_evt, options = {}) => {
  const profile = typeof options.profile === 'string' ? options.profile.trim() : ''
  if (profile) {
    const bad = validateProfileName(profile)
    if (bad) return { status: 'error', error: bad }
  }
  const quote = (s) => `"${s}"`
  const launch = (cmd) => new Promise((resolve) => {
    exec(cmd, { cwd: repoRoot }, (err) => {
      if (err) resolve({ status: 'error', error: String(err).slice(0, 1000) })
      else resolve({ status: 'started', profile: profile || null })
    })
  })
  if (process.platform === 'win32') {
    const launchBat = path.join(repoRoot, 'launch.bat')
    const args = profile ? ` /profile ${quote(profile)}` : ''
    return launch(`${quote(launchBat)}${args}`)
  }
  const launchSh = path.join(repoRoot, 'launch.sh')
  const args = profile ? ` --profile ${quote(profile)}` : ''
  return launch(`bash ${quote(launchSh)}${args}`)
})

ipcMain.handle('open-data-folder', async () => {
  try {
    const r = await shell.openPath(dataDir)
    if (r) return { status: 'error', error: r }
    return { status: 'opened' }
  } catch (e) {
    return { status: 'error', error: String(e) }
  }
})

ipcMain.handle('run-doctor', async () => {
  const python = pythonBin()
  const script = path.join(repoRoot, 'tools', 'doctor', 'export_health.py')

  const result = await new Promise((resolve) => {
    exec(`"${python}" "${script}"`, { cwd: repoRoot, timeout: 60000 }, (err, stdout, stderr) => {
      if (err) {
        resolve({ ok: false, error: (stderr || String(err)).trim().slice(0, 2000), stdout: (stdout || '').slice(0, 1000) })
      } else {
        resolve({ ok: true, stdout: (stdout || '').slice(0, 1000) })
      }
    })
  })

  // Open dashboard window (even on exporter failure so the error is visible).
  try {
    const dash = new BrowserWindow({
      width: 960,
      height: 760,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        nodeIntegration: false,
        contextIsolation: true,
      }
    })
    dash.loadFile(path.join(__dirname, 'dashboard.html'))
  } catch (e) {
    return { status: 'error', error: `Could not open dashboard: ${e.message}`, exporter: result }
  }

  if (!result.ok) {
    return { status: 'dashboard-opened-with-errors', exporter_err: result.error }
  }
  return { status: 'dashboard-opened' }
})

// Provide an IPC method for the renderer to request the health JSON
ipcMain.handle('get-health-report', async () => {
  try {
    const reportPath = path.join(repoRoot, 'data', 'health.json')
    if (!fs.existsSync(reportPath)) {
      return { error: 'No health report yet. Press “Refresh health” to generate data/health.json.' }
    }
    const raw = fs.readFileSync(reportPath, 'utf8')
    return JSON.parse(raw)
  } catch (e) {
    return { error: `Cannot read health report: ${e.message}` }
  }
})

ipcMain.handle('list-profiles', async () => {
  const local = listProfilesLocal()
  if (local && local.error) return { ok: false, error: local.error }
  return { ok: true, profiles: local, active: getActiveProfile() }
})

ipcMain.handle('create-profile', async (_evt, name) => {
  const bad = validateProfileName(name)
  if (bad) return { ok: false, error: bad }
  const script = path.join(repoRoot, 'tools', 'profiles', 'profile_manager.py')
  const res = await runPythonScript(script, ['create', name.trim()])
  if (!res.ok) return { ok: false, error: res.error || 'Create failed.' }
  return { ok: true, message: res.stdout }
})

ipcMain.handle('delete-profile', async (_evt, payload = {}) => {
  const name = typeof payload.name === 'string' ? payload.name.trim() : ''
  const confirmed = payload.confirmed === true
  const typed = typeof payload.typedName === 'string' ? payload.typedName.trim() : ''
  if (!name) return { ok: false, error: 'Select a profile to delete.' }
  const bad = validateProfileName(name)
  if (bad) return { ok: false, error: bad }
  // Require explicit two-part confirmation: checkbox + re-typed name.
  if (!confirmed) return { ok: false, error: 'Deletion requires explicit confirmation.' }
  if (typed !== name) return { ok: false, error: `Type the profile name (“${name}”) to confirm deletion.` }
  const script = path.join(repoRoot, 'tools', 'profiles', 'profile_manager.py')
  const res = await runPythonScript(script, ['delete', name])
  if (!res.ok) return { ok: false, error: res.error || 'Delete failed.' }
  // If the deleted profile was active, clear the pointer.
  try {
    if (getActiveProfile() === name) fs.rmSync(path.join(dataDir, 'active-profile.json'), { force: true })
  } catch { /* ignore */ }
  return { ok: true, message: res.stdout }
})

ipcMain.handle('switch-profile', async (_evt, name) => {
  const trimmed = typeof name === 'string' ? name.trim() : ''
  if (!trimmed) {
    try { fs.rmSync(path.join(dataDir, 'active-profile.json'), { force: true }) } catch { /* ignore */ }
    return { ok: true, active: null }
  }
  const bad = validateProfileName(trimmed)
  if (bad) return { ok: false, error: bad }
  if (!fs.existsSync(path.join(profilesDir, trimmed))) {
    return { ok: false, error: `Profile “${trimmed}” does not exist.` }
  }
  try {
    fs.mkdirSync(dataDir, { recursive: true })
    fs.writeFileSync(path.join(dataDir, 'active-profile.json'), JSON.stringify({ active: trimmed }, null, 2))
    return { ok: true, active: trimmed }
  } catch (e) {
    return { ok: false, error: `Cannot save active profile: ${e.message}` }
  }
})

ipcMain.handle('get-setup-progress', async () => {
  const runtimeDir = findRuntimeDir()
  let progress = null
  try {
    const p = path.join(runtimeDir, 'setup-progress.json')
    if (fs.existsSync(p)) progress = JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch (e) {
    progress = { error: `Cannot parse setup-progress.json: ${e.message}` }
  }
  const ready = fs.existsSync(path.join(runtimeDir, 'ready.flag'))
  const cancelled = fs.existsSync(path.join(runtimeDir, 'setup-cancelled.flag'))
  const logFile = process.platform === 'win32'
    ? path.join(runtimeDir, 'install.log')
    : path.join(runtimeDir, 'setup.log')
  return {
    ok: true,
    runtimeDir,
    ready,
    cancelled,
    running: setupChild !== null,
    progress,
    log: tailFile(logFile),
    launchLog: tailFile(path.join(repoRoot, '.cache', 'logs', 'launch.log'), 20),
  }
})

ipcMain.handle('run-setup', async () => {
  if (setupChild) return { ok: false, error: 'Setup is already running.' }
  const runtimeDir = findRuntimeDir()
  try { fs.mkdirSync(runtimeDir, { recursive: true }) } catch { /* ignore */ }
  // Clear a stale cancellation marker; a fresh run is recoverable by design.
  try { fs.rmSync(path.join(runtimeDir, 'setup-cancelled.flag'), { force: true }) } catch { /* ignore */ }
  const script = process.platform === 'win32'
    ? ['powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(repoRoot, 'scripts', 'setup-windows.ps1'), '-Root', repoRoot]]
    : ['bash', [path.join(repoRoot, 'scripts', 'setup-unix.sh'), repoRoot]]
  return new Promise((resolve) => {
    try {
      setupChild = spawn(script[0], script[1], { cwd: repoRoot })
    } catch (e) {
      setupChild = null
      resolve({ ok: false, error: `Cannot start setup: ${e.message}` })
      return
    }
    setupChild.on('error', (err) => {
      setupChild = null
      resolve({ ok: false, error: `Setup failed to start: ${err.message}` })
    })
    setupChild.on('exit', (code) => {
      setupChild = null
      if (code === 0) resolve({ ok: true, message: 'Setup completed.' })
      else resolve({ ok: false, error: `Setup exited with code ${code}. Logs are preserved — re-run setup to resume.` })
    })
    // Resolve immediately as "started"; progress is polled via get-setup-progress.
    setTimeout(() => {
      if (setupChild) resolve({ ok: true, message: 'Setup started.' })
    }, 300)
  })
})

ipcMain.handle('cancel-setup', async () => {
  if (!setupChild) return { ok: false, error: 'No setup run to cancel.' }
  try {
    setupChild.kill('SIGTERM')
    const runtimeDir = findRuntimeDir()
    setTimeout(() => {
      try {
        if (setupChild) setupChild.kill('SIGKILL')
      } catch { /* ignore */ }
    }, 3000).unref?.()
    return { ok: true, message: 'Cancellation requested. Logs are preserved; the next launch will resume setup.' }
  } catch (e) {
    return { ok: false, error: `Cannot cancel setup: ${e.message}` }
  }
})
