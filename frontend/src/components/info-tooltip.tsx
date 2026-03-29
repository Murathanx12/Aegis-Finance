"use client";

import { Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useBeginnerMode } from "@/hooks/use-beginner-mode";

interface InfoTooltipProps {
  text: string;
  /** Simpler explanation shown in beginner mode (falls back to `text`) */
  beginnerText?: string;
}

export function InfoTooltip({ text, beginnerText }: InfoTooltipProps) {
  const { beginner } = useBeginnerMode();
  const displayText = beginner && beginnerText ? beginnerText : text;

  // In beginner mode, show the explanation inline instead of hidden in tooltip
  if (beginner) {
    return (
      <span className="inline-flex items-start gap-1 ml-1">
        <Info className="h-3.5 w-3.5 text-blue-400 shrink-0 mt-0.5" />
        <span className="text-xs text-blue-400/80 leading-relaxed">{displayText}</span>
      </span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center justify-center text-muted-foreground hover:text-primary transition-colors ml-1"
          aria-label="What does this mean?"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
        {displayText}
      </TooltipContent>
    </Tooltip>
  );
}
