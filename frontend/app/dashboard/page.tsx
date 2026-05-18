"use client";
import { useQuery } from "@tanstack/react-query";
import { api, type Engagement, type Finding } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { Target, ShieldCheck, Skull, DollarSign } from "lucide-react";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low: "bg-green-500/20 text-green-400 border-green-500/30",
  info: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

export default function Dashboard() {
  const { data: engagements = [] } = useQuery({ queryKey: ["engagements"], queryFn: api.engagements.list });
  const { data: findings = [] } = useQuery({ queryKey: ["findings"], queryFn: () => api.findings.list() });

  const valid = findings.filter((f) => f.status === "valid").length;
  const total = findings.length;
  const validRate = total ? Math.round((valid / total) * 100) : 0;
  const spent = engagements.reduce((s, e) => s + e.llm_spent_usd, 0);

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8">
        <h1 className="text-xl font-bold mb-6">Dashboard</h1>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard icon={<Target size={16} />} label="Engagements" value={engagements.length} />
          <StatCard icon={<ShieldCheck size={16} />} label="Valid findings" value={valid} />
          <StatCard
            icon={<Skull size={16} />}
            label="Valid rate"
            value={`${validRate}%`}
            highlight={validRate >= 60}
          />
          <StatCard icon={<DollarSign size={16} />} label="LLM spent" value={`$${spent.toFixed(2)}`} />
        </div>

        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Recent findings
          </h2>
          <Link href="/engagements/new" className="text-xs text-primary hover:underline">
            + New engagement
          </Link>
        </div>

        <div className="space-y-2">
          {findings.slice(0, 20).map((f) => (
            <FindingRow key={f.id} finding={f} />
          ))}
          {findings.length === 0 && (
            <p className="text-sm text-muted-foreground py-8 text-center">
              No findings yet. Start a hunt.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function StatCard({ icon, label, value, highlight }: { icon: React.ReactNode; label: string; value: string | number; highlight?: boolean }) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="pt-4">
        <div className="flex items-center gap-2 text-muted-foreground mb-1">
          {icon}
          <span className="text-xs">{label}</span>
        </div>
        <div className={`text-2xl font-bold ${highlight ? "text-green-400" : ""}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <Link href={`/engagements/${finding.engagement_id}`}>
      <div className="flex items-center gap-3 rounded-md border border-border bg-card/50 px-4 py-2 hover:bg-card transition-colors">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${SEVERITY_COLOR[finding.severity] ?? ""}`}>
          {finding.severity.toUpperCase()}
        </span>
        <span className="text-sm flex-1 truncate">{finding.title}</span>
        {finding.cvss_score && (
          <span className="text-xs text-muted-foreground">CVSS {finding.cvss_score.toFixed(1)}</span>
        )}
        <Badge variant="outline" className="text-[10px]">
          {finding.status}
        </Badge>
      </div>
    </Link>
  );
}
