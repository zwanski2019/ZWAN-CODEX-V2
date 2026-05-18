"use client";
import { use, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low: "bg-green-500/20 text-green-400 border-green-500/30",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={copy} className="p-1 rounded hover:bg-zinc-700 transition-colors">
      {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} className="text-muted-foreground" />}
    </button>
  );
}

function CodeBlock({ code, lang = "" }: { code: string; lang?: string }) {
  return (
    <div className="relative group">
      <pre className="bg-zinc-950 border border-border rounded-md p-4 text-xs overflow-x-auto whitespace-pre-wrap break-all">
        <code>{code}</code>
      </pre>
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

export default function FindingPage({
  params,
}: {
  params: Promise<{ id: string; fid: string }>;
}) {
  const { id, fid } = use(params);
  const qc = useQueryClient();

  const { data: finding, isLoading } = useQuery({
    queryKey: ["finding", fid],
    queryFn: () => api.findings.get(fid),
  });

  const updateMut = useMutation({
    mutationFn: (body: Parameters<typeof api.findings.update>[1]) =>
      api.findings.update(fid, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finding", fid] });
      qc.invalidateQueries({ queryKey: ["findings", id] });
      toast.success("Finding updated");
    },
    onError: (e) => toast.error(String(e)),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Nav />
        <main className="ml-56 flex-1 p-8 text-muted-foreground text-sm">Loading…</main>
      </div>
    );
  }

  if (!finding) return null;

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8 max-w-4xl">
        {/* Header */}
        <div className="mb-6 space-y-2">
          <div className="flex items-start gap-3">
            <span className={cn("text-xs font-bold px-2 py-1 rounded border shrink-0 mt-0.5", SEVERITY_COLOR[finding.severity])}>
              {finding.severity.toUpperCase()}
            </span>
            <h1 className="text-xl font-bold leading-tight">{finding.title}</h1>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {finding.cvss_score && <span>CVSS {finding.cvss_score.toFixed(1)}</span>}
            <Badge variant="outline" className="text-[10px]">{finding.status}</Badge>
            <div className="flex gap-2 ml-auto">
              {finding.status !== "valid" && (
                <button
                  onClick={() => updateMut.mutate({ status: "valid" as any })}
                  className="text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-500"
                >
                  Mark valid
                </button>
              )}
              {finding.status !== "killed" && (
                <button
                  onClick={() => updateMut.mutate({ status: "killed" as any })}
                  className="text-xs bg-red-800 text-white px-3 py-1 rounded hover:bg-red-700"
                >
                  Kill
                </button>
              )}
            </div>
          </div>
        </div>

        <Tabs defaultValue="report">
          <TabsList className="bg-card border border-border mb-4">
            <TabsTrigger value="report">Report</TabsTrigger>
            <TabsTrigger value="reproducer">Reproducer</TabsTrigger>
            <TabsTrigger value="http">HTTP Transcript</TabsTrigger>
            <TabsTrigger value="validator">Validator</TabsTrigger>
          </TabsList>

          {/* Report tab — full submission-ready markdown */}
          <TabsContent value="report" className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Submission-ready markdown</span>
              <CopyButton text={finding.report_md || _buildFallbackReport(finding)} />
            </div>
            <CodeBlock code={finding.report_md || _buildFallbackReport(finding)} lang="markdown" />
          </TabsContent>

          {/* Reproducer tab */}
          <TabsContent value="reproducer" className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Steps to reproduce</span>
              <CopyButton text={finding.reproducer} />
            </div>
            <CodeBlock code={finding.reproducer || "No reproducer yet."} />
          </TabsContent>

          {/* HTTP Transcript */}
          <TabsContent value="http" className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Raw HTTP traffic</span>
              <CopyButton text={finding.description + "\n\n" + finding.impact} />
            </div>
            <CodeBlock code={finding.description + (finding.impact ? "\n\n" + finding.impact : "")} lang="http" />
          </TabsContent>

          {/* Validator reasoning */}
          <TabsContent value="validator" className="space-y-3">
            <span className="text-xs text-muted-foreground">ValidatorAgent reasoning</span>
            <div className="bg-zinc-950 border border-border rounded-md p-4 text-xs text-zinc-300 whitespace-pre-wrap">
              {finding.validator_reasoning || "Not yet validated."}
            </div>
            {finding.dup_similarity != null && (
              <div className={cn("text-xs px-3 py-2 rounded border", finding.dup_similarity > 0.85 ? "bg-red-500/10 border-red-500/30 text-red-400" : "bg-zinc-800 border-border text-zinc-400")}>
                Duplicate similarity: {(finding.dup_similarity * 100).toFixed(0)}%
                {finding.dup_similarity > 0.85 && " ⚠ Likely duplicate"}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

function _buildFallbackReport(finding: any): string {
  return `## Summary

${finding.description}

## Severity

**${finding.severity.charAt(0).toUpperCase() + finding.severity.slice(1)}** — CVSS ${finding.cvss_score ?? "N/A"}

## Steps to reproduce

${finding.reproducer || "See HTTP transcript."}

## Impact

${finding.impact}
`;
}
