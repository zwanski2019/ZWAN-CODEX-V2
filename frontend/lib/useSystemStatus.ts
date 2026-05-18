"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { rawReq } from "./api";

export interface ServiceStatus {
  up: boolean;
  pid?: number | null;
}

export interface SystemStatus {
  backend: ServiceStatus;
  worker: ServiceStatus;
  frontend: ServiceStatus;
}

export function useSystemStatus() {
  return useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => rawReq<SystemStatus>("/api/system/status"),
    refetchInterval: 5000,
    retry: false,
  });
}

export function useSystemStop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => rawReq("/api/system/stop", { method: "POST" }),
    onSettled: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["system-status"] }), 1500);
    },
  });
}
