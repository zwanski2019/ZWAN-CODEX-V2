"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Nav } from "@/components/nav";
import { cn } from "@/lib/utils";
import {
  Target, Code2, Key, Globe, Zap, Shield, Radio, Database, ScanLine,
  Play, Square, CheckCircle2, AlertTriangle, Wifi, WifiOff,
  ChevronDown, ChevronUp, Settings2,
  Filter, FolderSearch, Network, Clock, Monitor,
} from "lucide-react";

const AGENT_WS   = process.env.NEXT_PUBLIC_AGENT_WS   ?? "ws://127.0.0.1:8788/ws";
const AGENT_HTTP = process.env.NEXT_PUBLIC_AGENT_HTTP  ?? "http://127.0.0.1:8788";
const TOKEN_KEY  = "zwan_agent_token";

// ── Hunt types ────────────────────────────────────────────────────────────────

const HUNTS = [
  {
    id: "recon",
    label: "Full Recon",
    desc: "Find all subdomains, open ports, and technologies",
    icon: Target,
    color: "border-cyan-500/40 bg-cyan-500/5 text-cyan-400",
    selColor: "border-cyan-400 bg-cyan-400/15 text-cyan-300",
    goal: (t: string) =>
      `Enumerate all subdomains of ${t} with subfinder and amass. Probe live hosts with httpx. Run nuclei recon templates. Screenshot interesting endpoints.`,
  },
  {
    id: "js",
    label: "JS Mining",
    desc: "Find API keys, secrets and hidden endpoints in JS files",
    icon: Code2,
    color: "border-yellow-500/40 bg-yellow-500/5 text-yellow-400",
    selColor: "border-yellow-400 bg-yellow-400/15 text-yellow-300",
    goal: (t: string) =>
      `Crawl ${t} with katana depth 3, collect all URLs with gau. Download every JavaScript file and mine for hardcoded API keys, tokens, secrets, Sentry DSNs, and hidden API endpoints.`,
  },
  {
    id: "oauth",
    label: "OAuth Hunt",
    desc: "Test OAuth flows for bypass and token theft",
    icon: Key,
    color: "border-purple-500/40 bg-purple-500/5 text-purple-400",
    selColor: "border-purple-400 bg-purple-400/15 text-purple-300",
    goal: (t: string) =>
      `Use browser to navigate ${t} and find all OAuth 2.0 and OIDC login flows. Use katana to crawl OAuth redirect chains. Test for PKCE stripping, redirect_uri bypass with double-encoded fragments (%2523), state fixation, and dynamic client registration abuse.`,
  },
  {
    id: "ssrf",
    label: "SSRF Probe",
    desc: "Find server-side request forgery in URL parameters",
    icon: Globe,
    color: "border-pink-500/40 bg-pink-500/5 text-pink-400",
    selColor: "border-pink-400 bg-pink-400/15 text-pink-300",
    goal: (t: string) =>
      `Use katana depth 2 and gau to crawl ${t} and extract all URL parameters. Use curl to test each parameter that accepts a URL value for SSRF by pointing it at an out-of-band server. Target PDF generators, image processors, and webhook relay endpoints.`,
  },
  {
    id: "race",
    label: "Race Conditions",
    desc: "Find race conditions on payment and coupon endpoints",
    icon: Zap,
    color: "border-orange-500/40 bg-orange-500/5 text-orange-400",
    selColor: "border-orange-400 bg-orange-400/15 text-orange-300",
    goal: (t: string) =>
      `Use katana and gau to find payment, transfer, withdrawal, subscription, and coupon endpoints on ${t}. Send concurrent curl_post requests to test for race conditions on operations that should execute only once (double-spend, coupon reuse, duplicate transfer).`,
  },
  {
    id: "nuclei",
    label: "Vuln Scan",
    desc: "Run nuclei high/critical templates on the target",
    icon: Shield,
    color: "border-red-500/40 bg-red-500/5 text-red-400",
    selColor: "border-red-400 bg-red-400/15 text-red-300",
    goal: (t: string) =>
      `Run nuclei against ${t} with high and critical severity templates only. Focus on CVEs from the last 12 months, auth bypass, and technology-specific exploits.`,
  },
  {
    id: "desync",
    label: "HTTP Desync",
    desc: "Test for HTTP request smuggling (CL.TE, H2.CL, CL.0)",
    icon: Radio,
    color: "border-rose-500/40 bg-rose-500/5 text-rose-400",
    selColor: "border-rose-400 bg-rose-400/15 text-rose-300",
    goal: (t: string) =>
      `Use curl with crafted Content-Length and Transfer-Encoding headers to test ${t} for HTTP request smuggling: CL.0, H2.CL, 0.CL, and client-side desync. Use differential response timing analysis to find vulnerable front-end/back-end proxy configurations.`,
  },
  {
    id: "caido",
    label: "Caido Review",
    desc: "Analyse traffic captured by Caido proxy for vulns",
    icon: Database,
    color: "border-amber-500/40 bg-amber-500/5 text-amber-400",
    selColor: "border-amber-400 bg-amber-400/15 text-amber-300",
    goal: (t: string) =>
      `Pull HTTP history from Caido for ${t} using caido_history. Identify the 10 most interesting endpoints by auth patterns and anomalies. Use caido_create_finding for any confirmed vulnerabilities.`,
  },
  {
    id: "scope",
    label: "Scope Map",
    desc: "Build a full attack surface map before any exploitation",
    icon: ScanLine,
    color: "border-green-500/40 bg-green-500/5 text-green-400",
    selColor: "border-green-400 bg-green-400/15 text-green-300",
    goal: (t: string) =>
      `Full scope scan of ${t}: port scan with naabu, TLS inspection with tlsx, technology fingerprint with whatweb, DNS records with dnsx. Build a complete attack surface map.`,
  },
  {
    id: "sqli",
    label: "SQL Injection",
    desc: "Find SQL injection in forms and URL parameters",
    icon: Filter,
    color: "border-violet-500/40 bg-violet-500/5 text-violet-400",
    selColor: "border-violet-400 bg-violet-400/15 text-violet-300",
    goal: (t: string) =>
      `Use katana depth 3 and gau to crawl ${t} and collect all form parameters and URL parameters. Run sqlmap against each injectable parameter. Prioritize login forms, search boxes, numeric ID params, and order/filter endpoints. Report all confirmed injections with database name and proof.`,
  },
  {
    id: "fuzz",
    label: "Dir Fuzzing",
    desc: "Find hidden files, admin panels and backup files",
    icon: FolderSearch,
    color: "border-teal-500/40 bg-teal-500/5 text-teal-400",
    selColor: "border-teal-400 bg-teal-400/15 text-teal-300",
    goal: (t: string) =>
      `Use ffuf with a large common wordlist to fuzz directories and files on ${t}. Use gobuster_dir for recursive directory brute-force. Use gobuster_dns to enumerate DNS subdomains. Focus on backup files (.bak, .zip, .sql), admin panels (/admin, /dashboard, /manage), .git exposure, and config files.`,
  },
  {
    id: "portscan",
    label: "Port Scan",
    desc: "Discover open ports and identify running services",
    icon: Network,
    color: "border-blue-500/40 bg-blue-500/5 text-blue-400",
    selColor: "border-blue-400 bg-blue-400/15 text-blue-300",
    goal: (t: string) =>
      `Run naabu for fast port discovery across all 65535 ports on ${t}. Follow with nmap -sV for service version detection and OS fingerprinting on every open port. Use masscan for high-speed full-port coverage on the IP range. Report unusual services, exposed databases, and version-specific CVEs.`,
  },
  {
    id: "historical",
    label: "Historical Recon",
    desc: "Mine Wayback Machine for old endpoints and leaks",
    icon: Clock,
    color: "border-indigo-500/40 bg-indigo-500/5 text-indigo-400",
    selColor: "border-indigo-400 bg-indigo-400/15 text-indigo-300",
    goal: (t: string) =>
      `Use waybackurls to pull all archived URLs for ${t} from the Wayback Machine. Use gau for additional URL discovery from multiple sources. Check whois for domain registration history. Use dig for full DNS record enumeration. Look for old API endpoints, leaked credentials in URLs, deprecated admin panels, and forgotten subdomains.`,
  },
  {
    id: "browse",
    label: "Browser Crawl",
    desc: "Navigate the site visually and map all functionality",
    icon: Monitor,
    color: "border-sky-500/40 bg-sky-500/5 text-sky-400",
    selColor: "border-sky-400 bg-sky-400/15 text-sky-300",
    goal: (t: string) =>
      `Use browser to navigate ${t}, interact with the live site, and screenshot all key pages. Use katana for deep JavaScript-aware crawling. Map every user-facing feature, form submission, file upload, and API call. Look for unauthenticated functionality, hidden parameters, and client-side logic exposing sensitive operations.`,
  },
] as const;

