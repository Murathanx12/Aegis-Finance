"use client";

import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Props = {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: { label: string; onClick: () => void };
};

export function EmptyState({ title, description, icon, action }: Props) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-10 text-center">
        <div className="rounded-full bg-muted p-3 text-muted-foreground" aria-hidden>
          {icon ?? <Inbox className="h-5 w-5" />}
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium">{title}</p>
          {description ? (
            <p className="text-xs text-muted-foreground max-w-prose">{description}</p>
          ) : null}
        </div>
        {action ? (
          <Button size="sm" variant="outline" onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
