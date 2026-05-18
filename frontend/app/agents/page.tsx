"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const STATUS_COLOR: Record<string, string> = {
  running: "border-blue-500/50 text-blue-400",
  done: "border-green-500/50 text-green-400",
  failed: "border-red-500/50 text-red-400",
  queued: "border-zinc-500/50 text-zinc-400",
};

export default function AgentsPage() {
  const { data: runs = [] } = useQuery({
    queryKey: ["agent-runs"],
    queryFn: () => api.agents.runs(),
    refetchInterval: 3000,
  });

  const totalCost = runs.reduce((s, r) => s + r.llm_cost_usd, 0);

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">Agent runs</h1>
          <span className="text-xs text-muted-foreground">Total LLM cost: ${totalCost.toFixed(4)}</span>
        </div>
        <div className="space-y-2">
          {runs.map((r) => (
            <Card key={r.id} className="bg-card border-border">
              <CardContent className="py-2.5 px-4 flex items-center gap-3">
                <span className="text-sm font-medium w-32 truncate">{r.agent_name}</span>
                <Badge variant="outline" className={`text-[10px] ${STATUS_COLOR[r.status] ?? ""}`}>
                  {r.status}
                </Badge>
                <span className="text-xs text-muted-foreground flex-1 truncate">{r.engagement_id}</span>
                <span className="text-xs text-muted-foreground">
                  {r.llm_tokens_in + r.llm_tokens_out} tok · ${r.llm_cost_usd.toFixed(4)}
                </span>
                {r.error && <span className="text-xs text-red-400 truncate max-w-xs">{r.error}</span>}
              </CardContent>
            </Card>
          ))}
          {runs.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-12">No agent runs yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
