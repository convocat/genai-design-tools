import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

type Entity = {
  id: number;
  name: string;
  type: string;
  description: string;
  degree: number;
};
type Relationship = {
  source: string;
  target: string;
  description: string;
  strength: number;
};
type Community = { id: number; title: string; size: number };
type Member = { community_id: number; entity_name: string };

type GraphPayload = {
  entities: Entity[];
  relationships: Relationship[];
  communities: Community[];
  members: Member[];
};

type GraphNode = Entity & {
  community_id: number | null;
  color: string;
};
type GraphLink = Relationship & {};

const COLORS = [
  "#3E5638", "#9C7A3E", "#A04A2C", "#5B7A8E", "#7A5A8E",
  "#2E8B57", "#B8860B", "#8B0000", "#4682B4", "#6A5ACD",
  "#228B22", "#CD853F", "#8B4513", "#5F9EA0", "#9370DB",
  "#2F4F4F", "#DAA520", "#A52A2A", "#1E90FF", "#9932CC",
  "#006400", "#FF8C00", "#B22222", "#20B2AA", "#8A2BE2",
  "#556B2F", "#D2691E", "#800000", "#00CED1", "#9400D3",
  "#808000", "#FF7F50", "#483D8B",
];

function communityColor(idx: number): string {
  return COLORS[idx % COLORS.length];
}

