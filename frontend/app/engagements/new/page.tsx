"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Platform } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";

const PLATFORMS: Platform[] = ["bbs", "h1", "bugcrowd", "hackenproof"];
const AGENTS = ["recon", "js_miner", "oauth_chain", "desync", "race", "ssrf", "agentic_target", "chain_hunter", "validator", "report"];

export default function NewEngagement() {
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState<Platform>("bbs");
  const [scopeText, setScopeText] = useState("");
  const [budget, setBudget] = useState("5.00");
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(new Set(AGENTS));

  const createMut = useMutation({
    mutationFn: () =>
      api.engagements.create({
        name,
        platform,
        scope_urls: scopeText.split("\n").map((s) => s.trim()).filter(Boolean),
        llm_budget_usd: parseFloat(budget),
      }),
    onSuccess: async (eng) => {
      await qc.invalidateQueries({ queryKey: ["engagements"] });
      // Update agent config
      toast.success("Engagement created — starting hunt…");
      await api.engagements.start(eng.id);
      router.push(`/engagements/${eng.id}`);
    },
    onError: (e) => toast.error(String(e)),
  });

  const toggleAgent = (a: string) => {
    setEnabledAgents((prev) => {
      const next = new Set(prev);
      next.has(a) ? next.delete(a) : next.add(a);
      return next;
    });
  };

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8 max-w-2xl">
        <h1 className="text-xl font-bold mb-6">New engagement</h1>

        <Card className="bg-card border-border">
          <CardContent className="pt-6 space-y-5">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Engagement name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Acme Corp Q2"
                className="w-full bg-background border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Platform</label>
              <div className="flex gap-2">
                {PLATFORMS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPlatform(p)}
                    className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                      platform === p
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:border-primary/50"
                    }`}
                  >
                    {p.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">
                Scope URLs <span className="text-muted-foreground/50">(one per line)</span>
              </label>
              <textarea
                value={scopeText}
                onChange={(e) => setScopeText(e.target.value)}
                placeholder={"https://app.target.com\nhttps://api.target.com"}
                rows={6}
                className="w-full bg-background border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary font-mono resize-none"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">LLM budget (USD)</label>
              <input
                type="number"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                min="0.5"
                max="50"
                step="0.5"
                className="w-32 bg-background border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-2 block">Agents</label>
              <div className="flex flex-wrap gap-2">
                {AGENTS.map((a) => (
                  <button
                    key={a}
                    onClick={() => toggleAgent(a)}
                    className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                      enabledAgents.has(a)
                        ? "bg-accent text-accent-foreground border-accent"
                        : "border-border text-muted-foreground/50"
                    }`}
                  >
                    {a}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => createMut.mutate()}
              disabled={!name || !scopeText || createMut.isPending}
              className="w-full bg-primary text-primary-foreground py-2.5 rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createMut.isPending ? "Starting hunt…" : "Start hunt"}
            </button>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
