"use client";
import { useState } from "react";
import { useSystemStatus, useSystemStop } from "@/lib/useSystemStatus";
import { cn } from "@/lib/utils";
import { Power, RefreshCw } from "lucide-react";
import { toast } from "sonner";

function Dot({ up }: { up: boolean }) {
  return (
    <span
      className={cn(
        "inline-block w-1.5 h-1.5 rounded-full",
        up ? "bg-green-400" : "bg-red-500"
      )}
    />
  );
}

export function SystemBar() {
  const { data: status } = useSystemStatus();
  const stopMut = useSystemStop();
  const [confirming, setConfirming] = useState(false);

  const allUp =
    status?.backend?.up && status?.worker?.up && status?.frontend?.up;

  const handleStop = () => {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000);
      return;
    }
    setConfirming(false);
    stopMut.mutate(undefined, {
      onSuccess: () => toast.success("All services stopped"),
      onError: () => toast.info("Backend stopping (connection will drop)"),
    });
  };

  return (
    <div className="mt-auto px-3 pb-4 space-y-2">
      {/* Service status dots */}
      <div className="rounded-md border border-border bg-zinc-900 px-3 py-2 space-y-1.5">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          System
        </p>
        {(["backend", "worker", "frontend"] as const).map((svc) => (
          <div key={svc} className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground capitalize">{svc}</span>
            <Dot up={status?.[svc]?.up ?? false} />
          </div>
        ))}
      </div>

      {/* Stop button */}
      <button
        onClick={handleStop}
        disabled={stopMut.isPending}
        className={cn(
          "w-full flex items-center justify-center gap-2 text-xs py-1.5 rounded-md border transition-colors",
          confirming
            ? "border-red-500 bg-red-500/20 text-red-400 animate-pulse"
            : "border-border text-muted-foreground hover:border-red-500/50 hover:text-red-400"
        )}
      >
        <Power size={11} />
        {stopMut.isPending
          ? "Stopping…"
          : confirming
          ? "Click again to confirm"
          : "Stop all services"}
      </button>
    </div>
  );
}