export function GraphTab() {
  const [data, setData] = useState<GraphPayload | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [minStrength, setMinStrength] = useState(5);
  const [activeCommunity, setActiveCommunity] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  // Library's ref type is generic over node/link shape; pragmatic any avoids
  // a long parameterised union and works at runtime.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 600 });

  useEffect(() => {
    fetch("/api/graph-data")
      .then((r) => r.json())
      .then(setData)
      .catch((e) => console.error("graph-data fetch failed", e));
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      const r = entry.contentRect;
      setDims({ w: Math.max(300, r.width), h: Math.max(300, r.height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const entityToCommunity = useMemo(() => {
    const m = new Map<string, number>();
    if (!data) return m;
    for (const x of data.members) m.set(x.entity_name, x.community_id);
    return m;
  }, [data]);

  const communityIndex = useMemo(() => {
    const m = new Map<number, number>();
    if (!data) return m;
    data.communities.forEach((c, i) => m.set(c.id, i));
    return m;
  }, [data]);

  const graph = useMemo(() => {
    if (!data) return { nodes: [] as GraphNode[], links: [] as GraphLink[] };
    const q = search.trim().toLowerCase();
    const filteredEntities = data.entities.filter((e) => {
      const cid = entityToCommunity.get(e.name) ?? null;
      if (activeCommunity !== "all" && cid !== activeCommunity) return false;
      if (q && !e.name.toLowerCase().includes(q)) return false;
      return true;
    });
    const nameSet = new Set(filteredEntities.map((e) => e.name));
    // Fresh clones each render: react-force-graph mutates node/link refs internally.
    const nodes: GraphNode[] = filteredEntities.map((e) => {
      const cid = entityToCommunity.get(e.name) ?? null;
      const idx = cid != null ? communityIndex.get(cid) ?? 0 : 0;
      return { ...e, community_id: cid, color: cid != null ? communityColor(idx) : "#888" };
    });
    // r.source/target may already be a node object from a prior layout pass; coerce to id string.
    const linkId = (v: unknown): string =>
      typeof v === "string" ? v : (v as { name?: string } | null)?.name ?? "";
    const links: GraphLink[] = data.relationships
      .filter((r) => {
        const s = linkId(r.source);
        const t = linkId(r.target);
        return r.strength >= minStrength && nameSet.has(s) && nameSet.has(t);
      })
      .map((r) => ({ ...r, source: linkId(r.source), target: linkId(r.target) }));
    return { nodes, links };
  }, [data, minStrength, activeCommunity, search, entityToCommunity, communityIndex]);

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading graph…
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1">
      <aside className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto border-r border-border bg-card/40 p-3">
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Graph
          </h3>
          <p className="text-[11px] text-muted-foreground">
            {graph.nodes.length} of {data.entities.length} entities ·{" "}
            {graph.links.length} edges
          </p>
        </div>

        <label className="text-xs">
          <div className="mb-1 flex justify-between">
            <span className="font-medium">Min edge strength</span>
            <span className="tabular-nums text-muted-foreground">{minStrength}</span>
          </div>
          <input
            type="range"
            min={1}
            max={10}
            value={minStrength}
            onChange={(e) => setMinStrength(parseInt(e.target.value))}
            className="w-full"
          />
        </label>

        <label className="text-xs">
          <div className="mb-1 font-medium">Search entity</div>
          <input
            type="text"
            value={search}
            placeholder="filter by name…"
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
          />
        </label>

        <div>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="font-medium">Collections</span>
            <button
              className="text-[10px] text-muted-foreground hover:underline"
              onClick={() => setActiveCommunity("all")}
            >
              reset
            </button>
          </div>
          <ul className="space-y-0.5 text-xs">
            <li>
              <button
                onClick={() => setActiveCommunity("all")}
                className={`w-full rounded px-1.5 py-1 text-left hover:bg-muted ${
                  activeCommunity === "all" ? "bg-muted font-semibold" : ""
                }`}
              >
                All ({data.entities.length})
              </button>
            </li>
            {data.communities.map((c) => {
              const idx = communityIndex.get(c.id) ?? 0;
              const active = activeCommunity === c.id;
              return (
                <li key={c.id}>
                  <button
                    onClick={() => setActiveCommunity(active ? "all" : c.id)}
                    className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left hover:bg-muted ${
                      active ? "bg-muted font-semibold" : ""
                    }`}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: communityColor(idx) }}
                    />
                    <span className="flex-1 truncate" title={c.title}>
                      {c.title}
                    </span>
                    <span className="text-[10px] text-muted-foreground">{c.size}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </aside>

      <div ref={containerRef} className="relative flex-1 bg-background">
        <ForceGraph2D
          ref={fgRef}
          graphData={graph}
          width={dims.w}
          height={dims.h}
          nodeId="name"
          nodeLabel={(n: GraphNode) =>
            `${n.name} (${n.type})${n.description ? "\n" + n.description.slice(0, 120) : ""}`
          }
          nodeVal={(n: GraphNode) => Math.max(2, Math.min(40, n.degree))}
          nodeColor={(n: GraphNode) => n.color}
          linkColor={() => "rgba(60,60,60,0.15)"}
          linkWidth={(l: GraphLink) => Math.max(0.4, l.strength / 4)}
          linkDirectionalParticles={0}
          cooldownTicks={120}
          onNodeClick={(n: GraphNode) => {
            setSelected(n);
            const fg = fgRef.current;
            if (fg && "x" in n && "y" in n) {
              fg.centerAt((n as any).x, (n as any).y, 600);
              fg.zoom(3, 600);
            }
          }}
          onBackgroundClick={() => setSelected(null)}
        />
        {selected && (
          <div className="absolute right-3 top-3 max-w-sm rounded-md border border-border bg-card/95 p-3 text-xs shadow-lg backdrop-blur">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="font-semibold">{selected.name}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase">
                {selected.type}
              </span>
            </div>
            <p className="mb-2 text-[11px] leading-snug text-muted-foreground">
              {selected.description || "(no description)"}
            </p>
            <p className="text-[10px] text-muted-foreground">
              degree {selected.degree} · community{" "}
              {selected.community_id != null
                ? data.communities.find((c) => c.id === selected.community_id)?.title ?? "—"
                : "none"}
            </p>
            <button
              className="mt-2 text-[10px] text-muted-foreground hover:underline"
              onClick={() => setSelected(null)}
            >
              close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
