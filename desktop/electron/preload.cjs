const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopAPI', {
  platform: process.platform,
  isElectron: true,
  getWindowMode: () => ipcRenderer.invoke('get-window-mode'),
  setWindowMode: (mode) => ipcRenderer.invoke('set-window-mode', mode),
  toggleWindowMode: () => ipcRenderer.invoke('toggle-window-mode'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  onWindowModeChange: (callback) => {
    const handler = (_event, mode) => callback(mode);
    ipcRenderer.on('window-mode-changed', handler);
    return () => ipcRenderer.removeListener('window-mode-changed', handler);
  },
});
