const { app, BrowserWindow, shell, ipcMain, globalShortcut, screen } = require('electron');
const path = require('path');

let mainWindow = null;
let currentMode = 'robot'; // Default: launch directly as Desktop Robot on home screen
let lastRobotPosition = null;

const ROBOT_WIDTH = 380;
const ROBOT_HEIGHT = 540;
const DASHBOARD_WIDTH = 1340;
const DASHBOARD_HEIGHT = 880;

function getRobotDefaultPosition() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: sw, height: sh } = primaryDisplay.workAreaSize;
  const x = Math.max(20, sw - ROBOT_WIDTH - 24);
  const y = Math.max(20, sh - ROBOT_HEIGHT - 24);
  return { x, y };
}

function switchMode(mode) {
  if (!mainWindow) return currentMode;
  if (mode === currentMode) return currentMode;

  if (mode === 'dashboard') {
    // Remember robot position before expanding
    const [rx, ry] = mainWindow.getPosition();
    lastRobotPosition = { x: rx, y: ry };

    mainWindow.setResizable(true);
    mainWindow.setAlwaysOnTop(false);
    mainWindow.setMinimumSize(1040, 700);
    mainWindow.setSize(DASHBOARD_WIDTH, DASHBOARD_HEIGHT);
    mainWindow.center();
    currentMode = 'dashboard';
  } else {
    // Switch to desktop robot companion
    mainWindow.setMinimumSize(320, 480);
    mainWindow.setResizable(false);
    mainWindow.setSize(ROBOT_WIDTH, ROBOT_HEIGHT);

    const targetPos = lastRobotPosition || getRobotDefaultPosition();
    mainWindow.setPosition(targetPos.x, targetPos.y);
    mainWindow.setAlwaysOnTop(true, 'screen-saver');
    currentMode = 'robot';
  }

  mainWindow.webContents.send('window-mode-changed', currentMode);
  return currentMode;
}

function createWindow() {
  const { x: defaultX, y: defaultY } = getRobotDefaultPosition();

  mainWindow = new BrowserWindow({
    width: ROBOT_WIDTH,
    height: ROBOT_HEIGHT,
    x: defaultX,
    y: defaultY,
    frame: false,
    transparent: true,
    hasShadow: false,
    alwaysOnTop: true,
    resizable: false,
    backgroundColor: '#00000000',
    title: 'NOVA AI — Desktop Robot Companion',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false, // Allows calling localhost:8000 smoothly
    },
  });

  // Load dist/index.html or dev server
  const fs = require('fs');
  const distHtmlPath = path.join(__dirname, '../dist/index.html');
  const devServerUrl = 'http://localhost:5173';

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL(devServerUrl).catch(() => {
      if (fs.existsSync(distHtmlPath)) {
        mainWindow.loadFile(distHtmlPath);
      }
    });
  } else if (fs.existsSync(distHtmlPath)) {
    mainWindow.loadFile(distHtmlPath);
  } else {
    mainWindow.loadURL(devServerUrl).catch(() => {
      setTimeout(() => mainWindow.loadURL(devServerUrl), 1000);
    });
  }

  // Open target="_blank" links in default external browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC handlers for window control and mode switching
ipcMain.handle('get-window-mode', () => currentMode);
ipcMain.handle('set-window-mode', (_event, mode) => switchMode(mode));
ipcMain.handle('toggle-window-mode', () => {
  return switchMode(currentMode === 'robot' ? 'dashboard' : 'robot');
});
ipcMain.handle('minimize-window', () => {
  if (mainWindow) mainWindow.minimize();
});
ipcMain.handle('close-window', () => {
  if (mainWindow) mainWindow.close();
});

app.whenReady().then(() => {
  createWindow();

  // Register Global Shortcuts:
  // - Ctrl + Shift + R: Toggle between Desktop Robot & Full Control Center
  // - Ctrl + Shift + A: Focus / show agent
  try {
    globalShortcut.register('CommandOrControl+Shift+R', () => {
      switchMode(currentMode === 'robot' ? 'dashboard' : 'robot');
    });

    globalShortcut.register('CommandOrControl+Shift+A', () => {
      if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        if (!mainWindow.isVisible()) mainWindow.show();
        mainWindow.focus();
      }
    });
  } catch (err) {
    console.error('Failed to register global shortcuts:', err);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
