const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  launchHermes: (options) => ipcRenderer.invoke('launch-hermes', options || {}),
  openDataFolder: () => ipcRenderer.invoke('open-data-folder'),
  runDoctor: () => ipcRenderer.invoke('run-doctor'),
  getHealthReport: () => ipcRenderer.invoke('get-health-report'),
  listProfiles: () => ipcRenderer.invoke('list-profiles'),
  createProfile: (name) => ipcRenderer.invoke('create-profile', name),
  deleteProfile: (payload) => ipcRenderer.invoke('delete-profile', payload),
  switchProfile: (name) => ipcRenderer.invoke('switch-profile', name),
  getSetupProgress: () => ipcRenderer.invoke('get-setup-progress'),
  runSetup: () => ipcRenderer.invoke('run-setup'),
  cancelSetup: () => ipcRenderer.invoke('cancel-setup'),
})
