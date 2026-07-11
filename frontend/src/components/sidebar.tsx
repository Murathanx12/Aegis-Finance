"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  TrendingDown,
  BarChart3,
  ListFilter,
  Briefcase,
  PieChart,
  Newspaper,
  Target,
  Info,
  Menu,
  Sun,
  Moon,
  Sparkles,
  LayoutGrid,
  Search,
  Star,
  NotebookPen,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useBeginnerMode } from "@/hooks/use-beginner-mode";

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard; code: string };
type NavGroup = { title: string | null; items: NavItem[]; hideForBeginner?: boolean };

// Grouped navigation: 5 sections instead of a flat 15-item list, with the
// previously unreachable pages (Track Record, World Markets) surfaced.
const NAV_GROUPS: NavGroup[] = [
  {
    title: null,
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, code: "DASH" },
    ],
  },
  {
    title: "Markets",
    items: [
      { href: "/outlook", label: "Market Outlook", icon: TrendingDown, code: "ECO" },
      { href: "/sectors", label: "Sectors", icon: PieChart, code: "SECT" },
      { href: "/world", label: "World Markets", icon: LayoutGrid, code: "WM" },
      { href: "/news", label: "News & Intel", icon: Newspaper, code: "NI" },
    ],
  },
  {
    title: "Stocks",
    items: [
      { href: "/stock", label: "Stock Analysis", icon: BarChart3, code: "GP" },
      { href: "/screener", label: "Screener", icon: ListFilter, code: "EQS" },
      { href: "/watchlist", label: "Watchlist", icon: Star, code: "WATCH" },
    ],
  },
  {
    title: "Portfolio",
    items: [
      { href: "/portfolio", label: "Builder & Analysis", icon: Briefcase, code: "PORT" },
      { href: "/portfolio-intelligence/track-record", label: "Track Record", icon: Activity, code: "NAV" },
      { href: "/portfolio-intelligence/conviction", label: "Conviction", icon: NotebookPen, code: "CONV" },
      { href: "/portfolio-intelligence/risk-watch", label: "Risk Watch", icon: Activity, code: "RISK" },
      { href: "/retirement", label: "Retirement", icon: Target, code: "RETIRE" },
    ],
  },
  {
    title: "Tools",
    hideForBeginner: true,
    items: [
      { href: "/copilot", label: "Copilot", icon: Sparkles, code: "AI" },
      { href: "/workspace", label: "Workspace", icon: LayoutGrid, code: "WORK" },
      { href: "/dev", label: "Dev", icon: LayoutGrid, code: "DEV" },
      { href: "/about", label: "About", icon: Info, code: "ABOUT" },
    ],
  },
];

function NavLinks({ onClick }: { onClick?: () => void }) {
  const pathname = usePathname();
  const { beginner } = useBeginnerMode();

  return (
    <nav className="flex flex-col gap-1 px-3">
      {NAV_GROUPS.map((group) => {
        if (group.hideForBeginner && beginner) return null;
        return (
          <div key={group.title ?? "top"} className="flex flex-col gap-0.5">
            {group.title && (
              <p className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                {group.title}
              </p>
            )}
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClick}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium transition-colors group",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  )}
                >
                  <item.icon className="h-5 w-5 shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  <span
                    className={cn(
                      "font-mono text-[9px] tracking-wider uppercase opacity-0 group-hover:opacity-60 transition-opacity",
                      active && "opacity-60",
                    )}
                    aria-hidden
                  >
                    {item.code}
                  </span>
                </Link>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}

function BeginnerToggle() {
  const { beginner, toggle } = useBeginnerMode();

  return (
    <button
      onClick={toggle}
      className={cn(
        "flex items-center gap-2 w-full rounded-lg px-3 py-2 text-xs font-medium transition-colors",
        beginner
          ? "bg-blue-500/15 text-blue-400"
          : "text-muted-foreground hover:bg-accent hover:text-foreground"
      )}
      aria-pressed={beginner}
      aria-label="Toggle beginner mode"
    >
      <span className={cn(
        "inline-flex h-5 w-9 items-center rounded-full transition-colors",
        beginner ? "bg-blue-500" : "bg-muted"
      )}>
        <span className={cn(
          "h-3.5 w-3.5 rounded-full bg-white transition-transform",
          beginner ? "translate-x-4.5" : "translate-x-0.5"
        )} />
      </span>
      Beginner Mode
    </button>
  );
}

function ThemeToggle() {
  // Avoid SSR/client hydration mismatch — useTheme() returns undefined on the
  // server and the actual theme on the client. Render a stable placeholder
  // until mounted, then switch to the real toggle.
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <button
        className="flex items-center gap-2 w-full rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground"
        aria-label="Toggle theme"
        suppressHydrationWarning
      >
        <Moon className="h-4 w-4" />
        Theme
      </button>
    );
  }

  const isDark = theme === "dark";
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="flex items-center gap-2 w-full rounded-lg px-3 py-2 text-xs font-medium transition-colors text-muted-foreground hover:bg-accent hover:text-foreground"
      aria-label="Toggle theme"
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      {isDark ? "Light Mode" : "Dark Mode"}
    </button>
  );
}

function CommandHint() {
  const onClick = () => {
    // Dispatch a synthetic Ctrl+K so the mounted ShortcutManager picks it up.
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }),
    );
  };
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 w-full rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
      aria-label="Open command palette"
    >
      <Search className="h-3.5 w-3.5" />
      <span className="flex-1 text-left">Search · functions · tickers</span>
      <kbd className="rounded border border-border bg-background/60 px-1.5 py-0.5 font-mono text-[10px]">
        Ctrl K
      </kbd>
    </button>
  );
}

function SidebarContent({ onClick }: { onClick?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5">
        <Image src="/logo.png" alt="Aegis Finance" width={32} height={32} />
        <span className="text-lg font-bold tracking-tight">Aegis Finance</span>
      </div>
      <div className="px-3 mb-3">
        <CommandHint />
      </div>
      <NavLinks onClick={onClick} />
      <div className="mt-auto px-6 py-4 space-y-3">
        <div className="px-0 space-y-1">
          <ThemeToggle />
          <BeginnerToggle />
        </div>
        <p className="text-xs text-muted-foreground">
          Educational tool only. Not financial advice.{" "}
          <span className="block mt-1">
            Press <kbd className="rounded border border-border bg-muted/40 px-1 font-mono text-[10px]">?</kbd> for shortcuts.
          </span>
        </p>
      </div>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:border-r lg:border-border bg-sidebar">
        <SidebarContent />
      </aside>

      {/* Mobile hamburger */}
      <div className="fixed top-0 left-0 z-40 flex h-14 w-full items-center border-b border-border bg-background/80 backdrop-blur-sm px-4 lg:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 p-0 bg-sidebar">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SidebarContent onClick={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
        <div className="flex items-center gap-2 ml-3">
          <Image src="/logo.png" alt="Aegis Finance" width={24} height={24} />
          <span className="font-semibold">Aegis Finance</span>
        </div>
      </div>

      {/* Spacer for mobile header */}
      <div className="h-14 lg:hidden" />
    </>
  );
}
