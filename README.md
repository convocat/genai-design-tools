# GenAI Design

A collection of generative-AI tools and deliverables. Each subdirectory is a self-contained project with its own README, dependencies, and runtime.

## Projects

| Project | What it is |
|---|---|
| [mindstudio-rag/](./mindstudio-rag/) | GraphRAG-style chatbot over the public [MindStudio University](https://university.mindstudio.ai/) docs. Vector + entity-relation graph + Louvain communities + HyDE query rewriting + Langfuse-managed prompts. Python FastAPI backend, React + assistant-ui frontend. |

## Conventions

- Each project ships its own `requirements.txt`, `package.json`, `.env.example`, and `README.md`.
- Secrets live in `.env` files inside each project; never committed.
- Where a project uses LLM APIs, the cost profile is documented in its README.
- Prompts that the project hands to an LLM live in `prompts/*.md` and are managed at runtime via Langfuse (with the local files as fallback).

## Adding a new project

```
mkdir my-new-tool
cd my-new-tool
# project-level README, requirements/package.json, .env.example
```

Update the table above with a one-line description.
