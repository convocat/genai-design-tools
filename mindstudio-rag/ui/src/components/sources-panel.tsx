import { useEffect, useState } from "react";
import { subscribeSources, type Source } from "@/lib/runtime";

type Collection = { id: number; title: string; summary: string; size: number };

export function SourcesPanel() {
  const [sources, setSources] = useState<Source[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [stats, setStats] = useState<{
    pages?: number;
    chunks?: number;
    entities?: number;
    relationships?: number;
  }>({});

  useEffect(() => subscribeSources(setSources), []);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {});
    fetch("/api/collections")
      .then((r) => r.json())
      .then((d) => setCollections(d.collections ?? []))
      .catch(() => {});
  }, []);

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col gap-4 border-l border-border bg-card/40 p-4 overflow-y-auto">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-tight">MindStudio docs</h2>
        <span className="text-[11px] text-muted-foreground">
          {stats.pages ?? "—"} pages · {stats.entities ?? "—"} entities
        </span>
      </header>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Sources for last answer
        </h3>
        {sources.length === 0 ? (
          <p className="text-xs text-muted-foreground">Ask a question to see citations here.</p>
        ) : (
          <ol className="space-y-2">
            {sources.map((s) => (
              <li key={s.n} className="rounded-md border border-border bg-card p-2 text-xs">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-foreground hover:underline"
                >
                  [{s.n}] {s.title}
                </a>
                <div className="mt-1 break-all text-[10px] text-muted-foreground">{s.url}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">score {s.score}</div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Smart collections ({collections.length})
        </h3>
        <ul className="space-y-1.5">
          {collections.slice(0, 12).map((c) => (
            <li key={c.id}>
              <details className="rounded-md border border-border bg-card text-xs">
                <summary className="cursor-pointer list-none px-2 py-1.5 font-medium hover:bg-muted">
                  <span className="text-muted-foreground">[{c.size}]</span> {c.title}
                </summary>
                <p className="border-t border-border px-2 py-1.5 text-[11px] leading-snug text-muted-foreground">
                  {c.summary}
                </p>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
