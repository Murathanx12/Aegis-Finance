"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CommandBar } from "@/components/command-bar";
import { ShortcutCheatsheet } from "@/components/shortcut-cheatsheet";
import { useShortcuts } from "@/hooks/use-shortcuts";

/**
 * Mount-once shortcut manager. Owns the command palette + cheatsheet dialogs
 * and wires global hotkeys:
 *
 *   Ctrl/Cmd+K → command palette
 *   /          → command palette (focus-to-search convention)
 *   ?          → shortcut cheatsheet
 *   Esc        → (handled by Radix — closes whatever dialog is open)
 *   g h        → go home
 *   g p        → go portfolio
 *   g s        → go screener
 *   g n        → go news
 *   g o        → go outlook
 *   g c        → go crash
 *   g k        → go copilot
 *   g r        → go retirement
 *   g w        → go workspace
 */
export function ShortcutManager() {
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [cheatsheetOpen, setCheatsheetOpen] = React.useState(false);

  useShortcuts(
    React.useMemo(
      () => [
        { combo: "cmd+k", handler: () => setPaletteOpen(true), allowInInputs: true },
        { combo: "ctrl+k", handler: () => setPaletteOpen(true), allowInInputs: true },
        { combo: "/", handler: () => setPaletteOpen(true) },
        { combo: "?", handler: () => setCheatsheetOpen(true) },
        { combo: "g h", handler: () => router.push("/") },
        { combo: "g p", handler: () => router.push("/portfolio") },
        { combo: "g s", handler: () => router.push("/screener") },
        { combo: "g n", handler: () => router.push("/news") },
        { combo: "g o", handler: () => router.push("/outlook") },
        { combo: "g c", handler: () => router.push("/crash") },
        { combo: "g k", handler: () => router.push("/copilot") },
        { combo: "g r", handler: () => router.push("/retirement") },
        { combo: "g w", handler: () => router.push("/workspace") },
        { combo: "g l", handler: () => router.push("/watchlist") },
        { combo: "g e", handler: () => router.push("/screener") },
      ],
      [router],
    ),
  );

  return (
    <>
      <CommandBar open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ShortcutCheatsheet open={cheatsheetOpen} onOpenChange={setCheatsheetOpen} />
    </>
  );
}
