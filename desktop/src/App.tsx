import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { ConfirmationDialog } from './components/confirmation/ConfirmationDialog';
import { DesktopRobot } from './components/robot/DesktopRobot';
import { useAgentStore } from './stores/agentStore';
import { useWebSocketInit } from './hooks/useWebSocket';
import { api } from './services/api';
import { WindowMode } from './types/electron';

// Pages
import { DashboardPage } from './pages/DashboardPage';
import { ChatPage } from './pages/ChatPage';
import { TasksPage } from './pages/TasksPage';
import { ToolsPage } from './pages/ToolsPage';
import { MemoryPage } from './pages/MemoryPage';
import { HistoryPage } from './pages/HistoryPage';
import { SecurityPage } from './pages/SecurityPage';
import { SettingsPage } from './pages/SettingsPage';
import { VoicePage } from './pages/VoicePage';
import { SystemStatusPage } from './pages/SystemStatusPage';
import { LogsPage } from './pages/LogsPage';

export const App: React.FC = () => {
  // Initialize real-time WebSocket & polling sync
  useWebSocketInit();

  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [windowMode, setWindowMode] = useState<WindowMode>('robot');
  const [agentState, store] = useAgentStore();

  // Sync mode with Electron main process
  useEffect(() => {
    if (window.desktopAPI?.getWindowMode) {
      window.desktopAPI.getWindowMode().then((mode) => {
        if (mode) setWindowMode(mode);
      });
    }

    if (window.desktopAPI?.onWindowModeChange) {
      const cleanup = window.desktopAPI.onWindowModeChange((mode) => {
        setWindowMode(mode);
      });
      return () => cleanup?.();
    }
  }, []);

  const handleSwitchMode = async (mode: WindowMode) => {
    setWindowMode(mode);
    if (window.desktopAPI?.setWindowMode) {
      try {
        await window.desktopAPI.setWindowMode(mode);
      } catch (err) {
        console.error('Failed to switch window mode in Electron:', err);
      }
    }
  };

  // Global Keyboard Shortcuts
  // - Ctrl + Shift + R: Toggle between Desktop Robot & Control Center
  // - Ctrl + Space: Activate voice
  // - Esc: Cancel current active task
  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      // Toggle window mode: Ctrl + Shift + R
      if (e.ctrlKey && e.shiftKey && e.code === 'KeyR') {
        e.preventDefault();
        const nextMode: WindowMode = windowMode === 'robot' ? 'dashboard' : 'robot';
        handleSwitchMode(nextMode);
        return;
      }

      // 1. Ctrl + Space -> Activate Voice
      if (e.ctrlKey && e.code === 'Space') {
        e.preventDefault();
        try {
          store.setStatus('listening', 'Listening for speech input (Ctrl+Space triggered)...');
          await api.triggerListen();
        } catch (err: any) {
          console.error('Failed to trigger voice listening', err);
          store.setStatus('error', err.message || 'Voice trigger failed');
        }
        return;
      }

      // 2. Esc -> Global Stop (halts current active task and stops TTS speech playback immediately)
      if (e.key === 'Escape') {
        e.preventDefault();
        try {
          await store.stopActive();
        } catch (err) {
          console.error('Failed to stop on Esc', err);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [windowMode, agentState.activeTask, agentState.tasks, store]);

  const renderActivePage = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardPage setActiveTab={setActiveTab} />;
      case 'chat':
        return <ChatPage />;
      case 'tasks':
        return <TasksPage />;
      case 'tools':
        return <ToolsPage />;
      case 'memory':
        return <MemoryPage />;
      case 'history':
        return <HistoryPage />;
      case 'security':
        return <SecurityPage />;
      case 'settings':
        return <SettingsPage />;
      case 'voice':
        return <VoicePage />;
      case 'system':
        return <SystemStatusPage />;
      case 'logs':
        return <LogsPage />;
      default:
        return <DashboardPage setActiveTab={setActiveTab} />;
    }
  };

  // ── Mode 1: Floating Desktop Robot Companion on Home Screen ──────────────
  if (windowMode === 'robot') {
    return (
      <div className="h-screen w-screen bg-transparent overflow-hidden flex flex-col justify-end select-none">
        <DesktopRobot onExpandDashboard={() => handleSwitchMode('dashboard')} />
      </div>
    );
  }

  // ── Mode 2: Full Windows Desktop Control Center ──────────────────────────
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#07090e] text-slate-100 font-sans select-none rounded-2xl border border-slate-800/80 shadow-2xl">
      {/* Interactive HIGH-risk Confirmation Modal */}
      <ConfirmationDialog tickets={agentState.pendingConfirmations} />

      {/* Main Sidebar (Control Center Tabs + Robot Dock) */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onSwitchToRobot={() => handleSwitchMode('robot')}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <Header
          activeTab={activeTab}
          onSwitchToRobot={() => handleSwitchMode('robot')}
        />
        <main className="flex-1 overflow-hidden relative">
          {renderActivePage()}
        </main>
      </div>
    </div>
  );
};

export default App;
