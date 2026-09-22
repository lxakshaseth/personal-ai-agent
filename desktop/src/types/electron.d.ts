export type WindowMode = 'robot' | 'dashboard';

export interface DesktopAPI {
  platform: string;
  isElectron: boolean;
  getWindowMode: () => Promise<WindowMode>;
  setWindowMode: (mode: WindowMode) => Promise<WindowMode>;
  toggleWindowMode: () => Promise<WindowMode>;
  minimizeWindow: () => Promise<void>;
  closeWindow: () => Promise<void>;
  onWindowModeChange: (callback: (mode: WindowMode) => void) => () => void;
}

declare global {
  interface Window {
    desktopAPI?: DesktopAPI;
  }
}
