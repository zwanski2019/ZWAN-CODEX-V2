"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Engagement, type Finding } from "@/lib/api";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  Target,
  ShieldCheck,
  Skull,
  DollarSign,
  TrendingUp,
  Activity,
  Radio,
  ChevronRight,
} from "lucide-react";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8731";

// H1 / Bugcrowd mid-range estimates 2026
const BOUNTY_EST: Record<string, { lo: number; hi: number }> = {
  critical: { lo: 5000, hi: 25000 },
  high:     { lo: 1000, hi:  5000 },
  medium:   { lo:  200, hi:  1000 },
  low:      { lo:   50, hi:   200 },
  info:     { lo:    0, hi:     0 },
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high:     "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium:   "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low:      "bg-green-500/20 text-green-400 border-green-500/30",
  info:     "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

const AGENT_COLORS: Record<string, string> = {
  recon:           "text-blue-400",
  js_miner:        "text-yellow-400",
  oauth_chain:     "text-purple-400",
  desync:          "text-red-400",
  race:            "text-orange-400",
  ssrf:            "text-pink-400",
  chain_hunter:    "text-cyan-400",
  validator:       "text-green-400",
  report:          "text-emerald-400",
  zeroday_scanner: "text-yellow-300",
  agentic_target:  "text-violet-400",
};

function estimateEarnings(findings: Finding[]) {
  const payable = findings.filter((f) => f.status === "valid" || f.status === "submitted");
  return payable.reduce(
    (acc, f) => {
      const range = BOUNTY_EST[f.severity] ?? { lo: 0, hi: 0 };
      return { lo: acc.lo + range.lo, hi: acc.hi + range.hi };
    },
    { lo: 0, hi: 0 }
  );
}

function fmt(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(0)}k`;
  return `$${n}`;
}

// ─── Mini live feed ───────────────────────────────────────────────────────────

interface MiniEvent {
  id: number;
  agent?: string;
  type: string;
  message: string;
  ts: string;
}

let _eid = 0;

function MiniLiveFeed() {
  const [events, setEvents] = useState<MiniEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/global`);

    ws.onmessage = (e) => {
      try {
        const raw = JSON.parse(e.data);
        const msg: string =
          (raw.data?.message ??
          (raw.data?.title ? `${raw.data.title} [${raw.data.severity?.toUpperCase()}]` : "")) ||
          raw.type;

        setEvents((prev) => [
          ...prev.slice(-19),
          { id: _eid++, agent: raw.agent, type: raw.type ?? "event", message: msg, ts: raw.ts ?? new Date().toISOString() },
        ]);
      } catch {
        // ignore
      }
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Radio size={11} className="text-green-400 animate-pulse" />
        <span className="text-xs font-semibold">Live Agent Activity</span>
        <Link href="/agents" className="ml-auto text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-0.5">
          Mission Control <ChevronRight size={10} />
        </Link>
      </div>
      <div className="p-3 font-mono text-[11px] space-y-0.5 max-h-44 overflow-y-auto">
        {events.length === 0 && (
          <p className="text-muted-foreground/40 text-center py-4">No agent activity yet</p>
        )}
        {events.map((ev) => (
          <div key={ev.id} className="flex gap-2 leading-relaxed">
            <span className="text-muted-foreground/30 shrink-0">
              {new Date(ev.ts).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            {ev.agent && (
              <span className={cn("shrink-0", AGENT_COLORS[ev.agent] ?? "text-zinc-400")}>
                [{ev.agent}]
              </span>
            )}
            <span className={cn(
              "break-all",
              ev.type === "finding" ? "text-orange-400" :
              ev.type === "error"   ? "text-red-400" :
              "text-muted-foreground"
            )}>
              {ev.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Components ───────────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-4">
      <div className="flex items-center gap-2 text-muted-foreground mb-1.5">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className={cn("text-2xl font-bold", highlight ? "text-green-400" : "")}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground/60 mt-0.5">{sub}</div>}
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <Link href={`/engagements/${finding.engagement_id}`}>
      <div className="flex items-center gap-3 rounded-md border border-border bg-card/50 px-4 py-2.5 hover:bg-card transition-colors">
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border shrink-0", SEVERITY_COLOR[finding.severity] ?? "")}>
          {finding.severity.toUpperCase()}
        </span>
        <span className="text-sm flex-1 truncate">{finding.title}</span>
        {finding.cvss_score && (
          <span className="text-xs text-muted-foreground shrink-0">CVSS {finding.cvss_score.toFixed(1)}</span>
        )}
        <span className={cn(
          "text-[10px] px-1.5 py-0.5 rounded border shrink-0",
          finding.status === "valid" || finding.status === "submitted"
            ? "border-green-500/30 text-green-400 bg-green-500/10"
            : "border-border text-muted-foreground"
        )}>
          {finding.status}
        </span>
      </div>
    </Link>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ["engagements"],
    queryFn: api.engagements.list,
  });
  const { data: findings = [] } = useQuery<Finding[]>({
    queryKey: ["findings"],
    queryFn: () => api.findings.list(),
    refetchInterval: 15_000,
  });

  const valid     = findings.filter((f) => f.status === "valid" || f.status === "submitted").length;
  const total     = findings.length;
  const validRate = total ? Math.round((valid / total) * 100) : 0;
  const spent     = engagements.reduce((s, e) => s + e.llm_spent_usd, 0);
  const earnings  = estimateEarnings(findings);

  const critCount = findings.filter((f) => f.severity === "critical").length;
  const highCount = findings.filter((f) => f.severity === "high").length;

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-6 max-w-6xl">

        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">Dashboard</h1>
          <Link
            href="/engagements/new"
            className="text-xs px-3 py-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:border-border/80 transition-colors"
          >
            + New engagement
          </Link>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <StatCard
            icon={<Target size={15} className="text-blue-400" />}
            label="Engagements"
            value={engagements.length}
          />
          <StatCard
            icon={<ShieldCheck size={15} className="text-green-400" />}
            label="Valid findings"
            value={valid}
            sub={`${critCount} crit · ${highCount} high`}
          />
          <StatCard
            icon={<Skull size={15} />}
            label="Valid rate"
            value={`${validRate}%`}
            highlight={validRate >= 60}
          />
          <StatCard
            icon={<DollarSign size={15} className="text-red-400" />}
            label="LLM spent"
            value={`$${spent.toFixed(2)}`}
          />
          <StatCard
            icon={<TrendingUp size={15} className="text-yellow-400" />}
            label="Est. earnings"
            value={earnings.lo > 0 ? `${fmt(earnings.lo)}–${fmt(earnings.hi)}` : "$0"}
            sub={earnings.lo > 0 ? "H1/BC mid-range · valid only" : "No paid findings yet"}
            highlight={earnings.lo > 0}
          />
        </div>

        <div className="grid grid-cols-[1fr_340px] gap-5">
          {/* Left: findings */}
          <div>
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              Recent findings
            </h2>
            <div className="space-y-1.5">
              {findings.slice(0, 25).map((f) => (
                <FindingRow key={f.id} finding={f} />
              ))}
              {findings.length === 0 && (
                <p className="text-sm text-muted-foreground py-12 text-center">
                  No findings yet. Start a hunt.
                </p>
              )}
            </div>
          </div>

          {/* Right: live feed + severity breakdown */}
          <div className="space-y-4">
            <MiniLiveFeed />

            {/* Severity breakdown */}
            {findings.length > 0 && (
              <div className="rounded-lg border border-border bg-card p-4">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Activity size={11} /> Severity Breakdown
                </p>
                <div className="space-y-2">
                  {(["critical", "high", "medium", "low"] as const).map((sev) => {
                    const count = findings.filter((f) => f.severity === sev).length;
                    const pct   = total ? Math.round((count / total) * 100) : 0;
                    const range = BOUNTY_EST[sev];
                    return (
                      <div key={sev}>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className={cn("uppercase font-semibold", SEVERITY_COLOR[sev].split(" ")[1])}>
                            {sev}
                          </span>
                          <span className="text-muted-foreground">
                            {count} · {fmt(range.lo)}–{fmt(range.hi)}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all",
                              sev === "critical" ? "bg-red-500" :
                              sev === "high"     ? "bg-orange-500" :
                              sev === "medium"   ? "bg-yellow-500" : "bg-green-500"
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
