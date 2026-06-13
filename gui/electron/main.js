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

  win.loadFile('index.html')
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

const repoRoot = path.resolve(__dirname, '..')

ipcMain.handle('launch-hermes', async () => {
  const launcBat = path.join(repoRoot, 'launch.bat')
  if (process.platform === 'win32') {
    exec(`"${launcBat}"`, { cwd: repoRoot }, (err, stdout, stderr) => {
      if (err) {
        console.error(err)
      }
    })
    return { status: 'started' }
  }
  return { status: 'unsupported-platform' }
})

ipcMain.handle('open-data-folder', async () => {
  const dataPath = path.join(repoRoot, 'data')
  shell.openPath(dataPath)
  return { status: 'opened' }
})

ipcMain.handle('run-doctor', async () => {
  // Attempt to run hermes doctor (assumes a command exists)
  // Fall back to running `python -m hermes.doctor` if present
  const pythonCmd = `python -m hermes_doctor 2>&1`
  exec(pythonCmd, { cwd: repoRoot }, (err, stdout, stderr) => {
    // stdout/stderr logged to console; the TUI doctor is expected to open in terminal.
    if (err) {
      console.error('Doctor command failed:', err)
    }
  })
  return { status: 'launched' }
})
