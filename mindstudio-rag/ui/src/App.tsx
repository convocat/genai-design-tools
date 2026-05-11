import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/thread";
import { SourcesPanel } from "@/components/sources-panel";
import { MindStudioAdapter } from "@/lib/runtime";
import { TooltipProvider } from "@/components/ui/tooltip";

function App() {
  const runtime = useLocalRuntime(MindStudioAdapter);

  return (
    <TooltipProvider>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="flex h-screen w-screen flex-col bg-background">
          <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
            <div className="flex items-baseline gap-3">
              <h1 className="text-lg font-semibold tracking-tight">MindStudio University bot</h1>
              <span className="text-xs text-muted-foreground">
                graph-RAG · {Intl.DateTimeFormat().resolvedOptions().timeZone}
              </span>
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
            <div className="min-w-0 flex-1">
              <Thread />
            </div>
            <SourcesPanel />
          </main>
        </div>
      </AssistantRuntimeProvider>
    </TooltipProvider>
  );
}

export default App;
