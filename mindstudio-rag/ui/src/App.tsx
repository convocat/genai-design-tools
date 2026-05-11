import { useState } from "react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/thread";
import { SourcesPanel } from "@/components/sources-panel";
import { GraphTab } from "@/components/graph-tab";
import { MindStudioAdapter } from "@/lib/runtime";
import { TooltipProvider } from "@/components/ui/tooltip";

type Tab = "chat" | "graph";

function App() {
  const runtime = useLocalRuntime(MindStudioAdapter);
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <TooltipProvider>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="flex h-screen w-screen flex-col bg-background">
          <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
            <div className="flex items-baseline gap-4">
              <h1 className="text-lg font-semibold tracking-tight">MindStudio University bot</h1>
              <nav className="flex gap-1 text-sm">
                <button
                  onClick={() => setTab("chat")}
                  className={`rounded px-2.5 py-1 ${
                    tab === "chat"
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Chat
                </button>
                <button
                  onClick={() => setTab("graph")}
                  className={`rounded px-2.5 py-1 ${
                    tab === "graph"
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Graph
                </button>
              </nav>
            </div>
            <a
              href="https://university.mindstudio.ai/"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground hover:underline"
            >
              source docs →
            </a>
          </header>
          <main className="flex min-h-0 flex-1">
            {tab === "chat" ? (
              <>
                <div className="min-w-0 flex-1">
                  <Thread />
                </div>
                <SourcesPanel />
              </>
            ) : (
              <GraphTab />
            )}
          </main>
        </div>
      </AssistantRuntimeProvider>
    </TooltipProvider>
  );
}

export default App;
