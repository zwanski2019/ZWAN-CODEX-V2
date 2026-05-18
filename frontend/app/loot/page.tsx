"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Card, CardContent } from "@/components/ui/card";

export default function LootPage() {
  const { data: assets = [] } = useQuery({ queryKey: ["assets"], queryFn: () => api.loot.assets() });
  const { data: secrets = [] } = useQuery({ queryKey: ["secrets"], queryFn: () => api.loot.secrets() });

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8">
        <h1 className="text-xl font-bold mb-6">Loot</h1>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              Assets ({assets.length})
            </h2>
            <div className="space-y-1">
              {(assets as any[]).map((a) => (
                <Card key={a.id} className="bg-card border-border">
                  <CardContent className="py-2 px-3 text-xs">
                    <span className={a.is_live ? "text-green-400" : "text-muted-foreground"}>●</span>
                    {" "}{a.host}
                    {a.tech_stack?.length > 0 && (
                      <span className="text-muted-foreground ml-2">{a.tech_stack.join(", ")}</span>
                    )}
                  </CardContent>
                </Card>
              ))}
              {assets.length === 0 && <p className="text-xs text-muted-foreground">No assets yet.</p>}
            </div>
          </div>
          <div>
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              Secrets ({secrets.length})
            </h2>
            <div className="space-y-1">
              {(secrets as any[]).map((s) => (
                <Card key={s.id} className="bg-card border-border">
                  <CardContent className="py-2 px-3 text-xs">
                    <span className="text-orange-400">{s.secret_type}</span>
                    {" — "}{s.source_url}
                  </CardContent>
                </Card>
              ))}
              {secrets.length === 0 && <p className="text-xs text-muted-foreground">No secrets found.</p>}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
