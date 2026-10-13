const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const { exec } = require('child_process')

function createWindow () {
  const win = new BrowserWindow({
    width: 600,
    height: 380,
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

// __dirname is gui/electron, so the repo root is two levels up.
const repoRoot = path.resolve(__dirname, '..', '..')

ipcMain.handle('launch-hermes', async () => {
  if (process.platform === 'win32') {
    const launchBat = path.join(repoRoot, 'launch.bat')
    exec(`"${launchBat}"`, { cwd: repoRoot }, (err) => {
      if (err) {
        console.error(err)
      }
    })
    return { status: 'started' }
  }
  const launchSh = path.join(repoRoot, 'launch.sh')
  exec(`bash "${launchSh}"`, { cwd: repoRoot }, (err) => {
    if (err) {
      console.error(err)
    }
  })
  return { status: 'started' }
})

ipcMain.handle('open-data-folder', async () => {
  const dataPath = path.join(repoRoot, 'data')
  shell.openPath(dataPath)
  return { status: 'opened' }
})

ipcMain.handle('run-doctor', async () => {
  // Run the JSON exporter and then open a graphical dashboard window.
  const python = process.platform === 'win32' ? 'python' : 'python3'
  const script = path.join(repoRoot, 'tools', 'doctor', 'export_health.py')

  return new Promise((resolve) => {
    exec(`"${python}" "${script}"`, { cwd: repoRoot }, (err, stdout, stderr) => {
      if (err) {
        console.error('Health exporter failed:', err)
      }

      // Open dashboard window
      const dash = new BrowserWindow({
        width: 900,
        height: 700,
        webPreferences: {
          preload: path.join(__dirname, 'preload.js'),
          nodeIntegration: false,
          contextIsolation: true,
        }
      })

      dash.loadFile(path.join(__dirname, 'dashboard.html'))

      resolve({ status: 'dashboard-opened', exporter_err: err ? String(err) : null })
    })
  })
})

// Provide an IPC method for the renderer to request the health JSON
ipcMain.handle('get-health-report', async () => {
  try {
    const reportPath = path.join(repoRoot, 'data', 'health.json')
    const raw = require('fs').readFileSync(reportPath, 'utf8')
    return JSON.parse(raw)
  } catch (e) {
    return { error: String(e) }
  }
})
