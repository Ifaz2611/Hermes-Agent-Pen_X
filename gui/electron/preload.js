const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  launchHermes: () => ipcRenderer.invoke('launch-hermes'),
  openDataFolder: () => ipcRenderer.invoke('open-data-folder'),
  runDoctor: () => ipcRenderer.invoke('run-doctor'),
})
