"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BookOpen,
  ClipboardList,
  Globe,
  LayoutDashboard,
  MessageSquare,
  Moon,
} from "lucide-react";
import { DesktopGuide } from "@/components/desktop/guide";
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
  // The BOARD is first (O4): in the desktop app the landing page is the
  // operator's own surface, not the website's marketing dashboard. The
  // universe sits beside it because "show me all the stocks" is the second
  // thing asked of this app and the first thing it could not do.
  { href: "/desktop", label: "Board", icon: LayoutDashboard },
  { href: "/desktop/universe", label: "Universe", icon: Globe },
  { href: "/desktop/night", label: "Night runs", icon: Moon },
  { href: "/desktop/fleet", label: "Fleet vs SPY", icon: Activity },
  { href: "/desktop/books", label: "Books", icon: BookOpen },
  // Lane A. It sits after Books because an agency book IS a paper book with
  // an IPS behind it, and a reader who has not seen the book table first has
  // no idea what the three options are options over.
  { href: "/desktop/agency", label: "Agency", icon: ClipboardList },
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

      <nav className="flex flex-wrap items-center gap-1 border-b border-border pb-2">
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
        {/* The first-run guide, and the only way back to it. A dialog that can
            be seen exactly once is a dialog nobody can re-read. */}
        <div className="ml-auto">
          <DesktopGuide />
        </div>
      </nav>

      {children}
    </div>
  );
}
