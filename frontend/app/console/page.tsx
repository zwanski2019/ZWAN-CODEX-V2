"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import {
  Terminal,
  Wifi,
  WifiOff,
  Play,
  Square,
  AlertTriangle,
  CheckCircle2,
  Shield,
  Zap,
  FlipHorizontal,
  Globe,
  Target,
  Code2,
  Key,
  Radio,
  Database,
  ScanLine,
} from "lucide-react";

const AGENT_WS = process.env.NEXT_PUBLIC_AGENT_WS ?? "ws://127.0.0.1:8788/ws";
const AGENT_HTTP = process.env.NEXT_PUBLIC_AGENT_HTTP ?? "http://127.0.0.1:8788";

// ── Quick-action preset workflows ────────────────────────────────────────────

function extractTarget(scopeYaml: string): string {
  const m = scopeYaml.match(/domains[^:]*:[^[\n]*(?:\[["']?|-)["']?\*?\.?([a-zA-Z0-9][a-zA-Z0-9._-]+)/);
  return m ? m[1] : "";
}

const PRESETS = [
  {
    label: "Full Recon",
    icon: Target,
    color: "text-cyan-400 border-cyan-400/30 hover:bg-cyan-400/10",
    goal: (t: string) =>
      `Enumerate all subdomains of ${t} with subfinder and amass. Probe live hosts with httpx. Run nuclei recon templates on discovered services. Screenshot interesting endpoints.`,
  },
  {
    label: "JS Mine",
    icon: Code2,
    color: "text-yellow-400 border-yellow-400/30 hover:bg-yellow-400/10",
    goal: (t: string) =>
      `Crawl ${t} with katana depth 3, collect all URLs with gau. Download every JavaScript file and mine for hardcoded API keys, tokens, secrets, Sentry DSNs, and hidden API endpoints.`,
  },
  {
    label: "OAuth Hunt",
    icon: Key,
    color: "text-purple-400 border-purple-400/30 hover:bg-purple-400/10",
    goal: (t: string) =>
      `Find all OAuth 2.0 and OIDC endpoints on ${t}. Test for PKCE stripping, redirect_uri bypass with double-encoded fragments (%2523), state fixation, and dynamic client registration abuse.`,
  },
  {
    label: "SSRF Probe",
    icon: Globe,
    color: "text-pink-400 border-pink-400/30 hover:bg-pink-400/10",
    goal: (t: string) =>
      `Find all URL parameters on ${t} that accept external URLs: webhook, redirect, url, src, href, path. Test each for SSRF. Target PDF generators, image processors, and webhook relay endpoints.`,
  },
  {
    label: "Race Conds",
    icon: Zap,
    color: "text-orange-400 border-orange-400/30 hover:bg-orange-400/10",
    goal: (t: string) =>
      `Find financial, payment, transfer, withdrawal, and coupon endpoints on ${t}. Test for race conditions on state-changing operations that should execute only once. Focus on balance and limit checks.`,
  },
  {
    label: "Nuclei High",
    icon: Shield,
    color: "text-red-400 border-red-400/30 hover:bg-red-400/10",
    goal: (t: string) =>
      `Run nuclei against ${t} with high and critical severity templates only. Focus on CVEs from the last 12 months, auth bypass, and technology-specific exploits. Use caido_create_finding for confirmed hits.`,
  },
  {
    label: "Desync",
    icon: Radio,
    color: "text-rose-400 border-rose-400/30 hover:bg-rose-400/10",
    goal: (t: string) =>
      `Test ${t} for HTTP request smuggling: CL.0, H2.CL, 0.CL, and client-side desync. Use differential response analysis. Route through Caido proxy to capture all raw requests for evidence.`,
  },
  {
    label: "Caido Review",
    icon: Database,
    color: "text-amber-400 border-amber-400/30 hover:bg-amber-400/10",
    goal: (t: string) =>
      `Pull HTTP history from Caido for ${t} using caido_history. Identify 10 most interesting endpoints by auth patterns and parameter anomalies. Use caido_create_finding for any confirmed vulnerabilities.`,
  },
  {
    label: "Scope Scan",
    icon: ScanLine,
    color: "text-green-400 border-green-400/30 hover:bg-green-400/10",
    goal: (t: string) =>
      `Full scope scan of ${t}: port scan with naabu, TLS inspection with tlsx, technology fingerprint with whatweb, DNS records with dnsx. Build a complete attack surface map before any exploitation.`,
  },
];

type ConnState = "disconnected" | "connecting" | "auth_pending" | "ready" | "running";
type Mode = "manual" | "auto" | "yolo";

interface LogLine {
  id: number;
  ts: string;
  type: string;
  text: string;
  stream?: string;
}

interface PendingCmd {
  cmd_id: string;
  audit_id?: string;
  tool: string;
  rendered: string;
  tier: string;
  targets: string[];
  needs_root: boolean;
  decision: string;
  rationale: string;
  dry_run: boolean;
}

let _lid = 0;

const SCOPE_PLACEHOLDER = `# Paste your scope.yaml here
program: my-target
in_scope:
  domains: ["*.example.com"]
  ips: ["10.10.0.0/24"]
out_of_scope:
  domains: ["admin.example.com"]`;

export default function ConsolePage() {
  const [connState, setConnState] = useState<ConnState>("disconnected");
  const [token, setToken] = useState("");
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [dryRun, setDryRun] = useState(true);
  const [scope, setScope] = useState("");
  const [log, setLog] = useState<LogLine[]>([]);
  const [pending, setPending] = useState<PendingCmd | null>(null);
  const [itersLeft, setItersLeft] = useState(25);
  const [budgetSec, setBudgetSec] = useState(1800);
  const [browserFrame, setBrowserFrame] = useState<{ url: string; png_b64: string } | null>(null);
  const [caidoAlive, setCaidoAlive] = useState<boolean | null>(null);
  const [caidoHasKey, setCaidoHasKey] = useState(false);
  const [caidoLoginInfo, setCaidoLoginInfo] = useState<{
    userCode: string; verificationUrl: string; expiresAt: string;
  } | null>(null);
  const [quickTarget, setQuickTarget] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((type: string, text: string, stream?: string) => {
    setLog((prev) => [
      ...prev.slice(-499),
      { id: _lid++, ts: new Date().toLocaleTimeString("en-GB", { hour12: false }), type, text, stream },
    ]);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log.length]);

  // Auto-extract first domain from scope YAML into the quick-target field
  useEffect(() => {
    const t = extractTarget(scope);
    if (t) setQuickTarget(t);
  }, [scope]);

  // Poll Caido status every 10 s (faster while login is pending)
  useEffect(() => {
    const check = () =>
      fetch(`${AGENT_HTTP}/api/caido/status`)
        .then((r) => r.json())
        .then((d) => {
          setCaidoAlive(d.alive);
          setCaidoHasKey(d.has_key);
          if (d.has_key) setCaidoLoginInfo(null); // auth complete — clear the prompt
        })
        .catch(() => setCaidoAlive(false));
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setConnState("connecting");
    addLog("sys", `Connecting to ${AGENT_WS}…`);

    const ws = new WebSocket(AGENT_WS);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnState("auth_pending");
      addLog("sys", "Connected. Authenticating…");
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        handleMsg(msg);
      } catch {
        addLog("err", `Parse error: ${e.data}`);
      }
    };

    ws.onerror = () => {
      addLog("err", "WebSocket error.");
      setConnState("disconnected");
    };

    ws.onclose = (ev) => {
      addLog("sys", `Disconnected (${ev.code}${ev.reason ? " " + ev.reason : ""}).`);
      setConnState("disconnected");
      wsRef.current = null;
      setPending(null);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, addLog]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
  }, []);

  const handleMsg = useCallback((msg: Record<string, unknown>) => {
    const t = msg.type as string;

    if (t === "auth_ok") {
      setConnState("ready");
      addLog("sys", "Authenticated. Agent ready.");
      return;
    }
    if (t === "thought") {
      addLog("thought", `[THINK] ${msg.text}`);
      return;
    }
    if (t === "command_proposed") {
      const c = msg as unknown as PendingCmd & { type: string };
      addLog(
        c.dry_run ? "dryrun" : c.tier === "exploit" ? "exploit" : "recon",
        `[${c.tier.toUpperCase()}${c.dry_run ? " DRY" : ""}] ${c.rendered}`
      );
      if (c.decision === "needs_approval") {
        setPending(c);
      }
      return;
    }
    if (t === "awaiting_approval") {
      setConnState("running");
      return;
    }
    if (t === "output_chunk") {
      addLog("output", msg.data as string, msg.stream as string);
      return;
    }
    if (t === "command_done") {
      const ec = msg.exit_code;
      addLog(
        ec === 0 || ec === null ? "done" : "err",
        `[DONE] exit=${ec === null ? "dry-run" : ec} (${msg.duration_ms}ms)`
      );
      setPending(null);
      return;
    }
    if (t === "blocked") {
      addLog("block", `[BLOCKED] ${msg.reason}`);
      return;
    }
    if (t === "browser_frame") {
      setBrowserFrame({ url: (msg.url as string) ?? "", png_b64: (msg.png_b64 as string) ?? "" });
      return;
    }
    if (t === "browser_state") {
      const els = (msg.elements as { id: number; tag: string; text: string }[]) ?? [];
      const url = (msg.url as string) ?? "";
      addLog("sys", `[BROWSER] ${url} — ${els.length} elements`);
      return;
    }
    if (t === "budget") {
      setItersLeft((msg.iters_left as number) ?? 25);
      setBudgetSec((msg.budget_left_sec as number) ?? 1800);
      return;
    }
    if (t === "session_done") {
      setConnState("ready");
      addLog("sys", `[SESSION DONE] ${msg.summary}`);
      setPending(null);
      return;
    }
    if (t === "error") {
      addLog("err", `[ERROR] ${msg.message}`);
      return;
    }
    if (t === "sudo_prompt_required") {
      addLog("warn", "[SUDO] Look at your agent terminal and type your password.");
      return;
    }
    if (t === "pong") return;
    addLog("sys", `[${t}] ${JSON.stringify(msg)}`);
  }, [addLog]);

  const sendMsg = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const startSession = useCallback(() => {
    setLog([]);
    setBrowserFrame(null);
    setConnState("running");
    sendMsg({ type: "start_session", goal, mode, scope, dry_run: dryRun });
    addLog("sys", `Session started | mode=${mode} dry=${dryRun}`);
  }, [goal, mode, scope, dryRun, sendMsg, addLog]);

  const abortSession = useCallback(() => {
    sendMsg({ type: "abort" });
    setPending(null);
    setConnState("ready");
    addLog("sys", "Abort sent.");
  }, [sendMsg, addLog]);

  const approve = useCallback(() => {
    if (!pending) return;
    sendMsg({ type: "approve", cmd_id: pending.cmd_id });
    addLog("sys", `[APPROVED] ${pending.rendered}`);
    setPending(null);
  }, [pending, sendMsg, addLog]);

  const reject = useCallback(() => {
    if (!pending) return;
    sendMsg({ type: "reject", cmd_id: pending.cmd_id });
    addLog("sys", `[REJECTED] ${pending.rendered}`);
    setPending(null);
  }, [pending, sendMsg, addLog]);

  const setModeRemote = useCallback((m: Mode) => {
    setMode(m);
    sendMsg({ type: "set_mode", mode: m });
  }, [sendMsg]);

  const toggleDryRun = useCallback(() => {
    const next = !dryRun;
    setDryRun(next);
    sendMsg({ type: "set_dry_run", value: next });
    addLog("sys", `Dry-run ${next ? "ON" : "OFF"}`);
  }, [dryRun, sendMsg, addLog]);

  const startCaidoLogin = useCallback(async () => {
    setCaidoLoginInfo(null);
    try {
      const r = await fetch(`${AGENT_HTTP}/api/caido/login`, { method: "POST" });
      const d = await r.json();
      if (d.error) { addLog("err", `[CAIDO] ${d.error}`); return; }
      setCaidoLoginInfo({ userCode: d.userCode, verificationUrl: d.verificationUrl, expiresAt: d.expiresAt });
      addLog("sys", `[CAIDO] Visit ${d.verificationUrl} — code: ${d.userCode}`);
    } catch (e) {
      addLog("err", `[CAIDO] Login failed: ${e}`);
    }
  }, [addLog]);

  const isConnected = connState !== "disconnected" && connState !== "connecting";
  const isRunning = connState === "running";

  return (
    <div className="flex min-h-screen bg-black">
      <Nav />
      <main className="ml-56 flex-1 flex flex-col p-4 font-mono">

        {/* CRT scanline overlay */}
        <div
          className="pointer-events-none fixed inset-0 z-50"
          style={{
            background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)",
          }}
        />

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <Terminal size={18} className="text-amber-400" />
          <span className="text-amber-400 font-bold tracking-widest text-sm uppercase">
            Operator Console
          </span>
          <span className="text-amber-400/40 text-xs ml-auto">
            v2.1 · {connState.toUpperCase()}
          </span>
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              connState === "ready" || connState === "running" ? "bg-amber-400 animate-pulse" :
              connState === "connecting" || connState === "auth_pending" ? "bg-yellow-600 animate-pulse" :
              "bg-zinc-700"
            )}
          />
        </div>

        <div className="flex gap-4 flex-1 min-h-0">
          {/* Left panel: config */}
          <div className="w-72 shrink-0 flex flex-col gap-3 overflow-y-auto">

            {/* Connection */}
            <div className="border border-amber-400/20 rounded p-3 bg-zinc-950">
              <p className="text-amber-400/60 text-[10px] uppercase tracking-widest mb-2">Connect</p>
              <input
                type="password"
                placeholder="Agent token (printed on daemon start)"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                disabled={isConnected}
                className="w-full bg-black border border-amber-400/20 rounded px-2 py-1.5 text-amber-300 text-xs focus:outline-none focus:border-amber-400/60 placeholder:text-amber-400/20 mb-2"
              />
              <div className="flex gap-2">
                <button
                  onClick={connect}
                  disabled={isConnected || !token}
                  className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 disabled:opacity-30 transition-colors"
                >
                  <Wifi size={11} /> Connect
                </button>
                <button
                  onClick={disconnect}
                  disabled={!isConnected}
                  className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs border border-zinc-700 text-zinc-400 hover:bg-zinc-800 disabled:opacity-30 transition-colors"
                >
                  <WifiOff size={11} /> Disconnect
                </button>
              </div>

              {/* Caido auth row */}
              <div className="mt-2 pt-2 border-t border-amber-400/10">
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "text-[9px] uppercase tracking-widest flex items-center gap-1",
                    caidoAlive && caidoHasKey ? "text-green-400" :
                    caidoAlive ? "text-yellow-400" : "text-zinc-600"
                  )}>
                    <span className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      caidoAlive && caidoHasKey ? "bg-green-400 animate-pulse" :
                      caidoAlive ? "bg-yellow-400" : "bg-zinc-700"
                    )} />
                    Caido {caidoAlive && caidoHasKey ? "ready" : caidoAlive ? "no auth" : "offline"}
                  </span>
                  {caidoAlive && !caidoHasKey && (
                    <button
                      onClick={startCaidoLogin}
                      className="ml-auto text-[9px] px-2 py-0.5 rounded border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 transition-colors uppercase tracking-widest"
                    >
                      Login →
                    </button>
                  )}
                </div>

                {/* Pending auth approval */}
                {caidoLoginInfo && (
                  <div className="mt-2 bg-black border border-amber-400/20 rounded p-2 text-[10px]">
                    <p className="text-amber-400/70 mb-1">Open this URL and approve:</p>
                    <a
                      href={caidoLoginInfo.verificationUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-amber-300 underline break-all block mb-1"
                    >
                      {caidoLoginInfo.verificationUrl}
                    </a>
                    <p className="text-amber-400/50">
                      Code: <span className="text-amber-300 font-bold tracking-wider">{caidoLoginInfo.userCode}</span>
                    </p>
                    <p className="text-amber-400/30 mt-1">Waiting for approval…</p>
                  </div>
                )}
              </div>
            </div>

            {/* Session config */}
            <div className="border border-amber-400/20 rounded p-3 bg-zinc-950 flex flex-col gap-2">
              <p className="text-amber-400/60 text-[10px] uppercase tracking-widest">Session</p>

              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Recon objective…"
                rows={2}
                disabled={isRunning}
                className="w-full bg-black border border-amber-400/20 rounded px-2 py-1.5 text-amber-300 text-xs focus:outline-none focus:border-amber-400/60 placeholder:text-amber-400/20 resize-none"
              />

              {/* Mode */}
              <div className="flex gap-1">
                {(["manual", "auto", "yolo"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setModeRemote(m)}
                    disabled={isRunning}
                    className={cn(
                      "flex-1 py-1 text-[10px] uppercase tracking-wider rounded border transition-colors",
                      mode === m
                        ? m === "yolo"
                          ? "border-red-500/60 bg-red-500/10 text-red-400"
                          : "border-amber-400/60 bg-amber-400/10 text-amber-400"
                        : "border-zinc-800 text-zinc-600 hover:border-zinc-600"
                    )}
                  >
                    {m}
                  </button>
                ))}
              </div>

              {/* Dry-run toggle */}
              <button
                onClick={toggleDryRun}
                className={cn(
                  "flex items-center justify-between w-full px-2 py-1.5 rounded border text-xs transition-colors",
                  dryRun
                    ? "border-amber-400/50 bg-amber-400/5 text-amber-400"
                    : "border-zinc-700 text-zinc-500 hover:border-zinc-600"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <FlipHorizontal size={11} />
                  DRY RUN
                </span>
                <span className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded",
                  dryRun ? "bg-amber-400/20 text-amber-400" : "bg-zinc-800 text-zinc-600"
                )}>
                  {dryRun ? "ON" : "OFF"}
                </span>
              </button>

              {/* Scope */}
              <textarea
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                placeholder={SCOPE_PLACEHOLDER}
                rows={7}
                disabled={isRunning}
                className="w-full bg-black border border-amber-400/20 rounded px-2 py-1.5 text-amber-300/70 text-[10px] focus:outline-none focus:border-amber-400/40 placeholder:text-amber-400/15 resize-none"
              />

              {/* Start / Abort */}
              <div className="flex gap-2 mt-1">
                <button
                  onClick={startSession}
                  disabled={!isConnected || isRunning || !goal}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded text-xs border border-amber-500/40 text-amber-400 bg-amber-500/5 hover:bg-amber-500/15 disabled:opacity-30 transition-colors font-bold"
                >
                  <Play size={12} fill="currentColor" /> START HUNT
                </button>
                <button
                  onClick={abortSession}
                  disabled={!isRunning}
                  className="px-3 py-2 rounded text-xs border border-red-700/40 text-red-400 hover:bg-red-500/10 disabled:opacity-30 transition-colors"
                >
                  <Square size={12} fill="currentColor" />
                </button>
              </div>
            </div>

            {/* Budget meters */}
            <div className="border border-amber-400/20 rounded p-3 bg-zinc-950">
              <p className="text-amber-400/60 text-[10px] uppercase tracking-widest mb-2">Budget</p>
              <div className="space-y-2">
                <div>
                  <div className="flex justify-between text-[10px] text-amber-400/50 mb-1">
                    <span>Iterations</span>
                    <span>{itersLeft} / 25</span>
                  </div>
                  <div className="h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-400/60 rounded-full transition-all"
                      style={{ width: `${(itersLeft / 25) * 100}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-[10px] text-amber-400/50 mb-1">
                    <span>Wall clock</span>
                    <span>{Math.floor(budgetSec / 60)}m {budgetSec % 60}s</span>
                  </div>
                  <div className="h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-400/40 rounded-full transition-all"
                      style={{ width: `${(budgetSec / 1800) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="border border-amber-400/20 rounded p-3 bg-zinc-950">
              {/* Header row: title + Caido status */}
              <div className="flex items-center gap-2 mb-2">
                <p className="text-amber-400/60 text-[10px] uppercase tracking-widest flex-1">
                  Quick Actions
                </p>
                <span
                  className={cn(
                    "flex items-center gap-1 text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded border",
                    caidoAlive === null
                      ? "border-zinc-700 text-zinc-600"
                      : caidoAlive && caidoHasKey
                      ? "border-green-500/40 text-green-400 bg-green-500/5"
                      : caidoAlive
                      ? "border-yellow-500/40 text-yellow-400 bg-yellow-500/5"
                      : "border-red-700/40 text-red-500"
                  )}
                  title={
                    caidoAlive && caidoHasKey
                      ? "Caido online + API key set"
                      : caidoAlive
                      ? "Caido running but CAIDO_API_KEY not set"
                      : "Caido not reachable"
                  }
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      caidoAlive === null ? "bg-zinc-600" :
                      caidoAlive && caidoHasKey ? "bg-green-400 animate-pulse" :
                      caidoAlive ? "bg-yellow-400" : "bg-red-500"
                    )}
                  />
                  Caido
                </span>
              </div>

              {/* Target input */}
              <input
                type="text"
                placeholder="target domain (auto-fills from scope)"
                value={quickTarget}
                onChange={(e) => setQuickTarget(e.target.value)}
                className="w-full bg-black border border-amber-400/20 rounded px-2 py-1 text-amber-300 text-xs focus:outline-none focus:border-amber-400/50 placeholder:text-amber-400/20 mb-2"
              />

              {/* Preset buttons grid */}
              <div className="grid grid-cols-3 gap-1">
                {PRESETS.map(({ label, icon: Icon, color, goal: g }) => (
                  <button
                    key={label}
                    disabled={isRunning}
                    onClick={() => {
                      const t = quickTarget || "TARGET";
                      setGoal(g(t));
                    }}
                    className={cn(
                      "flex flex-col items-center gap-0.5 py-1.5 rounded border text-[9px] uppercase tracking-wider transition-colors disabled:opacity-30",
                      color
                    )}
                    title={g(quickTarget || "TARGET")}
                  >
                    <Icon size={12} />
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right: live console */}
          <div className="flex-1 flex flex-col border border-amber-400/20 rounded bg-zinc-950 overflow-hidden">
            {/* Console header */}
            <div className="flex items-center gap-2 px-3 py-2 border-b border-amber-400/15">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              <span className="text-amber-400/60 text-[10px] uppercase tracking-widest">
                Live Output
              </span>
              <span className="ml-auto text-[10px] text-amber-400/30">{log.length} lines</span>
            </div>

            {/* Log pane */}
            <div className="flex-1 overflow-y-auto p-3 text-[11px] space-y-0.5">
              {log.length === 0 && (
                <p className="text-amber-400/20 text-center pt-16">
                  ▌ Waiting for connection…
                </p>
              )}
              {log.map((line) => (
                <div key={line.id} className="flex gap-2 leading-relaxed">
                  <span className="text-amber-400/25 shrink-0 tabular-nums">{line.ts}</span>
                  <span className={cn(
                    "break-all",
                    line.type === "thought"  ? "text-amber-300/70 italic" :
                    line.type === "recon"    ? "text-cyan-400" :
                    line.type === "exploit"  ? "text-orange-400" :
                    line.type === "dryrun"   ? "text-amber-400/60" :
                    line.type === "done"     ? "text-green-400/80" :
                    line.type === "err"      ? "text-red-400" :
                    line.type === "block"    ? "text-red-500" :
                    line.type === "warn"     ? "text-yellow-400" :
                    line.type === "output"
                      ? line.stream === "stderr"
                        ? "text-red-300/70"
                        : "text-amber-100/80"
                      : "text-amber-400/50"
                  )}>
                    {line.text}
                  </span>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            {pending && (
              <div className="border-t border-amber-400/30 bg-zinc-900 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle size={14} className="text-amber-400" />
                  <span className="text-amber-400 text-xs font-bold uppercase tracking-wider">
                    Awaiting Approval — {pending.tier.toUpperCase()}
                    {pending.needs_root && " [ROOT]"}
                    {pending.dry_run && " [DRY-RUN]"}
                  </span>
                </div>
                <div className="bg-black rounded border border-amber-400/20 px-3 py-2 mb-2">
                  <code className="text-amber-300 text-xs">{pending.rendered}</code>
                </div>
                <p className="text-amber-400/50 text-[10px] mb-1">Targets: {pending.targets.join(", ") || "none"}</p>
                <p className="text-amber-400/50 text-[10px] mb-3">Rationale: {pending.rationale}</p>
                <div className="flex gap-2">
                  <button
                    onClick={approve}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded border border-green-500/40 text-green-400 bg-green-500/5 hover:bg-green-500/15 text-xs transition-colors"
                  >
                    <CheckCircle2 size={12} /> APPROVE
                  </button>
                  <button
                    onClick={reject}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded border border-red-700/40 text-red-400 hover:bg-red-500/10 text-xs transition-colors"
                  >
                    <Square size={12} /> REJECT
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Live Browser View — Manus-style screen-share of the agent's headless browser */}
          <div className="w-[480px] shrink-0 flex flex-col border border-amber-400/20 rounded bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-amber-400/15">
              <Globe size={12} className="text-amber-400" />
              <span className="text-amber-400/60 text-[10px] uppercase tracking-widest">
                Live Browser
              </span>
              {browserFrame && (
                <span
                  className="ml-auto text-[10px] text-amber-300/60 truncate max-w-[340px]"
                  title={browserFrame.url}
                >
                  {browserFrame.url || "(blank)"}
                </span>
              )}
            </div>

            <div className="flex-1 overflow-auto p-2 bg-black">
              {browserFrame && browserFrame.png_b64 ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={`data:image/png;base64,${browserFrame.png_b64}`}
                  alt="agent browser"
                  className="w-full border border-amber-400/15 rounded"
                />
              ) : (
                <div className="h-full flex items-center justify-center text-amber-400/20 text-xs text-center px-6">
                  ▌ No browser activity yet.<br />
                  <span className="text-amber-400/15 text-[10px] mt-2 block">
                    Frames stream automatically when the planner uses the
                    <span className="text-amber-400/40"> browser </span>tool.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
