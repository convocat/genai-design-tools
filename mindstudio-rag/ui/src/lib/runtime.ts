import type { ChatModelAdapter } from "@assistant-ui/react";

export type Source = { n: number; url: string; title: string; score: number };

let pendingSources: Source[] = [];
const sourceListeners = new Set<(s: Source[]) => void>();

export function subscribeSources(cb: (s: Source[]) => void): () => void {
  sourceListeners.add(cb);
  cb(pendingSources);
  return () => sourceListeners.delete(cb);
}

function setSources(s: Source[]) {
  pendingSources = s;
  sourceListeners.forEach((cb) => cb(s));
}

const HISTORY_LIMIT = 10;

export const MindStudioAdapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    const last = messages[messages.length - 1];
    const question = last.content
      .map((p) => (p.type === "text" ? p.text : ""))
      .join(" ")
      .trim();

    if (!question) {
      yield { content: [{ type: "text", text: "Ask me anything about MindStudio University." }] };
      return;
    }

    // Build history from prior messages (skip the most recent, which IS the new question).
    const history = messages
      .slice(0, -1)
      .slice(-HISTORY_LIMIT)
      .map((m) => ({
        role: m.role,
        content: m.content
          .map((p) => (p.type === "text" ? p.text : ""))
          .join(" ")
          .trim(),
      }))
      .filter((m) => (m.role === "user" || m.role === "assistant") && m.content);

    setSources([]);

    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
      signal: abortSignal,
    });

    if (!resp.ok || !resp.body) {
      yield { content: [{ type: "text", text: `Error: ${resp.status} ${resp.statusText}` }] };
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let answer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        let evt: { type: string; text?: string; sources?: Source[]; error?: string };
        try {
          evt = JSON.parse(line);
        } catch {
          continue;
        }
        if (evt.type === "sources" && evt.sources) {
          setSources(evt.sources);
        } else if (evt.type === "token" && typeof evt.text === "string") {
          answer += evt.text;
          yield { content: [{ type: "text", text: answer }] };
        } else if (evt.type === "error") {
          yield { content: [{ type: "text", text: `Error: ${evt.error}` }] };
          return;
        } else if (evt.type === "done") {
          return;
        }
      }
    }
  },
};
