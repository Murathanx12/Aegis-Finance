"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BeginnerModeContext, useBeginnerModeState } from "@/hooks/use-beginner-mode";

const STALE_TIME_DEFAULT = 5 * 60 * 1000; // 5 min
const RETRY_COUNT = 2;

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
          <TooltipProvider>{children}</TooltipProvider>
        </BeginnerModeContext.Provider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
