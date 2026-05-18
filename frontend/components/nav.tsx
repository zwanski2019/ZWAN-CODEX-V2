"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Target, Cpu, Search, Settings } from "lucide-react";

const links = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/engagements", label: "Engagements", icon: Target },
  { href: "/agents", label: "Agents", icon: Cpu },
  { href: "/loot", label: "Loot", icon: Search },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="fixed left-0 top-0 h-screen w-56 border-r border-border bg-card flex flex-col gap-1 p-3">
      <div className="px-2 py-3 mb-2">
        <span className="text-xs font-bold tracking-widest text-muted-foreground">ZWAN-CODEX</span>
        <div className="text-[10px] text-muted-foreground/50">v2.0</div>
      </div>
      {links.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            path.startsWith(href)
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          )}
        >
          <Icon size={15} />
          {label}
        </Link>
      ))}
    </nav>
  );
}
