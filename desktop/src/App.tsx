import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { ConfirmationDialog } from './components/confirmation/ConfirmationDialog';
import { useAgentStore } from './stores/agentStore';
import { useWebSocketInit } from './hooks/useWebSocket';
import { api } from './services/api';

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
  const [agentState, store] = useAgentStore();

  // Global Keyboard Shortcuts
  // - Ctrl + Space: Activate voice
  // - Esc: Cancel current active task
  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
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
  }, [agentState.activeTask, agentState.tasks, store]);

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

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#07090e] text-slate-100 font-sans select-none">
      {/* Interactive HIGH-risk Confirmation Modal */}
      <ConfirmationDialog tickets={agentState.pendingConfirmations} />

      {/* Main Sidebar (Exactly 8 Control Center Tabs) */}
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <Header activeTab={activeTab} />
        <main className="flex-1 overflow-hidden relative">
          {renderActivePage()}
        </main>
      </div>
    </div>
  );
};

export default App;
