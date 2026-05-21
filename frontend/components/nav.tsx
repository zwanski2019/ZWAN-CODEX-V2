"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Target, Cpu, Search, Settings, Zap, Terminal, Database } from "lucide-react";
import { SystemBar } from "@/components/system-bar";

const links = [
  { href: "/dashboard",   label: "Dashboard",   icon: LayoutDashboard, crt: false },
  { href: "/engagements", label: "Engagements", icon: Target,           crt: false },
  { href: "/agents",      label: "Agents",      icon: Cpu,              crt: false },
  { href: "/loot",        label: "Loot",        icon: Search,           crt: false },
  { href: "/zeroday",     label: "Zero-Day",    icon: Zap,              crt: false },
  { href: "/console",     label: "Console",     icon: Terminal,         crt: true  },
  { href: "/audit",       label: "Audit",       icon: Database,         crt: true  },
  { href: "/settings",    label: "Settings",    icon: Settings,         crt: false },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="fixed left-0 top-0 h-screen w-56 border-r border-border bg-card flex flex-col p-3">
      <div className="px-2 py-3 mb-2">
        <span className="text-xs font-bold tracking-widest text-muted-foreground">ZWAN-CODEX</span>
        <div className="text-[10px] text-muted-foreground/50">v2.1</div>
      </div>

      <div className="flex flex-col gap-1 flex-1">
        {links.map(({ href, label, icon: Icon, crt }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              path.startsWith(href)
                ? crt
                  ? "bg-amber-400/10 text-amber-400 border border-amber-400/20"
                  : "bg-accent text-accent-foreground"
                : crt
                  ? "text-amber-400/50 hover:text-amber-400 hover:bg-amber-400/5"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
            )}
          >
            <Icon size={15} />
            {label}
          </Link>
        ))}
      </div>

      {/* System status + stop button always visible at bottom of nav */}
      <SystemBar />
    </nav>
  );
}
