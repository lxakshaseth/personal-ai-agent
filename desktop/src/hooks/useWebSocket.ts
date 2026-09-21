import { useEffect } from 'react';
import { wsClient } from '../services/websocket';
import { agentStore } from '../stores/agentStore';
import { systemStore } from '../stores/systemStore';
import { api } from '../services/api';
import { WSEvent } from '../types/events';
import { AgentStatusType } from '../types/agent';
import { TimelineItem } from '../types/timeline';

function formatEventTime(isoOrEpoch?: string | number): string {
  if (!isoOrEpoch) {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  const d = typeof isoOrEpoch === 'number' ? new Date(isoOrEpoch * 1000) : new Date(isoOrEpoch);
  if (isNaN(d.getTime())) {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function useWebSocketInit() {
  useEffect(() => {
    // 1. Initial REST polling to sync state
    async function syncInitial() {
      try {
        const health = await api.checkHealth();
        if (health.status === 'ok') {
          agentStore.setConnected(true);
        }
        const statusData = await api.getStatus();
        agentStore.setStatus(statusData.status as AgentStatusType, statusData.detail);
        agentStore.setState({ activeModel: statusData.active_model });

        const confs = await api.getConfirmations();
        agentStore.setConfirmations(confs);

        const history = await api.getHistory();
        agentStore.setState({ history });

        const tasks = await api.getTasks();
        agentStore.setTasks(tasks);
      } catch (err) {
        agentStore.setConnected(false);
      }
    }

    syncInitial();

    // 2. Connect WebSocket
    wsClient.connect();

    // 3. Connection state
    const unsubConn = wsClient.subscribe('connection', (event: any) => {
      const connected = event.payload?.connected;
      agentStore.setConnected(connected);
      if (connected) {
        syncInitial();
      }
    });

    // 4. Initial state snapshot
    const unsubInit = wsClient.subscribe('init_snapshot', (event: WSEvent) => {
      const payload = event.payload;
      if (payload.status) {
        agentStore.setStatus(payload.status, payload.detail);
      }
      if (payload.pending_confirmations) {
        agentStore.setConfirmations(payload.pending_confirmations);
      }
    });

    // 5. Canonical agent.state event (requirement 2)
    const unsubAgentState = wsClient.subscribe('agent.state', (event: any) => {
      const data = event.payload || event;
      const rawState = (data.state || data.status || 'online').toLowerCase();
      const detail = data.detail || '';
      agentStore.setStatus(rawState as AgentStatusType, detail);

      if (rawState === 'idle' || rawState === 'completed' || rawState === 'online') {
        const cur = agentStore.getState().activeExecution;
        if (cur && cur.status === 'running') {
          agentStore.setActiveExecution({
            ...cur,
            status: 'completed',
            currentOperation: detail || 'Ready',
            progress: 1.0,
          });
        }
      } else if (rawState === 'speaking') {
        const cur = agentStore.getState().activeExecution;
        if (cur) {
          agentStore.setActiveExecution({
            ...cur,
            status: 'running',
            currentOperation: 'Speaking response aloud...',
            progress: 0.95,
          });
        }
      }
    });

    // 5b. Legacy status_changed
    const unsubStatus = wsClient.subscribe('status_changed', (event: WSEvent) => {
      const { status, detail } = event.payload || {};
      if (status) agentStore.setStatus(status, detail);
    });

    // 6. Confirmation events
    const unsubConfReq = wsClient.subscribe('confirmation_requested', (event: WSEvent) => {
      if (event.payload) agentStore.addConfirmation(event.payload);
    });

    const unsubConfRes = wsClient.subscribe('confirmation_resolved', (event: WSEvent) => {
      if (event.payload?.ticket_id) agentStore.resolveConfirmation(event.payload.ticket_id);
    });

    // 7. Command events
    const unsubCmdComp = wsClient.subscribe('command_completed', (event: WSEvent) => {
      const record = event.payload;
      if (record?.id) {
        agentStore.setState({
          history: [record, ...agentStore.getState().history.filter((h) => h.id !== record.id)],
        });
      }
    });

    // 8. Task events
    const unsubTaskCreated = wsClient.subscribe('task_created', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });
    const unsubTaskUpdated = wsClient.subscribe('task_updated', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });
    const unsubTaskPaused = wsClient.subscribe('task_paused', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });
    const unsubTaskResumed = wsClient.subscribe('task_resumed', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });
    const unsubTaskCompleted = wsClient.subscribe('task_completed', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });
    const unsubTaskCancelled = wsClient.subscribe('task_cancelled', (event: any) => {
      if (event.payload) agentStore.upsertTask(event.payload);
    });

    // ──────────────────────────────────────────────────────────────────────────
    // 9. THE 12 REAL-TIME EXECUTION VISUALIZATION EVENTS
    // ──────────────────────────────────────────────────────────────────────────

    // 1. agent.started
    const unsubAgentStarted = wsClient.subscribe('agent.started', (event: any) => {
      const data = event.payload || event;
      const timeStr = formatEventTime(data.timestamp);
      agentStore.setActiveExecution({
        requestId: data.request_id,
        taskId: data.task_id,
        command: data.command,
        currentOperation: 'Initializing command',
        startTime: Date.now(),
        elapsedSeconds: 0,
        status: 'running',
        progress: 0.1,
      });
      agentStore.addTimelineItem({
        id: 'start_' + (data.request_id || Date.now()),
        event: 'agent.started',
        timestamp: timeStr,
        rawTimestamp: Date.now(),
        title: `🚀 Started: "${data.command || 'Command'}"`,
        status: 'completed',
        requestId: data.request_id,
      });
    });

    // 2. agent.listening
    const unsubAgentListening = wsClient.subscribe('agent.listening', (event: any) => {
      const data = event.payload || event;
      agentStore.setStatus('listening', 'Listening for speech...');
      agentStore.setActiveExecution({
        requestId: data.request_id,
        currentOperation: 'Listening for voice command...',
        startTime: Date.now(),
        elapsedSeconds: 0,
        status: 'running',
        progress: 0.1,
      });
      agentStore.addTimelineItem({
        id: 'listen_' + Date.now(),
        event: 'agent.listening',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: '🎙 Listening',
        status: 'running',
        requestId: data.request_id,
      });
    });

    // 3. agent.transcribing
    const unsubAgentTranscribing = wsClient.subscribe('agent.transcribing', (event: any) => {
      const data = event.payload || event;
      agentStore.setStatus('listening', 'Transcribing audio...');
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: 'Transcribing speech...',
          progress: 0.2,
        });
      }
      agentStore.addTimelineItem({
        id: 'transcribe_' + Date.now(),
        event: 'agent.transcribing',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: '📝 Transcribing',
        status: 'running',
        requestId: data.request_id,
      });
    });

    // 4. agent.thinking
    const unsubAgentThinking = wsClient.subscribe('agent.thinking', (event: any) => {
      const data = event.payload || event;
      agentStore.setStatus('thinking', 'Understanding command...');
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: 'Understanding command...',
          progress: 0.25,
        });
      }
      agentStore.addTimelineItem({
        id: 'think_' + (data.request_id || Date.now()),
        event: 'agent.thinking',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: '🧠 Understanding command',
        status: 'completed',
        requestId: data.request_id,
      });
    });

    // 5. agent.planning
    const unsubAgentPlanning = wsClient.subscribe('agent.planning', (event: any) => {
      const data = event.payload || event;
      agentStore.setStatus('thinking', 'Planning execution steps...');
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: 'Planning tool execution with Groq LLM...',
          progress: 0.35,
        });
      }
      agentStore.addTimelineItem({
        id: 'plan_' + (data.request_id || Date.now()),
        event: 'agent.planning',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: '🧠 Planning',
        status: 'completed',
        requestId: data.request_id,
      });
    });

    // 6. tool.selected
    const unsubToolSelected = wsClient.subscribe('tool.selected', (event: any) => {
      const data = event.payload || event;
      const toolName = data.tool || 'tool';
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: `Selected tool: ${toolName}`,
          progress: 0.45,
        });
      }
      agentStore.addTimelineItem({
        id: 'selected_' + toolName + '_' + Date.now(),
        event: 'tool.selected',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: `🔧 Selected: ${toolName}`,
        tool: toolName,
        details: data.arguments,
        status: 'completed',
        requestId: data.request_id,
      });
    });

    // 7. tool.started
    const unsubToolStarted = wsClient.subscribe('tool.started', (event: any) => {
      const data = event.payload || event;
      const toolName = data.tool || 'tool';
      agentStore.setStatus('executing', `Executing ${toolName}...`);
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: `Executing ${toolName}`,
          progress: 0.6,
        });
      }
      agentStore.addTimelineItem({
        id: 'exec_' + toolName + '_' + (data.request_id || Date.now()),
        event: 'tool.started',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: '⚙ Executing',
        tool: toolName,
        details: data.arguments,
        status: 'running',
        requestId: data.request_id,
      });
    });

    // 8. tool.progress
    const unsubToolProgress = wsClient.subscribe('tool.progress', (event: any) => {
      const data = event.payload || event;
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: data.message || `Executing ${data.tool || 'tool'}`,
          progress: data.progress ?? cur.progress,
        });
      }
    });

    // 9. tool.completed
    const unsubToolCompleted = wsClient.subscribe('tool.completed', (event: any) => {
      const data = event.payload || event;
      const toolName = data.tool || 'tool';
      const isSuccess = data.success !== false;
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          currentOperation: `${toolName} finished`,
          progress: 0.85,
        });
      }
      agentStore.addTimelineItem({
        id: 'comp_' + toolName + '_' + Date.now(),
        event: 'tool.completed',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: isSuccess ? '✓ Completed' : `✗ Failed (${toolName})`,
        tool: toolName,
        duration: data.duration,
        details: data.output || data.error,
        error: data.error,
        status: isSuccess ? 'completed' : 'error',
        requestId: data.request_id,
      });
    });

    // 10. confirmation.required
    const unsubConfRequired = wsClient.subscribe('confirmation.required', (event: any) => {
      const data = event.payload || event;
      const toolName = data.tool || 'tool';
      agentStore.setStatus('waiting_confirmation', `Confirmation needed for ${toolName}`);
      agentStore.addTimelineItem({
        id: 'conf_req_' + Date.now(),
        event: 'confirmation.required',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: `⚠️ Approval Required: ${toolName}`,
        tool: toolName,
        details: data.arguments,
        error: data.reason,
        status: 'running',
        requestId: data.request_id,
      });
    });

    // 11. agent.completed
    const unsubAgentCompleted = wsClient.subscribe('agent.completed', (event: any) => {
      const data = event.payload || event;
      agentStore.setStatus('online', 'Ready');
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          status: 'completed',
          currentOperation: 'Execution completed',
          progress: 1.0,
        });
      }
      const replyText = typeof data.response === 'string' ? data.response : 'Task completed.';
      agentStore.addTimelineItem({
        id: 'agent_comp_' + Date.now(),
        event: 'agent.completed',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: `🤖 ${replyText}`,
        duration: data.duration,
        details: data.tool_calls,
        status: 'completed',
        requestId: data.request_id,
      });
    });

    // 12. agent.error
    const unsubAgenterror = wsClient.subscribe('agent.error', (event: any) => {
      const data = event.payload || event;
      const errText = data.error || 'Execution encountered an error';
      agentStore.setStatus('error', errText);
      const cur = agentStore.getState().activeExecution;
      if (cur) {
        agentStore.setActiveExecution({
          ...cur,
          status: 'error',
          currentOperation: errText,
        });
      }
      agentStore.addTimelineItem({
        id: 'err_' + Date.now(),
        event: 'agent.error',
        timestamp: formatEventTime(data.timestamp),
        rawTimestamp: Date.now(),
        title: `✗ ${errText}`,
        error: errText,
        status: 'error',
        requestId: data.request_id,
      });
    });

    // Periodic system metrics polling
    const metricsInterval = setInterval(async () => {
      try {
        const metrics = await api.getSystemMetrics();
        systemStore.setMetrics(metrics);
      } catch (err: any) {
        systemStore.setError(err.message);
      }
    }, 2500);

    return () => {
      unsubConn();
      unsubInit();
      unsubAgentState();
      unsubStatus();
      unsubConfReq();
      unsubConfRes();
      unsubCmdComp();
      unsubTaskCreated();
      unsubTaskUpdated();
      unsubTaskPaused();
      unsubTaskResumed();
      unsubTaskCompleted();
      unsubTaskCancelled();

      // Unsubscribe visualization events
      unsubAgentStarted();
      unsubAgentListening();
      unsubAgentTranscribing();
      unsubAgentThinking();
      unsubAgentPlanning();
      unsubToolSelected();
      unsubToolStarted();
      unsubToolProgress();
      unsubToolCompleted();
      unsubConfRequired();
      unsubAgentCompleted();
      unsubAgenterror();

      clearInterval(metricsInterval);
      wsClient.disconnect();
    };
  }, []);
}