type HuntId = (typeof HUNTS)[number]["id"];

// ── Log helpers ───────────────────────────────────────────────────────────────

type LogLine = { id: number; ts: string; kind: string; text: string };
let _lid = 0;

function linePrefix(kind: string) {
  switch (kind) {
    case "think":   return "🤔";
    case "recon":   return "🔍";
    case "exploit": return "⚡";
    case "done":    return "✓";
    case "fail":    return "✗";
    case "block":   return "🚫";
    case "warn":    return "⚠️";
    case "sys":     return "·";
    default:        return "·";
  }
}

function lineColor(kind: string) {
  switch (kind) {
    case "think":   return "text-amber-300/70 italic";
    case "recon":   return "text-cyan-400";
    case "exploit": return "text-orange-400";
    case "done":    return "text-green-400";
    case "fail":    return "text-red-400";
    case "block":   return "text-red-500";
    case "warn":    return "text-yellow-400";
    default:        return "text-zinc-400";
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

type ConnState = "off" | "connecting" | "ready" | "running";

interface PendingCmd {
  cmd_id: string; tool: string; rendered: string;
  tier: string; targets: string[]; needs_root: boolean;
  decision: string; rationale: string; dry_run: boolean;
}

export default function ConsolePage() {
  // Connection
  const [conn, setConn]           = useState<ConnState>("off");
  const [token, setToken]         = useState("");
  const [showTokenInput, setShowTokenInput] = useState(false);
  const wsRef                     = useRef<WebSocket | null>(null);

  // Hunt
  const [target, setTarget]       = useState("");
  const [huntId, setHuntId]       = useState<HuntId | null>(null);
  const [dryRun, setDryRun]       = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [scopeYaml, setScopeYaml] = useState("");

  // Session
  const [log, setLog]             = useState<LogLine[]>([]);
  const [pending, setPending]     = useState<PendingCmd | null>(null);
  const [itersLeft, setItersLeft] = useState(25);
  const [budgetSec, setBudgetSec] = useState(1800);
  const [browserFrame, setBrowserFrame] = useState<{ url: string; png_b64: string } | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);

  // Caido
  const [caidoAlive, setCaidoAlive] = useState<boolean | null>(null);
  const [caidoHasKey, setCaidoHasKey] = useState(false);
  const [caidoLogin, setCaidoLogin] = useState<{
    userCode: string; verificationUrl: string;
  } | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Auto-scroll ──────────────────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log.length]);

  // ── Restore token from localStorage ──────────────────────────────────────

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) setToken(stored);
  }, []);

  // ── Caido status poll ─────────────────────────────────────────────────────

  useEffect(() => {
    const check = () =>
      fetch(`${AGENT_HTTP}/api/caido/status`)
        .then((r) => r.json())
        .then((d) => {
          setCaidoAlive(d.alive);
          setCaidoHasKey(d.has_key);
          if (d.has_key) setCaidoLogin(null);
        })
        .catch(() => { setCaidoAlive(false); setCaidoHasKey(false); });
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, []);

  // ── Auto-scope from target ────────────────────────────────────────────────

  function targetToScope(t: string): string {
    const domain = t.replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "");
    if (!domain) return "";
    return `program: ${domain}\nin_scope:\n  domains:\n    - "*.${domain}"\n    - "${domain}"`;
  }

  // ── Log helper ────────────────────────────────────────────────────────────

  const addLog = useCallback((kind: string, text: string) => {
    setLog((prev) => [
      ...prev.slice(-499),
      { id: _lid++, ts: new Date().toLocaleTimeString("en-GB", { hour12: false }), kind, text },
    ]);
  }, []);

  // ── Message handler ───────────────────────────────────────────────────────

  const handleMsg = useCallback((msg: Record<string, unknown>) => {
    const t = msg.type as string;
    if (t === "auth_ok")          { setConn("ready"); addLog("sys", "Agent connected and ready."); return; }
    if (t === "thought")          { addLog("think", String(msg.text ?? "")); return; }
    if (t === "output_chunk")     { addLog("sys", String(msg.data ?? "")); return; }
    if (t === "blocked")          { addLog("block", `Blocked: ${msg.reason}`); return; }
    if (t === "error")            { addLog("fail", String(msg.message ?? "")); return; }
    if (t === "sudo_prompt_required") { addLog("warn", "Agent needs sudo — type your password in the terminal where the agent is running."); return; }
    if (t === "session_done")     { setConn("ready"); addLog("done", String(msg.summary ?? "Session complete.")); setPending(null); return; }
    if (t === "budget")           { setItersLeft((msg.iters_left as number) ?? 25); setBudgetSec((msg.budget_left_sec as number) ?? 1800); return; }
    if (t === "browser_frame")    { setBrowserFrame({ url: (msg.url as string) ?? "", png_b64: (msg.png_b64 as string) ?? "" }); setShowBrowser(true); return; }
    if (t === "pong")             return;

    if (t === "command_proposed") {
      const c = msg as unknown as PendingCmd & { type: string };
      const label = c.tier === "exploit" ? "exploit" : "recon";
      addLog(label, c.rendered);
      if (c.decision === "needs_approval") setPending(c);
      return;
    }
    if (t === "awaiting_approval") { setConn("running"); return; }
    if (t === "command_done") {
      const ec = msg.exit_code;
      addLog(ec === 0 || ec === null ? "done" : "fail",
        `Done (${msg.duration_ms}ms${ec !== null ? `, exit ${ec}` : ", dry-run"})`);
      setPending(null);
      return;
    }
  }, [addLog]);

  // ── WS connect ────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!token) return;
    localStorage.setItem(TOKEN_KEY, token);
    setConn("connecting");
    addLog("sys", "Connecting to agent…");
    const ws = new WebSocket(AGENT_WS);
    wsRef.current = ws;
    ws.onopen    = () => ws.send(JSON.stringify({ type: "auth", token }));
    ws.onmessage = (e) => { try { handleMsg(JSON.parse(e.data)); } catch {} };
    ws.onerror   = () => { addLog("fail", "Connection error."); setConn("off"); };
    ws.onclose   = (ev) => {
      addLog("sys", `Disconnected (${ev.code}).`);
      setConn("off"); wsRef.current = null; setPending(null);
    };
  }, [token, addLog, handleMsg]);

  const disconnect = useCallback(() => { wsRef.current?.close(); }, []);

  const sendMsg = useCallback((m: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify(m));
  }, []);

  // ── Auto-connect on mount if token stored ─────────────────────────────────

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) { setToken(stored); }
    // slight delay so token state is set
  }, []);

  // ── Hunt ──────────────────────────────────────────────────────────────────

  const startHunt = useCallback(() => {
    if (!huntId || !target) return;
    const hunt = HUNTS.find((h) => h.id === huntId)!;
    const goal  = hunt.goal(target);
    const scope = scopeYaml || targetToScope(target);
    setLog([]);
    setBrowserFrame(null);
    setConn("running");
    sendMsg({ type: "start_session", goal, mode: "auto", scope, dry_run: dryRun });
    addLog("sys", `Starting ${hunt.label} on ${target}${dryRun ? " (dry run)" : ""}…`);
  }, [huntId, target, scopeYaml, dryRun, sendMsg, addLog]);

  const abort = useCallback(() => {
    sendMsg({ type: "abort" });
    setPending(null);
    setConn("ready");
    addLog("sys", "Aborted.");
  }, [sendMsg, addLog]);

  const approve = useCallback(() => {
    if (!pending) return;
    sendMsg({ type: "approve", cmd_id: pending.cmd_id });
    addLog("done", `Approved: ${pending.rendered}`);
    setPending(null);
  }, [pending, sendMsg, addLog]);

  const reject = useCallback(() => {
    if (!pending) return;
    sendMsg({ type: "reject", cmd_id: pending.cmd_id });
    addLog("sys", `Rejected: ${pending.rendered}`);
    setPending(null);
  }, [pending, sendMsg, addLog]);

  // ── Caido login ───────────────────────────────────────────────────────────

  const startCaidoLogin = useCallback(async () => {
    const r = await fetch(`${AGENT_HTTP}/api/caido/login`, { method: "POST" });
    const d = await r.json();
    if (d.error) { addLog("fail", `Caido: ${d.error}`); return; }
    setCaidoLogin({ userCode: d.userCode, verificationUrl: d.verificationUrl });
    addLog("sys", `Caido: open ${d.verificationUrl}`);
  }, [addLog]);

  // ── Derived state ─────────────────────────────────────────────────────────

  const isReady   = conn === "ready";
  const isRunning = conn === "running";
  const isOff     = conn === "off";
  const canStart  = isReady && !!target && !!huntId && !isRunning;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex min-h-screen bg-zinc-950">
      <Nav />
      <main className="ml-56 flex-1 flex flex-col p-6 gap-5">

        {/* ── Header ── */}
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-amber-400 tracking-wide">Hunt Console</h1>
          <span className={cn(
            "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium",
            isRunning ? "border-amber-400/50 bg-amber-400/10 text-amber-400" :
            isReady   ? "border-green-500/50 bg-green-500/10 text-green-400" :
            conn === "connecting" ? "border-yellow-500/40 text-yellow-400" :
            "border-zinc-700 text-zinc-500"
          )}>
            <span className={cn("w-2 h-2 rounded-full",
              isRunning ? "bg-amber-400 animate-pulse" :
              isReady   ? "bg-green-400" :
              conn === "connecting" ? "bg-yellow-500 animate-pulse" : "bg-zinc-600"
            )} />
            {isRunning ? "Hunting…" : isReady ? "Ready" : conn === "connecting" ? "Connecting…" : "Agent offline"}
          </span>

          {/* Token / connection controls */}
          {isOff && (
            <div className="ml-auto flex items-center gap-2">
              {showTokenInput ? (
                <>
                  <input
                    type="password"
                    placeholder="Paste agent token…"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && connect()}
                    className="bg-black border border-amber-400/30 rounded px-3 py-1.5 text-amber-300 text-sm w-64 focus:outline-none focus:border-amber-400"
                  />
                  <button onClick={connect} disabled={!token}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-amber-400/40 text-amber-400 hover:bg-amber-400/10 text-sm disabled:opacity-30 transition-colors">
                    <Wifi size={13} /> Connect
                  </button>
                </>
              ) : (
                <button onClick={() => setShowTokenInput(true)}
                  className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:border-amber-400/40 hover:text-amber-400 text-xs transition-colors">
                  <Wifi size={12} /> Connect agent
                </button>
              )}
            </div>
          )}
          {!isOff && (
            <button onClick={disconnect}
              className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded border border-zinc-700 text-zinc-500 hover:text-red-400 hover:border-red-700/40 text-xs transition-colors">
              <WifiOff size={11} /> Disconnect
            </button>
          )}
        </div>

        {/* ── Token hint if first time ── */}
        {isOff && !token && (
          <div className="bg-amber-400/5 border border-amber-400/20 rounded-lg p-4 text-sm text-amber-300/80">
            <p className="font-medium mb-1">Start the agent first</p>
            <p className="text-xs text-amber-400/50">In a terminal: <code className="bg-black/40 px-1.5 py-0.5 rounded text-amber-300">cd ZWAN-CODEX-V2 &amp;&amp; agent/.venv/bin/python -m agent.main</code></p>
            <p className="text-xs text-amber-400/50 mt-1">It prints a token — paste it above and click Connect.</p>
          </div>
        )}

        <div className="flex gap-5 flex-1 min-h-0">

          {/* ── Left: launcher + output ── */}
          <div className="flex-1 flex flex-col gap-4 min-w-0">

            {/* Target input */}
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-widest mb-1.5 block">
                Target domain
              </label>
              <input
                type="text"
                placeholder="example.com"
                value={target}
                onChange={(e) => setTarget(e.target.value.trim())}
                disabled={isRunning}
                className="w-full bg-black border border-zinc-800 rounded-lg px-4 py-3 text-amber-300 text-base focus:outline-none focus:border-amber-400/60 placeholder:text-zinc-700 transition-colors"
              />
            </div>

            {/* Hunt type cards */}
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-widest mb-2 block">
                What do you want to hunt?
              </label>
              <div className="grid grid-cols-3 gap-2">
                {HUNTS.map((h) => {
                  const Icon = h.icon;
                  const sel  = huntId === h.id;
                  return (
                    <button
                      key={h.id}
                      disabled={isRunning}
                      onClick={() => setHuntId(h.id)}
                      className={cn(
                        "flex flex-col items-start gap-1 p-3 rounded-lg border text-left transition-all disabled:opacity-40",
                        sel ? h.selColor : h.color + " hover:brightness-125"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <Icon size={14} />
                        <span className="font-semibold text-xs">{h.label}</span>
                      </div>
                      <span className="text-[10px] opacity-70 leading-snug">{h.desc}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Advanced toggle */}
            <div>
              <button
                onClick={() => setShowAdvanced((v) => !v)}
                className="flex items-center gap-1.5 text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                <Settings2 size={11} />
                Advanced options
                {showAdvanced ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              </button>
              {showAdvanced && (
                <div className="mt-2 flex flex-col gap-2 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
                  <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none">
                    <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)}
                      className="accent-amber-400" />
                    Dry run — plan only, don't actually execute commands
                  </label>
                  <div>
                    <p className="text-[10px] text-zinc-600 mb-1 uppercase tracking-widest">Scope YAML (auto-generated from target if empty)</p>
                    <textarea
                      value={scopeYaml}
                      onChange={(e) => setScopeYaml(e.target.value)}
                      rows={5}
                      disabled={isRunning}
                      placeholder={targetToScope(target || "example.com")}
                      className="w-full bg-black border border-zinc-800 rounded px-3 py-2 text-zinc-400 text-[11px] font-mono focus:outline-none focus:border-amber-400/40 placeholder:text-zinc-700 resize-none"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Start / Abort */}
            {!isRunning ? (
              <button
                onClick={startHunt}
                disabled={!canStart}
                className="flex items-center justify-center gap-2 py-3 rounded-lg border border-amber-500/50 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 font-bold text-sm transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <Play size={15} fill="currentColor" />
                {!isReady ? "Connect agent first" : !target ? "Enter a target" : !huntId ? "Choose a hunt type" : "Start Hunt"}
              </button>
            ) : (
              <button
                onClick={abort}
                className="flex items-center justify-center gap-2 py-3 rounded-lg border border-red-600/40 bg-red-500/5 text-red-400 hover:bg-red-500/15 font-bold text-sm transition-colors"
              >
                <Square size={14} fill="currentColor" /> Stop Hunt
              </button>
            )}

            {/* Budget bar — only when running */}
            {isRunning && (
              <div className="flex gap-3">
                <div className="flex-1">
                  <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                    <span>Steps</span><span>{itersLeft} left</span>
                  </div>
                  <div className="h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400/60 rounded-full transition-all"
                      style={{ width: `${(itersLeft / 25) * 100}%` }} />
                  </div>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                    <span>Time</span><span>{Math.floor(budgetSec / 60)}m left</span>
                  </div>
                  <div className="h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400/30 rounded-full transition-all"
                      style={{ width: `${(budgetSec / 1800) * 100}%` }} />
                  </div>
                </div>
              </div>
            )}

            {/* Output log */}
            <div className="flex-1 min-h-48 bg-black border border-zinc-800 rounded-lg overflow-hidden flex flex-col">
              <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2">
                <span className="text-[10px] text-zinc-600 uppercase tracking-widest">Output</span>
                {log.length > 0 && (
                  <button onClick={() => setLog([])}
                    className="ml-auto text-[9px] text-zinc-700 hover:text-zinc-500 transition-colors">
                    clear
                  </button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto p-3 text-[11px] font-mono space-y-0.5">
                {log.length === 0 && (
                  <p className="text-zinc-700 text-center pt-8">
                    Output will appear here when the hunt starts.
                  </p>
                )}
                {log.map((line) => (
                  <div key={line.id} className="flex gap-2 leading-relaxed">
                    <span className="text-zinc-700 shrink-0 tabular-nums w-16">{line.ts}</span>
                    <span className="text-zinc-600 shrink-0 w-4">{linePrefix(line.kind)}</span>
                    <span className={cn("break-all whitespace-pre-wrap", lineColor(line.kind))}>
                      {line.text}
                    </span>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
            </div>
          </div>

          {/* ── Right: Caido + Browser ── */}
          <div className="w-72 shrink-0 flex flex-col gap-3">

            {/* Caido panel */}
            <div className="border border-zinc-800 rounded-lg p-3 bg-black">
              <div className="flex items-center gap-2 mb-3">
                <span className={cn("w-2 h-2 rounded-full",
                  caidoAlive && caidoHasKey ? "bg-green-400 animate-pulse" :
                  caidoAlive ? "bg-yellow-400" : "bg-zinc-700"
                )} />
                <span className="text-xs font-medium text-zinc-300">Caido Proxy</span>
                <span className={cn("ml-auto text-[10px]",
                  caidoAlive && caidoHasKey ? "text-green-400" :
                  caidoAlive ? "text-yellow-400" : "text-zinc-600"
                )}>
                  {caidoAlive && caidoHasKey ? "Connected" : caidoAlive ? "Not logged in" : "Offline"}
                </span>
              </div>

              {caidoAlive && !caidoHasKey && !caidoLogin && (
                <button onClick={startCaidoLogin}
                  className="w-full py-2 rounded border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 text-xs font-medium transition-colors">
                  Log in to Caido →
                </button>
              )}

              {caidoLogin && (
                <div className="text-xs space-y-2">
                  <p className="text-zinc-400">Click the link below and approve:</p>
                  <a href={caidoLogin.verificationUrl} target="_blank" rel="noreferrer"
                    className="block bg-amber-400/10 border border-amber-400/30 rounded px-2 py-1.5 text-amber-300 hover:bg-amber-400/15 transition-colors text-center font-medium">
                    Approve on Caido Dashboard →
                  </a>
                  <p className="text-zinc-600 text-center">
                    Code: <span className="text-zinc-300 font-bold">{caidoLogin.userCode}</span>
                  </p>
                  <p className="text-zinc-700 text-center text-[10px]">Waiting for approval…</p>
                </div>
              )}

              {caidoAlive && caidoHasKey && (
                <p className="text-[10px] text-zinc-600">
                  All agent traffic is captured in Caido History. Use the <strong className="text-zinc-500">Caido Review</strong> hunt to analyse it.
                </p>
              )}

              {!caidoAlive && (
                <p className="text-[10px] text-zinc-600">
                  Caido is not running. Start it with: <code className="text-zinc-500">caido</code>
                </p>
              )}
            </div>

            {/* Browser view */}
            {(browserFrame || showBrowser) && (
              <div className="border border-zinc-800 rounded-lg overflow-hidden bg-black flex flex-col">
                <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2">
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest flex-1">Agent Browser</span>
                  <button onClick={() => { setShowBrowser(false); setBrowserFrame(null); }}
                    className="text-[9px] text-zinc-700 hover:text-zinc-500">hide</button>
                </div>
                {browserFrame?.png_b64 ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={`data:image/png;base64,${browserFrame.png_b64}`}
                    alt="agent browser" className="w-full" />
                ) : (
                  <p className="text-[10px] text-zinc-700 text-center p-6">
                    Browser frames appear here when the agent navigates a website.
                  </p>
                )}
                {browserFrame?.url && (
                  <p className="text-[9px] text-zinc-700 px-2 py-1 border-t border-zinc-900 truncate">
                    {browserFrame.url}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Approval overlay ── */}
        {pending && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-zinc-900 border border-amber-400/40 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle size={18} className="text-amber-400" />
                <span className="text-amber-400 font-bold uppercase tracking-wider text-sm">
                  Agent wants to run {pending.tier === "exploit" ? "an exploit" : "a recon"} command
                </span>
              </div>

              <div className="bg-black rounded-lg border border-zinc-800 px-4 py-3 mb-4">
                <code className="text-amber-300 text-sm break-all">{pending.rendered}</code>
              </div>

              <div className="text-xs text-zinc-500 mb-1">
                Why: <span className="text-zinc-400">{pending.rationale}</span>
              </div>
              {pending.targets.length > 0 && (
                <div className="text-xs text-zinc-500 mb-4">
                  Target: <span className="text-zinc-400">{pending.targets.join(", ")}</span>
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={approve}
                  className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-green-500/50 bg-green-500/10 text-green-400 hover:bg-green-500/20 font-bold text-sm transition-colors">
                  <CheckCircle2 size={16} /> Allow it
                </button>
                <button onClick={reject}
                  className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-zinc-700 text-zinc-400 hover:border-red-700/40 hover:text-red-400 font-bold text-sm transition-colors">
                  <Square size={14} /> Skip it
                </button>
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
