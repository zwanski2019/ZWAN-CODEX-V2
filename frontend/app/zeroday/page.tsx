"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Engagement, type Finding } from "@/lib/api";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import {
  Zap,
  ChevronRight,
  AlertTriangle,
  Shield,
  Code2,
  Swords,
  FlaskConical,
  Play,
  RefreshCw,
  Radio,
} from "lucide-react";
import { toast } from "sonner";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8731";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8731";

const SEV_STYLES: Record<string, string> = {
  critical: "border-red-500 text-red-400 bg-red-500/10",
  high: "border-orange-500 text-orange-400 bg-orange-500/10",
  medium: "border-yellow-500 text-yellow-400 bg-yellow-500/10",
};

const CATEGORY_LABEL: Record<string, string> = {
  prototype_pollution: "Prototype Pollution",
  eval_injection: "eval() Injection",
  dom_xss: "DOM XSS",
  logic_flaw: "Logic Flaw",
  broken_auth: "Broken Auth",
  race_condition: "Race Condition",
  crypto_flaw: "Crypto Flaw",
  ssrf: "SSRF",
  path_traversal: "Path Traversal",
  deserialization: "Deserialization",
  mass_assignment: "Mass Assignment",
  idor: "IDOR",
  jwt_confusion: "JWT Confusion",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold uppercase tracking-wide",
        SEV_STYLES[severity] ?? "border-zinc-500 text-zinc-400 bg-zinc-500/10"
      )}
    >
      <AlertTriangle size={10} />
      {severity}
    </span>
  );
}

function CategoryBadge({ category }: { category?: string }) {
  if (!category) return null;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-purple-500/40 text-purple-400 bg-purple-500/10 text-xs">
      <Code2 size={10} />
      {CATEGORY_LABEL[category] ?? category}
    </span>
  );
}

interface TraceEvent {
  type: string;
  data: { message?: string; title?: string; severity?: string; cvss?: number };
  agent?: string;
}

function FindingCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const category = finding.meta?.category;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-accent/30 transition-colors"
      >
        <ChevronRight
          size={14}
          className={cn("text-muted-foreground shrink-0 transition-transform", open && "rotate-90")}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <SeverityBadge severity={finding.severity} />
            <CategoryBadge category={category} />
            {finding.cvss_score && (
              <span className="text-xs text-muted-foreground">CVSS {finding.cvss_score.toFixed(1)}</span>
            )}
          </div>
          <p className="text-sm font-medium truncate">{finding.title}</p>
          {finding.meta?.location && (
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{finding.meta.location}</p>
          )}
        </div>
      </button>

      {open && (
        <div className="border-t border-border px-4 pb-4 pt-3 space-y-4">
          {finding.description && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Shield size={11} /> Vulnerability Description
              </div>
              <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
                {finding.description}
              </p>
            </section>
          )}

          {finding.impact && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Swords size={11} /> Exploit Vector & Attack Chain
              </div>
              <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
                {finding.impact}
              </p>
            </section>
          )}

          {finding.reproducer && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <FlaskConical size={11} /> Proof of Concept
              </div>
              <pre className="text-xs bg-zinc-900 border border-border rounded p-3 overflow-x-auto text-green-400 whitespace-pre-wrap">
                {finding.reproducer}
              </pre>
            </section>
          )}

          {finding.http_transcript && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <Code2 size={11} /> Source / Location
              </div>
              <p className="text-xs text-muted-foreground break-all">{finding.http_transcript}</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function LiveTrace({
  engagementId,
  active,
}: {
  engagementId: string;
  active: boolean;
}) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!active) return;
    const ws = new WebSocket(`${WS_BASE}/ws/${engagementId}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const ev: TraceEvent = JSON.parse(e.data);
        if (ev.agent === "zeroday_scanner") {
          setEvents((prev) => [...prev.slice(-99), ev]);
          bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        }
      } catch {
        // ignore malformed
      }
    };

    return () => {
      ws.close();
    };
  }, [engagementId, active]);

  if (!active && events.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-zinc-900 p-3">
      <div className="flex items-center gap-2 mb-2">
        <Radio size={11} className="text-green-400 animate-pulse" />
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Live Trace</span>
      </div>
      <div className="space-y-1 max-h-48 overflow-y-auto font-mono text-xs text-muted-foreground">
        {events.map((ev, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-purple-400 shrink-0">[{ev.type}]</span>
            <span className={ev.type === "finding" ? "text-orange-400" : ""}>
              {ev.data.message ?? (ev.data.title ? `FINDING: ${ev.data.title} (${ev.data.severity?.toUpperCase()})` : JSON.stringify(ev.data))}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

export default function ZeroDayPage() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scanActive, setScanActive] = useState(false);

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ["engagements"],
    queryFn: () => api.engagements.list(),
  });

  const { data: allFindings = [], isFetching } = useQuery<Finding[]>({
    queryKey: ["zeroday-findings", selectedId],
    queryFn: () =>
      selectedId
        ? api.findings.list({ engagement_id: selectedId })
        : Promise.resolve([]),
    enabled: !!selectedId,
    refetchInterval: scanActive ? 8000 : false,
  });

  // Filter to only zeroday_scanner findings
  const findings = allFindings.filter(
    (f) => f.meta?.source_agent === "zeroday_scanner"
  );

  const scanMut = useMutation({
    mutationFn: (id: string) => api.zeroday.startScan(id),
    onSuccess: () => {
      toast.success("Zero-Day scan queued — watching for findings...");
      setScanActive(true);
      setTimeout(() => {
        setScanActive(false);
        qc.invalidateQueries({ queryKey: ["zeroday-findings", selectedId] });
      }, 120_000); // stop live refresh after 2 min
    },
    onError: () => toast.error("Failed to queue scan"),
  });

  const selected = engagements.find((e) => e.id === selectedId);
  const critCount = findings.filter((f) => f.severity === "critical").length;
  const highCount = findings.filter((f) => f.severity === "high").length;

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
          <Zap size={20} className="text-yellow-400" />
        </div>
        <div>
          <h1 className="text-lg font-bold">Zero-Day Scanner</h1>
          <p className="text-xs text-muted-foreground">
            AI-driven deep analysis · JS files, APIs, logic flaws · CVSS ≥ 7.0 only
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded border border-purple-500/30 bg-purple-500/10">
          <span className="text-[10px] font-mono text-purple-400">X-JURA-BUGBOUNTY: Zwanski</span>
        </div>
      </div>

      <div className="grid grid-cols-[220px_1fr] gap-6">
        {/* Engagement selector */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Select Engagement
          </p>
          {engagements.length === 0 && (
            <p className="text-xs text-muted-foreground">No engagements yet</p>
          )}
          {engagements.map((eng) => (
            <button
              key={eng.id}
              onClick={() => setSelectedId(eng.id)}
              className={cn(
                "w-full text-left rounded-md px-3 py-2 text-xs border transition-colors",
                selectedId === eng.id
                  ? "border-yellow-500/50 bg-yellow-500/10 text-yellow-300"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-border/80 hover:bg-accent/30"
              )}
            >
              <div className="font-medium truncate">{eng.name}</div>
              <div className="text-[10px] opacity-60 mt-0.5 uppercase">{eng.platform}</div>
            </button>
          ))}
        </div>

        {/* Main panel */}
        <div className="space-y-4">
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground border border-dashed border-border rounded-lg">
              <Zap size={32} className="mb-3 opacity-30" />
              <p className="text-sm">Select an engagement to start scanning</p>
            </div>
          ) : (
            <>
              {/* Controls */}
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <h2 className="font-semibold text-sm">{selected?.name}</h2>
                  <p className="text-xs text-muted-foreground">
                    {selected?.scope_urls.join(", ")}
                  </p>
                </div>

                {isFetching && !scanActive && (
                  <RefreshCw size={13} className="text-muted-foreground animate-spin" />
                )}

                <button
                  onClick={() => scanMut.mutate(selectedId)}
                  disabled={scanMut.isPending || scanActive}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold border transition-colors",
                    scanActive || scanMut.isPending
                      ? "border-yellow-500/50 bg-yellow-500/20 text-yellow-300 animate-pulse"
                      : "border-yellow-500/60 bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20"
                  )}
                >
                  <Play size={12} />
                  {scanActive ? "Scanning…" : scanMut.isPending ? "Queuing…" : "Run Zero-Day Scan"}
                </button>
              </div>

              {/* Stats */}
              {findings.length > 0 && (
                <div className="flex gap-3">
                  <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
                    <div className="text-lg font-bold text-red-400">{critCount}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Critical</div>
                  </div>
                  <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
                    <div className="text-lg font-bold text-orange-400">{highCount}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">High</div>
                  </div>
                  <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
                    <div className="text-lg font-bold text-foreground">{findings.length}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Total</div>
                  </div>
                </div>
              )}

              {/* Live trace */}
              {selectedId && (
                <LiveTrace engagementId={selectedId} active={scanActive} />
              )}

              {/* Findings list */}
              {findings.length === 0 && !scanActive ? (
                <div className="flex flex-col items-center justify-center h-48 text-muted-foreground border border-dashed border-border rounded-lg">
                  <Zap size={24} className="mb-2 opacity-30" />
                  <p className="text-sm">No zero-day findings yet</p>
                  <p className="text-xs mt-1 opacity-60">Run a scan to discover logic flaws and novel vulns</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Sort: critical first */}
                  {[...findings]
                    .sort((a, b) => {
                      const order = { critical: 0, high: 1, medium: 2 };
                      return (order[a.severity as keyof typeof order] ?? 3) -
                             (order[b.severity as keyof typeof order] ?? 3);
                    })
                    .map((f) => (
                      <FindingCard key={f.id} finding={f} />
                    ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      </main>
    </div>
  );
}
