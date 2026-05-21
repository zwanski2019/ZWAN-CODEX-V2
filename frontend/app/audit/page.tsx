"use client";

import { useState, useEffect } from "react";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import { Database, ChevronRight, Download, RefreshCw } from "lucide-react";

const AGENT_BASE = process.env.NEXT_PUBLIC_AGENT_HTTP ?? "http://127.0.0.1:8788";

async function agentFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${AGENT_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

interface AuditSession {
  id: string;
  started_at: string;
  goal: string;
  mode: string;
  scope_hash: string;
  ended_at: string | null;
  summary: string | null;
}

interface AuditCommand {
  id: string;
  session_id: string;
  ts: string;
  tool: string;
  rendered_cmd: string;
  tier: string;
  needs_root: number;
  decision: string;
  approved_by: string | null;
  target: string | null;
  exit_code: number | null;
  duration_ms: number | null;
  blocked_reason: string | null;
}

const DECISION_COLOR: Record<string, string> = {
  allow_auto:       "text-green-400",
  needs_approval:   "text-amber-400",
  block:            "text-red-400",
};

const TIER_COLOR: Record<string, string> = {
  recon:   "text-cyan-400",
  exploit: "text-orange-400",
};

function CommandRow({ cmd }: { cmd: AuditCommand }) {
  const statusColor =
    cmd.blocked_reason ? "text-red-400" :
    cmd.exit_code === 0 ? "text-green-400" :
    cmd.exit_code === null ? "text-amber-400/60" :
    "text-red-300";

  return (
    <tr className="border-b border-amber-400/10 hover:bg-amber-400/5">
      <td className="px-2 py-1.5 text-amber-400/40 tabular-nums text-[10px] whitespace-nowrap">
        {new Date(cmd.ts).toLocaleTimeString("en-GB", { hour12: false })}
      </td>
      <td className={cn("px-2 py-1.5 text-[11px]", TIER_COLOR[cmd.tier] ?? "text-zinc-400")}>
        {cmd.tool}
      </td>
      <td className="px-2 py-1.5 text-amber-200/70 text-[10px] font-mono max-w-xs truncate">
        {cmd.rendered_cmd}
      </td>
      <td className={cn("px-2 py-1.5 text-[10px]", DECISION_COLOR[cmd.decision] ?? "text-zinc-400")}>
        {cmd.decision}
      </td>
      <td className={cn("px-2 py-1.5 text-[10px] tabular-nums", statusColor)}>
        {cmd.blocked_reason ?? (cmd.exit_code === null ? "dry" : String(cmd.exit_code))}
      </td>
      <td className="px-2 py-1.5 text-amber-400/30 text-[10px] tabular-nums">
        {cmd.duration_ms !== null ? `${cmd.duration_ms}ms` : "—"}
      </td>
    </tr>
  );
}

export default function AuditPage() {
  const [sessions, setSessions] = useState<AuditSession[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [commands, setCommands] = useState<AuditCommand[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const loadSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await agentFetch<AuditSession[]>("/api/sessions");
      setSessions(data);
    } catch (e) {
      setError(`Agent unreachable — is it running on port 8788? (${e})`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSessions(); }, []);

  const selectSession = async (id: string) => {
    setSelected(id);
    try {
      const cmds = await agentFetch<AuditCommand[]>(`/api/sessions/${id}/commands`);
      setCommands(cmds);
    } catch {
      setCommands([]);
    }
  };

  const exportMarkdown = async () => {
    if (!selected) return;
    setExporting(true);
    try {
      const data = await agentFetch<{ markdown: string }>(`/api/sessions/${selected}/export`);
      const blob = new Blob([data.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `session-${selected.slice(0, 8)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-black">
      <Nav />
      <main className="ml-56 flex-1 flex flex-col p-4 font-mono">

        {/* CRT scanline */}
        <div
          className="pointer-events-none fixed inset-0 z-50"
          style={{
            background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)",
          }}
        />

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <Database size={18} className="text-amber-400" />
          <span className="text-amber-400 font-bold tracking-widest text-sm uppercase">Audit Log</span>
          <button
            onClick={loadSessions}
            disabled={loading}
            className="ml-auto flex items-center gap-1.5 px-3 py-1 rounded border border-amber-400/20 text-amber-400/60 text-xs hover:border-amber-400/40 hover:text-amber-400 transition-colors"
          >
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="border border-red-500/30 bg-red-500/5 rounded px-3 py-2 text-red-400 text-xs mb-3">
            {error}
          </div>
        )}

        <div className="flex gap-4 flex-1 min-h-0">
          {/* Sessions list */}
          <div className="w-72 shrink-0 flex flex-col border border-amber-400/20 rounded bg-zinc-950 overflow-hidden">
            <div className="px-3 py-2 border-b border-amber-400/15">
              <span className="text-amber-400/60 text-[10px] uppercase tracking-widest">
                Sessions ({sessions.length})
              </span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {sessions.length === 0 && !loading && (
                <p className="text-amber-400/20 text-center text-xs pt-8">No sessions recorded.</p>
              )}
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 border-b border-amber-400/10 hover:bg-amber-400/5 transition-colors",
                    selected === s.id && "bg-amber-400/8 border-l-2 border-l-amber-400"
                  )}
                >
                  <div className="flex items-start justify-between gap-1">
                    <span className="text-amber-300/80 text-xs truncate flex-1">
                      {s.goal || "(no goal)"}
                    </span>
                    <span className={cn(
                      "text-[10px] shrink-0",
                      s.mode === "yolo" ? "text-red-400" :
                      s.mode === "auto" ? "text-amber-400" :
                      "text-zinc-500"
                    )}>
                      {s.mode}
                    </span>
                  </div>
                  <div className="text-amber-400/30 text-[10px] mt-0.5">
                    {new Date(s.started_at).toLocaleString("en-GB", { hour12: false })}
                  </div>
                  {s.ended_at && (
                    <div className="text-amber-400/20 text-[10px] truncate">
                      {s.summary}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Commands table */}
          <div className="flex-1 flex flex-col border border-amber-400/20 rounded bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-amber-400/15">
              <span className="text-amber-400/60 text-[10px] uppercase tracking-widest">
                Commands {selected ? `(${commands.length})` : "— select session"}
              </span>
              {selected && (
                <button
                  onClick={exportMarkdown}
                  disabled={exporting}
                  className="ml-auto flex items-center gap-1.5 px-3 py-1 rounded border border-amber-400/20 text-amber-400/60 text-[10px] hover:border-amber-400/40 hover:text-amber-400 transition-colors"
                >
                  <Download size={10} />
                  Export .md
                </button>
              )}
            </div>

            {selected && commands.length > 0 ? (
              <div className="flex-1 overflow-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-amber-400/15">
                      {["Time", "Tool", "Command", "Decision", "Exit", "Duration"].map((h) => (
                        <th key={h} className="text-left px-2 py-1.5 text-amber-400/40 text-[10px] uppercase tracking-wider font-normal">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {commands.map((c) => <CommandRow key={c.id} cmd={c} />)}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-amber-400/20 text-xs">
                {selected ? "No commands recorded." : "▌ Select a session"}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
