"use client";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi, type AppSetting } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Key,
  Cpu,
  Wrench,
  Radio,
  Shield,
  Eye,
  EyeOff,
  Save,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Zap,
} from "lucide-react";
import { Nav } from "@/components/nav";
import { toast } from "sonner";

const SECTION_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  ai:     { label: "AI Models & LLM",     icon: Cpu,    color: "text-blue-400" },
  tools:  { label: "Proxy & Tools",       icon: Wrench, color: "text-orange-400" },
  oast:   { label: "OAST / Interactsh",   icon: Radio,  color: "text-green-400" },
  crypto: { label: "Encryption",          icon: Shield, color: "text-purple-400" },
};

const OR_FREE_MODELS = [
  "deepseek/deepseek-r1-distill-qwen-32b:free",
  "deepseek/deepseek-r1-distill-llama-70b:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "mistralai/mistral-small-3.1-24b-instruct:free",
  "google/gemma-3-27b-it:free",
  "google/gemini-2.0-flash-exp:free",
  "qwen/qwen2.5-72b-instruct:free",
  "microsoft/phi-4:free",
];

function SettingField({
  setting,
  value,
  onChange,
}: {
  setting: AppSetting;
  value: string;
  onChange: (val: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const isModelSelect = setting.key.startsWith("OPENROUTER_MODEL_");

  if (isModelSelect) {
    return (
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-zinc-900 border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-blue-500/60 appearance-none pr-8"
        >
          {OR_FREE_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
          {value && !OR_FREE_MODELS.includes(value) && (
            <option value={value}>{value}</option>
          )}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
      </div>
    );
  }

  if (setting.sensitive) {
    return (
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <input
            type={revealed ? "text" : "password"}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={
              setting.raw_set
                ? "Enter new value to change (leave blank to keep current)"
                : "Not configured"
            }
            className={cn(
              "w-full bg-zinc-900 border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none pr-10 font-mono",
              setting.raw_set
                ? "border-green-500/30 focus:border-green-500/60"
                : "border-border focus:border-blue-500/60"
            )}
          />
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {revealed ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
        {setting.raw_set && (
          <div className="flex items-center gap-1 text-green-400 text-xs shrink-0">
            <CheckCircle2 size={12} />
            Set
          </div>
        )}
      </div>
    );
  }

  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={setting.value || "Not set"}
      className="w-full bg-zinc-900 border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-blue-500/60"
    />
  );
}

function SectionCard({
  section,
  sectionSettings,
  localValues,
  onChange,
}: {
  section: string;
  sectionSettings: AppSetting[];
  localValues: Record<string, string>;
  onChange: (key: string, val: string) => void;
}) {
  const meta = SECTION_META[section] ?? { label: section, icon: Key, color: "text-muted-foreground" };
  const Icon = meta.icon;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-border bg-zinc-900/40">
        <Icon size={14} className={meta.color} />
        <span className="text-sm font-semibold">{meta.label}</span>
      </div>
      <div className="divide-y divide-border/40">
        {sectionSettings.map((s) => (
          <div key={s.key} className="px-4 py-3.5">
            <div className="flex items-start justify-between gap-4 mb-2">
              <div>
                <p className="text-xs font-medium text-foreground">{s.label}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{s.desc}</p>
              </div>
              <code className="text-[10px] text-muted-foreground/50 font-mono shrink-0 mt-0.5 bg-zinc-800/60 px-1.5 py-0.5 rounded">
                {s.key}
              </code>
            </div>
            <SettingField
              setting={s}
              value={localValues[s.key] ?? ""}
              onChange={(val) => onChange(s.key, val)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function OpenRouterBanner({ allSettings }: { allSettings: AppSetting[] }) {
  const orKey = allSettings.find((s) => s.key === "OPENROUTER_API_KEY");
  const anthropicKey = allSettings.find((s) => s.key === "ANTHROPIC_API_KEY");
  if (!orKey) return null;

  const hasOr = orKey.raw_set;
  const hasAnthro = anthropicKey?.raw_set;

  return (
    <div className={cn(
      "flex items-start gap-3 rounded-lg border px-4 py-3 text-sm",
      hasOr ? "border-green-500/25 bg-green-500/5" : "border-yellow-500/25 bg-yellow-500/5"
    )}>
      <Zap size={14} className={cn("mt-0.5 shrink-0", hasOr ? "text-green-400" : "text-yellow-400")} />
      <div className="space-y-1">
        {hasOr ? (
          <p className="text-green-400 font-medium text-xs">
            OpenRouter fallback active — free models kick in when Anthropic budget runs out
          </p>
        ) : (
          <p className="text-yellow-400 font-medium text-xs">
            OpenRouter not configured — add a key to get free-model fallback
          </p>
        )}
        {!hasAnthro && (
          <p className="text-orange-400 text-xs">
            No Anthropic key — all LLM calls will use OpenRouter free models only
          </p>
        )}
        {!hasOr && (
          <p className="text-muted-foreground text-xs">
            Free signup at openrouter.ai · supports 100+ models including free DeepSeek, Llama, Gemma tiers
          </p>
        )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: allSettings = [], isLoading } = useQuery<AppSetting[]>({
    queryKey: ["app-settings"],
    queryFn: settingsApi.list,
  });

  const [localValues, setLocalValues] = useState<Record<string, string>>({});
  const [initialized, setInitialized] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (allSettings.length > 0 && !initialized) {
      const init: Record<string, string> = {};
      for (const s of allSettings) {
        // Sensitive fields: show empty so user must type to change
        init[s.key] = s.sensitive ? "" : s.value;
      }
      setLocalValues(init);
      setInitialized(true);
    }
  }, [allSettings, initialized]);

  const saveMut = useMutation({
    mutationFn: (updates: Record<string, string>) => settingsApi.save(updates),
    onSuccess: (data) => {
      if (data.restart_required.length > 0) {
        toast.warning(
          `Saved. Restart backend for changes to: ${data.restart_required.join(", ")}`,
          { duration: 7000 }
        );
      } else {
        toast.success(`${data.saved.length} setting(s) saved`);
      }
      setDirty(false);
      setInitialized(false);
      qc.invalidateQueries({ queryKey: ["app-settings"] });
    },
    onError: () => toast.error("Failed to save settings"),
  });

  const handleChange = (key: string, val: string) => {
    setLocalValues((prev) => ({ ...prev, [key]: val }));
    setDirty(true);
  };

  const handleSave = () => {
    const updates: Record<string, string> = {};
    for (const [key, val] of Object.entries(localValues)) {
      if (val !== "") updates[key] = val;
    }
    saveMut.mutate(updates);
  };

  const handleReset = () => {
    setDirty(false);
    setInitialized(false);
  };

  const sections = ["ai", "tools", "oast", "crypto"];

  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="ml-56 flex-1 p-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-zinc-800 border border-border">
          <Key size={18} className="text-muted-foreground" />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Settings</h1>
          <p className="text-xs text-muted-foreground">API keys, LLM models, tool integrations</p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <RotateCcw size={11} /> Reset
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!dirty || saveMut.isPending}
            className={cn(
              "flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-colors",
              dirty
                ? "bg-blue-600 text-white hover:bg-blue-500"
                : "bg-zinc-800 text-muted-foreground cursor-not-allowed"
            )}
          >
            <Save size={11} />
            {saveMut.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground py-16 text-center animate-pulse">
          Loading settings…
        </div>
      ) : (
        <div className="space-y-4">
          <OpenRouterBanner allSettings={allSettings} />

          {sections.map((section) => {
            const sectionSettings = allSettings.filter((s) => s.section === section);
            if (sectionSettings.length === 0) return null;
            return (
              <SectionCard
                key={section}
                section={section}
                sectionSettings={sectionSettings}
                localValues={localValues}
                onChange={handleChange}
              />
            );
          })}

          <div className="flex items-start gap-2 text-[11px] text-muted-foreground/70 px-1 pt-1">
            <AlertTriangle size={11} className="mt-0.5 shrink-0 text-yellow-500/50" />
            <span>
              Changes are written to the database and <code className="bg-zinc-800 px-1 rounded">.env</code>.
              API key values are never returned in plaintext — enter a new value to update.
              Some changes require a backend restart to take full effect.
            </span>
          </div>
        </div>
      )}
      </main>
    </div>
  );
}
