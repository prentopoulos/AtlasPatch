import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { parseSnapshotText, type LoadResult } from "@/lib/snapshot";

interface SnapshotLoaderProps {
  onLoad: (result: LoadResult) => void;
}

/**
 * The point-in-time snapshot loader (design D-REACT-2): a file picker + drag-drop zone that
 * reads a `snapshot.json` and hands the parsed `LoadResult` up. It never fetches or polls — a
 * static client only ever reads a file the operator supplies. Parsing a malformed or
 * version-mismatched file returns an explicit result rather than throwing.
 */
export function SnapshotLoader({ onLoad }: SnapshotLoaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const readFile = useCallback(
    async (file: File) => {
      try {
        const text = await file.text();
        onLoad(parseSnapshotText(text));
      } catch {
        onLoad({ status: "malformed", message: "Could not read the selected file." });
      }
    },
    [onLoad],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void readFile(file);
    },
    [readFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "inline-flex items-center gap-2.5 rounded-lg border border-dashed border-border bg-card/40 px-3 py-2 text-xs text-muted-foreground transition-colors",
        dragging && "border-ring bg-muted/60 text-foreground",
      )}
    >
      <Upload className="size-4 shrink-0" aria-hidden="true" />
      <span className="hidden whitespace-nowrap sm:inline">
        Drop a <code className="font-mono">snapshot.json</code>, or
      </span>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="shrink-0 whitespace-nowrap rounded-md border border-border bg-muted px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-border"
      >
        Choose file
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        aria-label="Load snapshot file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void readFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
