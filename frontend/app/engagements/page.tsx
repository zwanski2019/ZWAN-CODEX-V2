"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";
import { ChevronRight, Plus } from "lucide-react";

export default function EngagementsPage() {
  const { data: engagements = [], isLoading } = useQuery({
    queryKey: ["engagements"],
    queryFn: api.engagements.list,
  });

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">Engagements</h1>
          <Link
            href="/engagements/new"
            className="flex items-center gap-1 text-sm bg-primary text-primary-foreground px-3 py-1.5 rounded-md hover:bg-primary/90"
          >
            <Plus size={14} /> New
          </Link>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

        <div className="space-y-2">
          {engagements.map((e) => (
            <Link key={e.id} href={`/engagements/${e.id}`}>
              <Card className="bg-card border-border hover:border-primary/50 transition-colors">
                <CardContent className="flex items-center gap-4 py-3 px-4">
                  <div className="flex-1">
                    <div className="font-medium text-sm">{e.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {e.platform.toUpperCase()} · {e.scope_urls.length} URLs · ${e.llm_spent_usd.toFixed(2)} spent
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
          {!isLoading && engagements.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-12">
              No engagements yet.{" "}
              <Link href="/engagements/new" className="text-primary hover:underline">
                Start your first hunt.
              </Link>
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
