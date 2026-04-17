"use client";

import * as React from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkspace, WorkspaceTile } from "@/hooks/use-workspace";
import { allCommands } from "@/lib/commands";
import { FunctionBadge } from "@/components/function-badge";
import { ArrowRight, X, Plus, RotateCcw, Grid2x2, Grid3x3 } from "lucide-react";

/**
 * Workspace page — Bloomberg-style 2×2 / 3×2 tile grid of favourite views.
 * Each tile is a function code (optionally with a ticker) that deep-links
 * to the full page. Preview content is a one-line summary — users click
 * through for the real view.
 */
export default function WorkspacePage() {
  const { workspace, ready, updateTile, addTile, removeTile, setLayout, reset } =
    useWorkspace();
  const [editing, setEditing] = React.useState<string | null>(null);

  if (!ready) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <div className="grid gap-4 grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="h-48 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const cols =
    workspace.layout === "3x2" ? "grid-cols-3" :
    workspace.layout === "2x3" ? "grid-cols-2" :
    "grid-cols-2";

  const maxTiles =
    workspace.layout === "3x2" ? 6 :
    workspace.layout === "2x3" ? 6 : 4;

  return (
    <div className="space-y-6">
      <PageHeader />

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <LayoutButton
            active={workspace.layout === "2x2"}
            onClick={() => setLayout("2x2")}
            icon={<Grid2x2 className="h-4 w-4" />}
            label="2×2"
          />
          <LayoutButton
            active={workspace.layout === "3x2"}
            onClick={() => setLayout("3x2")}
            icon={<Grid3x3 className="h-4 w-4" />}
            label="3×2"
          />
          <LayoutButton
            active={workspace.layout === "2x3"}
            onClick={() => setLayout("2x3")}
            icon={<Grid2x2 className="h-4 w-4 rotate-90" />}
            label="2×3"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={reset} title="Reset to default tiles">
            <RotateCcw className="h-4 w-4 mr-1.5" />
            Reset
          </Button>
        </div>
      </div>

      <div className={cn("grid gap-4", cols)}>
        {workspace.tiles.map((tile) => (
          <TileCard
            key={tile.id}
            tile={tile}
            isEditing={editing === tile.id}
            onEdit={(v) => setEditing(v ? tile.id : null)}
            onUpdate={(patch) => updateTile(tile.id, patch)}
            onRemove={() => removeTile(tile.id)}
          />
        ))}
        {workspace.tiles.length < maxTiles && (
          <AddTileCard onAdd={(tile) => addTile(tile)} />
        )}
      </div>
    </div>
  );
}

function PageHeader() {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">Workspace</h1>
          <FunctionBadge code="WORK" />
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Your personalised tile layout. Press{" "}
          <kbd className="inline-flex rounded border border-border bg-muted/50 px-1.5 py-0.5 font-mono text-[11px]">
            Ctrl+K
          </kbd>{" "}
          to jump anywhere, or click a tile to drill in.
        </p>
      </div>
    </div>
  );
}

function LayoutButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function TileCard({
  tile,
  isEditing,
  onEdit,
  onUpdate,
  onRemove,
}: {
  tile: WorkspaceTile;
  isEditing: boolean;
  onEdit: (v: boolean) => void;
  onUpdate: (patch: Partial<WorkspaceTile>) => void;
  onRemove: () => void;
}) {
  const def = allCommands().find(
    (c) => c.code === tile.functionCode.toUpperCase(),
  );
  const href = def
    ? typeof def.href === "function"
      ? def.href(tile.ticker)
      : def.href
    : "/";

  return (
    <Card className="relative overflow-hidden h-48 p-0 group">
      <div className="absolute right-2 top-2 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onEdit(!isEditing)}
          className="rounded-md bg-background/80 p-1 text-xs text-muted-foreground hover:text-foreground"
          aria-label="Edit tile"
        >
          edit
        </button>
        <button
          onClick={onRemove}
          className="rounded-md bg-background/80 p-1 text-muted-foreground hover:text-foreground"
          aria-label="Remove tile"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {isEditing ? (
        <TileEditor tile={tile} onSave={(patch) => { onUpdate(patch); onEdit(false); }} />
      ) : (
        <Link href={href} className="flex h-full flex-col p-5 hover:bg-accent/30 transition-colors">
          <div className="flex items-center justify-between mb-2">
            <FunctionBadge code={tile.functionCode.toUpperCase()} />
            {tile.ticker && (
              <span className="font-mono text-xs tracking-wider text-muted-foreground">
                {tile.ticker.toUpperCase()}
              </span>
            )}
          </div>
          <h3 className="text-base font-semibold">
            {tile.label ?? def?.label ?? tile.functionCode}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground leading-relaxed line-clamp-3">
            {def?.description ?? "Custom tile"}
          </p>
          <div className="mt-auto pt-3 text-xs text-muted-foreground flex items-center gap-1">
            Open <ArrowRight className="h-3 w-3" />
          </div>
        </Link>
      )}
    </Card>
  );
}

function TileEditor({
  tile,
  onSave,
}: {
  tile: WorkspaceTile;
  onSave: (patch: Partial<WorkspaceTile>) => void;
}) {
  const [code, setCode] = React.useState(tile.functionCode);
  const [ticker, setTicker] = React.useState(tile.ticker ?? "");
  const [label, setLabel] = React.useState(tile.label ?? "");

  return (
    <div className="flex h-full flex-col gap-2 p-4">
      <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
        Function code
        <select
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm"
        >
          {allCommands().map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
        Ticker (optional)
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="AAPL"
          className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
        />
      </label>
      <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
        Custom label
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="auto"
          className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <div className="mt-auto flex gap-2">
        <Button
          size="sm"
          onClick={() => onSave({ functionCode: code, ticker: ticker || undefined, label: label || undefined })}
        >
          Save
        </Button>
      </div>
    </div>
  );
}

function AddTileCard({ onAdd }: { onAdd: (tile: Omit<WorkspaceTile, "id">) => void }) {
  return (
    <Card className="h-48 p-0 border-dashed flex items-center justify-center">
      <button
        onClick={() => onAdd({ functionCode: "DASH" })}
        className="flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
      >
        <Plus className="h-6 w-6" />
        <span className="text-sm">Add tile</span>
      </button>
    </Card>
  );
}

