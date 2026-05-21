"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AgentRun, type AgentRunDetail, type Engagement } from "@/lib/api";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Cpu,
  Radio,
  ChevronRight,
  DollarSign,
  Terminal,
  Zap,
  Filter,
  RefreshCw,
} from "lucide-react";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8731";

const AGENT_META: Record<string, { label: string; color: string }> = {
  recon:           { label: "Recon Mapper",    color: "text-blue-400"   },
  js_miner:        { label: "JS Miner",        color: "text-yellow-400" },
  oauth_chain:     { label: "OAuth Chain",     color: "text-purple-400" },
  desync:          { label: "HTTP Desync",     color: "text-red-400"    },
  race:            { label: "Race Condition",  color: "text-orange-400" },
  ssrf:            { label: "SSRF Hunter",     color: "text-pink-400"   },
  chain_hunter:    { label: "Chain Hunter",    color: "text-cyan-400"   },
  validator:       { label: "Validator",       color: "text-green-400"  },
  report:          { label: "Report Gen",      color: "text-emerald-400"},
  zeroday_scanner: { label: "Zero-Day",        color: "text-yellow-300" },
  agentic_target:  { label: "Agentic Target",  color: "text-violet-400" },
};

const STATUS_DOT: Record<string, string> = {
  running: "bg-blue-500 animate-pulse",
  done:    "bg-green-500",
  failed:  "bg-red-500",
  queued:  "bg-zinc-500",
};

const STATUS_LABEL: Record<string, string> = {
  running: "text-blue-400",
  done:    "text-green-400",
  failed:  "text-red-400",
  queued:  "text-zinc-400",
};

