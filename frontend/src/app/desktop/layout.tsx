"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, MessageSquare, Moon, Server } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Aegis Desktop — the operator surface of the packaged app.
 *
 * Every page under here talks ONLY to `/api/control/*` on the same origin that
 * served the page (see `lib/control-api.ts`). Nothing here places an order, arms
 * a book, or seals anything; the control plane has no broker import and an AST
 * test keeps it that way.
 */
const TABS = [
  { href: "/desktop", label: "Services", icon: Server },
  { href: "/desktop/night", label: "Night runs", icon: Moon },
  { href: "/desktop/fleet", label: "Fleet vs SPY", icon: Activity },
  { href: "/desktop/ask", label: "Ask Aegis", icon: MessageSquare },
];

export default function DesktopLayout({ children }: { children: React.ReactNode }) {
  const raw = usePathname() ?? "/desktop";
  // The static desktop build uses trailing slashes; strip one so /desktop/night/
  // and /desktop/night are the same tab.
  const pathname = raw.length > 1 && raw.endsWith("/") ? raw.slice(0, -1) : raw;

  return (
    <div className="space-y-5 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Aegis Desktop</h1>
        <p className="text-sm text-muted-foreground">
          Local control plane. Every number on these pages comes from a{" "}
          <span className="font-mono">/api/control</span> payload — where a field is
          absent the page prints an em dash, never a stand-in.
        </p>
      </div>

      <nav className="flex flex-wrap gap-1 border-b border-border pb-2">
        {TABS.map((t) => {
          const active = pathname === t.href;
          const Icon = t.icon;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              <Icon className="size-3.5" />
              {t.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
