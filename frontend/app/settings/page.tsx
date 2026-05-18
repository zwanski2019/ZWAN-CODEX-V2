"use client";
import { Nav } from "@/components/nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8 max-w-xl">
        <h1 className="text-xl font-bold mb-6">Settings</h1>
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-sm">API keys</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-2">
            <p>API keys are configured via the <code className="bg-zinc-800 px-1 py-0.5 rounded">.env</code> file on the server.</p>
            <p>Restart the backend container after changing keys.</p>
            <div className="mt-4 space-y-1 font-mono text-[11px]">
              <div>ANTHROPIC_API_KEY — Claude LLM calls</div>
              <div>OPENROUTER_API_KEY — fallback model routing</div>
              <div>BURP_API_KEY — Burp Pro REST integration</div>
              <div>INTERACTSH_TOKEN — OAST collaborator</div>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
