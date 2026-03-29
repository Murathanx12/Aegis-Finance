"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function ErrorCard({
  title = "API Error",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-red-500/20 bg-red-500/5 animate-fade-in">
      <CardContent className="flex items-start gap-3 p-4">
        <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-red-400">{title}</p>
          <p className="text-xs text-red-400/80 mt-1">{message}</p>
          {message.includes("fetch") && (
            <p className="text-xs text-muted-foreground mt-2">
              Make sure the backend is running:{" "}
              <code className="bg-red-500/10 px-1 rounded text-red-400/70">
                uvicorn backend.main:app --port 8000
              </code>
            </p>
          )}
        </div>
        {onRetry && (
          <Button size="sm" variant="ghost" onClick={onRetry} className="shrink-0 text-red-400 hover:text-red-300">
            <RefreshCw className="h-4 w-4" />
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
