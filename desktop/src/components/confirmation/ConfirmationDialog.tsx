import React, { useState, useEffect } from 'react';
import { ConfirmationTicket } from '../../types/agent';
import { api } from '../../services/api';
import { agentStore } from '../../stores/agentStore';
import { AlertTriangle, Check, X, ShieldAlert, Clock } from 'lucide-react';

interface ConfirmationDialogProps {
  tickets: ConfirmationTicket[];
}

export const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({ tickets }) => {
  if (!tickets || tickets.length === 0) return null;

  const activeTicket = tickets[0]; // Process top ticket
  const [timeLeft, setTimeLeft] = useState<number>(60);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const expiresAt = activeTicket.expires_at || Date.now() / 1000 + 60;
    const updateTimer = () => {
      const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
      setTimeLeft(remaining);
      if (remaining <= 0) {
        agentStore.resolveConfirmation(activeTicket.ticket_id);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [activeTicket]);

  const handleAction = async (approved: boolean) => {
    setIsSubmitting(true);
    try {
      await api.respondConfirmation(activeTicket.ticket_id, approved);
      agentStore.resolveConfirmation(activeTicket.ticket_id);
    } catch (err) {
      console.error('Failed to respond to confirmation ticket', err);
      agentStore.resolveConfirmation(activeTicket.ticket_id);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-[#0e131f] border border-amber-500/40 rounded-2xl shadow-2xl shadow-amber-950/40 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-950/80 via-amber-900/40 to-slate-900 px-6 py-4 border-b border-amber-500/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/20 border border-amber-500/40 rounded-xl text-amber-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-white text-base">Security Confirmation Required</h3>
              <p className="text-xs text-amber-300/80">HIGH-risk computer operation requested</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 border border-amber-500/30 rounded-full text-amber-300 text-xs font-mono">
            <Clock className="w-3.5 h-3.5" />
            <span>{timeLeft}s</span>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400 font-medium">Requested Tool</span>
              <span className="px-2 py-0.5 text-[11px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-md">
                HIGH RISK
              </span>
            </div>
            <div className="font-mono text-cyan-300 text-sm font-semibold mb-1">
              {activeTicket.tool_name}()
            </div>
            {activeTicket.command && (
              <div className="text-xs text-slate-300 mb-2">
                Triggered by: <span className="text-slate-100 font-medium italic">"{activeTicket.command}"</span>
              </div>
            )}
            <p className="text-xs text-slate-400 leading-relaxed">{activeTicket.reason}</p>
          </div>

          {/* Arguments */}
          <div>
            <span className="text-xs text-slate-400 font-medium mb-1.5 block">Operation Parameters</span>
            <pre className="bg-[#080b11] border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300 overflow-x-auto max-h-36">
              {JSON.stringify(activeTicket.arguments, null, 2)}
            </pre>
          </div>

          <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg flex items-start gap-2.5 text-xs text-amber-200/90">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <span>
              This operation can modify or delete files or alter system state. Only approve if you intended this action.
            </span>
          </div>
        </div>

        {/* Footer actions */}
        <div className="px-6 py-4 bg-slate-900/60 border-t border-slate-800/80 flex items-center justify-end gap-3">
          <button
            onClick={() => handleAction(false)}
            disabled={isSubmitting}
            className="px-4 py-2 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl transition-colors flex items-center gap-1.5"
          >
            <X className="w-3.5 h-3.5" />
            Reject & Cancel
          </button>
          <button
            onClick={() => handleAction(true)}
            disabled={isSubmitting}
            className="px-5 py-2 text-xs font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-lg shadow-emerald-950/50 rounded-xl transition-all flex items-center gap-1.5 active:scale-95"
          >
            <Check className="w-3.5 h-3.5" />
            Approve Execution
          </button>
        </div>
      </div>
    </div>
  );
};