function duration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const sec = Math.floor((e - s) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function timeAgo(iso: string): string {
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

// ─── Live global feed ────────────────────────────────────────────────────────

interface FeedEvent {
  id: number;
  ts: string;
  engagement_id?: string;
  agent?: string;
  type: string;
  message: string;
}

let _feedId = 0;

function LiveFeed() {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/global`);

    ws.onmessage = (e) => {
      try {
        const raw = JSON.parse(e.data);
        const msg: string =
          (raw.data?.message ??
          (raw.data?.title ? `FINDING: ${raw.data.title} (${raw.data.severity?.toUpperCase()})` : "")) ||
          raw.type;

        const ev: FeedEvent = {
          id: _feedId++,
          ts: raw.ts ?? new Date().toISOString(),
          engagement_id: raw.engagement_id,
          agent: raw.agent,
          type: raw.type ?? "event",
          message: msg,
        };

        setEvents((prev) => [...prev.slice(-149), ev]);
      } catch {
        // malformed
      }
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <Radio size={11} className="text-green-400 animate-pulse" />
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Global Event Feed
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground/50">{events.length} events</span>
      </div>
      <div className="flex-1 overflow-y-auto font-mono text-[11px] p-2 space-y-0.5">
        {events.length === 0 && (
          <p className="text-muted-foreground/40 text-center pt-8">Waiting for agent activity…</p>
        )}
        {events.map((ev) => (
          <div key={ev.id} className="flex gap-1.5 leading-relaxed group">
            <span className="text-muted-foreground/30 shrink-0 text-[10px] pt-px">
              {new Date(ev.ts).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            {ev.agent && (
              <span className={cn("shrink-0", AGENT_META[ev.agent]?.color ?? "text-zinc-400")}>
                [{AGENT_META[ev.agent]?.label ?? ev.agent}]
              </span>
            )}
            <span
              className={cn(
                "break-all",
                ev.type === "finding" ? "text-orange-400" :
                ev.type === "error"   ? "text-red-400" :
                ev.type === "done"    ? "text-green-400" :
                "text-muted-foreground"
              )}
            >
              {ev.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Run card ────────────────────────────────────────────────────────────────

function RunCard({ run }: { run: AgentRun }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [loadingTrace, setLoadingTrace] = useState(false);

  const meta = AGENT_META[run.agent_name] ?? { label: run.agent_name, color: "text-zinc-400" };
  const dur = duration(run.started_at, run.finished_at);

  const handleOpen = useCallback(async () => {
    const next = !open;
    setOpen(next);
    if (next && !detail && !loadingTrace) {
      setLoadingTrace(true);
      try {
        const d = await api.agents.getRun(run.id);
        setDetail(d);
      } catch {
        // ignore
      } finally {
        setLoadingTrace(false);
      }
    }
  }, [open, detail, loadingTrace, run.id]);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        onClick={handleOpen}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-accent/20 transition-colors"
      >
        <span className={cn("w-2 h-2 rounded-full shrink-0", STATUS_DOT[run.status] ?? "bg-zinc-500")} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-semibold", meta.color)}>{meta.label}</span>
            <span className={cn("text-[10px] uppercase font-mono", STATUS_LABEL[run.status] ?? "text-zinc-400")}>
              {run.status}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground/60 truncate mt-0.5 font-mono">{run.engagement_id}</p>
        </div>

        <div className="flex items-center gap-4 text-[11px] text-muted-foreground shrink-0">
          {run.status === "running" && (
            <span className="flex items-center gap-1">
              <Clock size={10} className="animate-spin" />
              {dur}
            </span>
          )}
          {run.status !== "running" && dur !== "—" && (
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {dur}
            </span>
          )}
          <span>{(run.llm_tokens_in + run.llm_tokens_out).toLocaleString()} tok</span>
          <span className="text-green-400/80">${run.llm_cost_usd.toFixed(4)}</span>
          {run.started_at && (
            <span className="text-muted-foreground/40">{timeAgo(run.started_at)}</span>
          )}
        </div>

        <ChevronRight
          size={13}
          className={cn("text-muted-foreground shrink-0 transition-transform ml-1", open && "rotate-90")}
        />
      </button>

      {run.error && (
        <div className="px-4 py-2 border-t border-red-500/20 bg-red-500/5 text-xs text-red-400 font-mono">
          {run.error}
        </div>
      )}

      {open && (
        <div className="border-t border-border px-4 py-3 space-y-3">
          {loadingTrace && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <RefreshCw size={11} className="animate-spin" /> Loading trace…
            </div>
          )}

          {detail && detail.trace && detail.trace.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <Terminal size={10} /> Agent Trace
              </p>
              <div className="bg-zinc-900 rounded border border-border p-2.5 max-h-64 overflow-y-auto font-mono text-[11px] space-y-0.5">
                {detail.trace.map((ev, i) => {
                  const msg =
                    (ev.data as Record<string, string>)?.message ??
                    (ev.data as Record<string, string>)?.title ??
                    JSON.stringify(ev.data ?? "");
                  return (
                    <div key={i} className="flex gap-2">
                      <span className="text-purple-400 shrink-0">[{String(ev.type ?? "event")}]</span>
                      <span className={String(ev.type) === "finding" ? "text-orange-400" : "text-muted-foreground"}>
                        {String(msg)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {detail && Object.keys(detail.output_data ?? {}).length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
                Output Summary
              </p>
              <pre className="bg-zinc-900 rounded border border-border p-2.5 text-[11px] text-muted-foreground overflow-x-auto">
                {JSON.stringify(detail.output_data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [engFilter, setEngFilter] = useState<string>("");

  const { data: runs = [], isFetching } = useQuery({
    queryKey: ["agent-runs", engFilter],
    queryFn: () => api.agents.runs(engFilter || undefined),
    refetchInterval: 4000,
  });

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ["engagements"],
    queryFn: api.engagements.list,
  });

  const running = runs.filter((r) => r.status === "running").length;
  const done    = runs.filter((r) => r.status === "done").length;
  const failed  = runs.filter((r) => r.status === "failed").length;
  const totalCost = runs.reduce((s, r) => s + r.llm_cost_usd, 0);

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 flex flex-col p-6 max-w-7xl">

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/30">
            <Activity size={20} className="text-blue-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold">Mission Control</h1>
            <p className="text-xs text-muted-foreground">Real-time agent activity · all engagements</p>
          </div>
          {isFetching && <RefreshCw size={13} className="text-muted-foreground animate-spin ml-2" />}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-3 mb-5">
          {[
            { icon: <Activity size={14} className="text-blue-400" />,  label: "Running",    value: running,               color: "text-blue-400"  },
            { icon: <CheckCircle2 size={14} className="text-green-400" />, label: "Completed", value: done,               color: "text-green-400" },
            { icon: <XCircle size={14} className="text-red-400" />,    label: "Failed",     value: failed,                color: "text-red-400"   },
            { icon: <DollarSign size={14} className="text-yellow-400" />, label: "LLM Cost",  value: `$${totalCost.toFixed(4)}`, color: "text-yellow-400" },
          ].map(({ icon, label, value, color }) => (
            <div key={label} className="rounded-lg border border-border bg-card px-4 py-3 flex items-center gap-3">
              {icon}
              <div>
                <div className={cn("text-lg font-bold leading-none", color)}>{value}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5 uppercase tracking-wider">{label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Main 2-column layout */}
        <div className="flex gap-5 flex-1 min-h-0">

          {/* Runs list */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Filter */}
            <div className="flex items-center gap-2 mb-3">
              <Filter size={12} className="text-muted-foreground shrink-0" />
              <select
                value={engFilter}
                onChange={(e) => setEngFilter(e.target.value)}
                className="flex-1 bg-zinc-900 border border-border rounded-md px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:border-blue-500/40 appearance-none"
              >
                <option value="">All engagements</option>
                {engagements.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
              <span className="text-[10px] text-muted-foreground shrink-0">{runs.length} runs</span>
            </div>

            <div className="space-y-2 overflow-y-auto flex-1 pr-1">
              {runs.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 text-muted-foreground border border-dashed border-border rounded-lg">
                  <Cpu size={28} className="mb-2 opacity-30" />
                  <p className="text-sm">No agent runs yet</p>
                  <p className="text-xs mt-1 opacity-60">Start a hunt to see agents working here</p>
                </div>
              )}
              {runs.map((r) => (
                <RunCard key={r.id} run={r} />
              ))}
            </div>
          </div>

          {/* Live feed panel */}
          <div className="w-80 shrink-0 rounded-lg border border-border bg-zinc-950 flex flex-col overflow-hidden" style={{ maxHeight: "calc(100vh - 240px)" }}>
            <LiveFeed />
          </div>
        </div>
      </main>
    </div>
  );
}
