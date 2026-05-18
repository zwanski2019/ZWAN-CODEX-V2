"use client";
import { use } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useAgentStream } from "@/lib/useAgentStream";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { toast } from "sonner";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low: "bg-green-500/20 text-green-400 border-green-500/30",
  info: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

export default function EngagementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: eng } = useQuery({ queryKey: ["engagement", id], queryFn: () => api.engagements.get(id) });
  const { data: findings = [] } = useQuery({
    queryKey: ["findings", id],
    queryFn: () => api.findings.list({ engagement_id: id }),
    refetchInterval: 5000,
  });
  const { events, connected } = useAgentStream(id);
  const qc = useQueryClient();
  const startMut = useMutation({
    mutationFn: () => api.engagements.start(id),
    onSuccess: () => toast.success("Hunt queued"),
    onError: (e) => toast.error(String(e)),
  });

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8 grid grid-cols-2 gap-6">
        {/* Left: engagement info + findings */}
        <div className="space-y-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold">{eng?.name ?? "…"}</h1>
              <button
                onClick={() => startMut.mutate()}
                disabled={startMut.isPending}
                className="text-xs bg-primary text-primary-foreground px-3 py-1 rounded hover:bg-primary/90 disabled:opacity-50"
              >
                {startMut.isPending ? "Queuing…" : "Re-run hunt"}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              {eng?.platform.toUpperCase()} · {eng?.scope_urls.length ?? 0} URLs · ${eng?.llm_spent_usd?.toFixed(2) ?? "0.00"} spent
            </p>
          </div>

          <div className="space-y-2">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Findings</h2>
            {findings.map((f) => (
              <Link key={f.id} href={`/engagements/${id}/findings/${f.id}`}>
                <Card className="bg-card border-border hover:border-primary/40 transition-colors cursor-pointer">
                  <CardContent className="py-3 px-4 flex items-center gap-3">
                    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border shrink-0", SEVERITY_COLOR[f.severity])}>
                      {f.severity.toUpperCase()}
                    </span>
                    <span className="flex-1 text-sm truncate">{f.title}</span>
                    {f.cvss_score && <span className="text-xs text-muted-foreground shrink-0">{f.cvss_score.toFixed(1)}</span>}
                    <Badge variant="outline" className={cn("text-[10px] shrink-0", f.status === "valid" ? "border-green-500/50 text-green-400" : f.status === "killed" ? "border-red-500/30 text-red-400/60" : "")}>{f.status}</Badge>
                  </CardContent>
                </Card>
              </Link>
            ))}
            {findings.length === 0 && (
              <p className="text-xs text-muted-foreground py-4 text-center">Waiting for findings…</p>
            )}
          </div>
        </div>

        {/* Right: live agent trace stream */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Agent trace</h2>
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded", connected ? "bg-green-500/20 text-green-400" : "bg-zinc-500/20 text-zinc-400")}>
              {connected ? "live" : "offline"}
            </span>
          </div>
          <div className="bg-zinc-950 border border-border rounded-md h-[calc(100vh-12rem)] overflow-y-auto p-3 space-y-1 font-mono text-xs">
            {events.length === 0 && (
              <span className="text-muted-foreground/50">No events yet.</span>
            )}
            {events.map((ev, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-muted-foreground/50 select-none">{ev.agent ?? "sys"}</span>
                <span className={cn("font-semibold", ev.type === "error" ? "text-red-400" : ev.type === "done" ? "text-green-400" : "text-zinc-300")}>
                  [{ev.type}]
                </span>
                <span className="text-zinc-400 truncate">{JSON.stringify(ev.data)}</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
