"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useContext, useEffect } from "react";
import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BeginnerModeContext, useBeginnerModeState } from "@/hooks/use-beginner-mode";
import { ShortcutManager } from "@/components/shortcut-manager";
import { FirstRunTour } from "@/components/first-run-tour";

const STALE_TIME_DEFAULT = 5 * 60 * 1000; // 5 min
// One retry: the heavy endpoints recompute for minutes when cold, so a
// third identical attempt only amplified backend load exactly when slow.
const RETRY_COUNT = 1;

function BeginnerModeBodyClass() {
  const beginner = useContext(BeginnerModeContext).beginner;
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (beginner) {
      document.documentElement.setAttribute("data-beginner", "true");
    } else {
      document.documentElement.removeAttribute("data-beginner");
    }
  }, [beginner]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: STALE_TIME_DEFAULT,
            retry: RETRY_COUNT,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  const beginnerMode = useBeginnerModeState();

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
      <QueryClientProvider client={queryClient}>
        <BeginnerModeContext.Provider value={beginnerMode}>
          <TooltipProvider>
            <BeginnerModeBodyClass />
            {children}
            <ShortcutManager />
            <FirstRunTour />
          </TooltipProvider>
        </BeginnerModeContext.Provider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
