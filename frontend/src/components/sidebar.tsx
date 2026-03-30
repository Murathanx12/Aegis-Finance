"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  TrendingDown,
  BarChart3,
  Briefcase,
  PieChart,
  Newspaper,
  Target,
  Info,
  Menu,
  Sun,
  Moon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useBeginnerMode } from "@/hooks/use-beginner-mode";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/outlook", label: "Market Outlook", icon: TrendingDown },
  { href: "/stock", label: "Stock Analysis", icon: BarChart3 },
  { href: "/sectors", label: "Sectors", icon: PieChart },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/news", label: "News & Intel", icon: Newspaper },
  { href: "/retirement", label: "Retirement", icon: Target },
  { href: "/about", label: "About", icon: Info },
];

function NavLinks({ onClick }: { onClick?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 px-3">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onClick}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {item.label}
          </Link>
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
  const { theme, setTheme } = useTheme();
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

function SidebarContent({ onClick }: { onClick?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-5">
        <Image src="/logo.png" alt="Aegis Finance" width={32} height={32} />
        <span className="text-lg font-bold tracking-tight">Aegis Finance</span>
      </div>
      <NavLinks onClick={onClick} />
      <div className="mt-auto px-6 py-4 space-y-3">
        <div className="px-0 space-y-1">
          <ThemeToggle />
          <BeginnerToggle />
        </div>
        <p className="text-xs text-muted-foreground">
          Educational tool only. Not financial advice.
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
