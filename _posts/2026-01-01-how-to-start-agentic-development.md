---
layout: post
title: "How to Start with Agentic Development: What to Know, What to Automate, and How to Use It"
date: 2026-01-01
author: Max Lukin
tags: [ai, agentic-development, software-engineering, productivity, rails, golang, mcp, rag, lsp, codex, claude-code, documentation, testing]
categories: [engineering, AI, best-practices]
description: "A senior-engineer playbook for agentic development: the mental model, the tooling vocabulary (AGENTS.md, Skills, MCP, RAG, LSP, Hooks), and a practical repo setup that increases speed without sacrificing code quality."
---

> **TL;DR**
>
> - Agentic development is a loop: **Plan → Act (tools) → Observe → Decide → Repeat**.
> - The biggest productivity gains come from **determinism, not prompting**: a single verify command, quality gates, and enforcement via hooks.
> - The “must-know” stack in 2026: **AGENTS.md**, **Skills**, **MCP**, **RAG**, **LSP**, **Hooks**, and **Workflows**.
> - My two most effective multipliers:
>   - **Contract-first + verification gates** (“Zero‑Gap API development”)
>   - **Documentation hierarchy + Flow docs with Responsible Files** (documentation-driven development that scales)

---

## Why agentic development feels different from “AI coding assistants”

Autocomplete and chat are mostly **suggestion engines**.

Agentic development is when the model runs a structured loop with tools:

- it reads your repo conventions
- it edits multiple files
- it runs commands
- it interprets errors
- it iterates until the system is green

That means your productivity is no longer limited by “how well can I prompt?”  
It’s limited by **how well your repo communicates intent and enforces correctness**.

The modern skill is not “prompting.”  
It’s **context engineering + verification engineering**.

---

## The mental model: the agent loop

An “agent” is just a loop with tool use:

1. **Plan** (what files, what changes, what tests)
2. **Act** (edit files, run commands, call tools)
3. **Observe** (test output, logs, compiler errors, lint)
4. **Decide** (fix, rollback, re-plan)
5. Repeat until done

Your job (as a senior engineer) is to make this loop:

- **well-scoped** (small diffs, explicit “definition of done”)
- **well-instrumented** (fast tests + lint + security checks)
- **hard to cheat** (quality gates / hooks / CI)
- **context-efficient** (agent sees the right context, not more context)

---

## Glossary: plugins, skills, MCP, RAG, LSP, hooks, workflows

Here’s the vocabulary, in a practical order:

### AGENTS.md
A repo-local “operating manual” for coding agents.

**What it’s for**
- Encode how *this repo* works (commands, conventions, boundaries)
- Stop re-explaining the same rules every session
- Make agent behavior predictable across tasks

Think: `README.md` for agents, but stricter and more actionable.

---

### Skills
A “Skill” is a packaged workflow (instructions + optional resources/scripts) that the agent can load on demand.

**What it’s for**
- Turn your best senior workflows into reusable modules:
  - “Implement Rails endpoint from contract + request specs”
  - “Safe refactor: characterization tests first”
  - “Write flow doc + Responsible Files table”
- Reduce quality drift and context repetition

If AGENTS.md is global repo policy, Skills are **repeatable procedures**.

---

### Hooks
Hooks are automation that runs at specific moments (after edits, before stopping, etc.).

**What it’s for**
- Enforce quality without relying on “remember to do it”
- Auto-format after edits
- Block dangerous operations
- Require `bin/verify` passing before the agent can “finish”

Prompts are best-effort. Hooks are default behavior.

---

### Workflows
Workflows are your end-to-end process:
- feature → tests → verify → docs → PR
- bugfix → reproduction test → fix → verify → postmortem note

Skills + hooks + CI turn workflows into a system.

---

### RAG (Retrieval-Augmented Generation)
RAG is the pattern of retrieving relevant docs/files and injecting them as context for the model.

**What it’s for**
- Ground the agent in *your* docs and code
- Reduce hallucinations
- Make “documentation-driven development” actually useful to the model

In practice: RAG is how an agent “remembers” your system without you pasting the whole repo.

---

### LSP (Language Server Protocol)
LSP is what powers “go to definition,” “find references,” “rename symbol,” etc.

**What it’s for**
- Semantic navigation beats grep for refactors and correctness
- Agents become safer when they can reliably answer:
  - “Where is this symbol used?”
  - “What implements this interface?”
  - “What breaks if I change this method signature?”

---

### MCP (Model Context Protocol)
MCP is a standard way to connect an agent to tools and data sources (issue trackers, DB schema, docs, internal APIs).

**What it’s for**
- Reduce copy/paste context
- Give structured, permissioned access to external systems
- Make tool integrations reusable across clients/vendors

MCP is most useful when your bottleneck is **access to information/tools**, not coding speed.

---

## The “agentic stack” in one picture

A practical way to visualize the stack:

```
Workflow (what to do)
  └─ Hooks (force it to happen)
      └─ Tool/data access (MCP)
          └─ Context feeding (RAG + LSP)
              └─ Skills (repeatable procedures)
                  └─ AGENTS.md (repo rules + commands + DoD)
```

If you want a big productivity jump: build from the bottom up.

---

## The senior engineer principle: determinism beats prompting

If something must happen every time:
- formatting
- tests
- lint
- security scan
- contract compliance check

…don’t “ask the model to remember.”

Make it **one command** and/or enforce it with **hooks** + CI.

This is the same reason “Zero‑Gap API Development” works: it’s a deterministic pipeline (contract → implement → verify → document), not vibes.  
And it’s the same reason documentation-driven development scales for large systems: it creates deterministic “where to look” maps.

---

## A universal framework that scales: Requirements → Implementation → Documentation

This generalizes cleanly across Rails monoliths, Go services, and polyglot repos:

```
┌──────────────────────────────────────────────┐
│ Layer 1: Requirements / Contracts            │
│ - Interfaces / OpenAPI / protobuf / specs    │
│ - Single source of truth                     │
└──────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ Layer 2: Implementation + Verification       │
│ - Code + tests + lint + security             │
│ - One “judge” command: bin/verify            │
└──────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ Layer 3: Documentation / Memory              │
│ - Flow docs (how it’s implemented)           │
│ - PRDs (why it exists)                       │
│ - Responsible Files tables                   │
└──────────────────────────────────────────────┘
```

Two key rules:
- **Docs are generated/updated only after verification passes**
- **Contracts are treated as the canonical truth** (or explicitly flagged when reality diverges)

---

## Step 1: Add AGENTS.md to every repo

Put this at the repo root. Keep it short and operational.

```md
# AGENTS.md — Project instructions for coding agents

## Prime directive
- Prefer small, verifiable changes.
- Never skip verification commands.
- If unsure: add/adjust tests first to lock behavior.

## Commands (source of truth)
### Ruby / Rails
- Setup: bundle install
- Test:  bin/test
- Lint:  bin/lint
- Verify (must pass before PR): bin/verify
- Security: bin/security

### Go (if present)
- Test:  make test
- Lint:  make lint
- Verify: make verify

### Node (if present)
- Test:  pnpm test
- Lint:  pnpm lint
- Typecheck: pnpm typecheck

## Definition of Done
- [ ] Implementation matches contract/specs
- [ ] Tests added/updated and pass
- [ ] Lint/static checks pass
- [ ] Security checks pass
- [ ] Docs updated (flow + PRD) if behavior changed
- [ ] No unrelated refactors in same diff

## Safety boundaries
- Don’t touch secrets/credentials or production config.
- Ask before adding dependencies or changing CI.
```

This alone reduces agent thrash dramatically.

---

## Step 2: Create one “judge command” (`bin/verify`)

Agents converge faster when there’s exactly one command that says “reality is correct.”

### Rails example

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "==> Lint"
bundle exec rubocop

echo "==> Tests"
bundle exec rspec

echo "==> Security (brakeman)"
bundle exec brakeman -q -w2

echo "==> Dependency audit"
bundle exec bundle audit check --update

echo "==> API docs generation (if used)"
bundle exec rails rswag:specs:swaggerize

echo "✅ verify passed"
```

### Go example

```makefile
verify:
	@gofmt -w .
	@golangci-lint run
	@go test ./...
```

The exact tools don’t matter.  
What matters is: **one obvious place to run the truth.**

---

## Step 3: Use contract-first development (especially for APIs)

My most reliable pattern for AI-assisted Rails APIs is contract-first:

- treat an interface/spec as canonical truth
- implement strictly against it
- verify via gates
- then update docs

### Safe defaults matter (required fields are never null)
In contract-first work, required fields should not come back as null “because DB is sparse.”

Use safe defaults by type:

| Type | Default |
|------|---------|
| String | `""` |
| Number | `0` or minimum valid |
| Boolean | `false` |
| Array | `[]` |
| Object | minimal valid object |
| Timestamp | `Time.current.iso8601` |

This removes a common “agent bug class”: missing fields / inconsistent shapes.

### Discrepancy tagging: `[IMPL]` vs `[DOC]`
When auditing contract compliance, classify gaps:

- **`[IMPL]`** → code is wrong, fix it now, rerun verification
- **`[DOC]`** → the doc/contract is wrong (DB/model reality differs), flag it, don’t silently change requirements

This small habit prevents teams from corrupting the source of truth.

---

## Step 4: Documentation-driven development for complex systems

When systems explode in complexity (MMORPG-scale, or any mature SaaS), your bottleneck becomes **coherence**, not raw coding time.

The pattern that scales:

### Documentation hierarchy
- **GDD / vision docs**: what the system is
- **Feature docs**: what each subsystem must do
- **Flow docs**: how it’s implemented (step-by-step + file ownership)

This is the structure that makes large Rails monoliths maintainable, and also makes AI agents effective because they can retrieve the correct context instead of guessing.

### Flow docs + Responsible Files tables
Flow docs should include:

- “Use case” steps that trace UI → controller → service → persistence → broadcast
- Key behaviors / invariants
- A “Responsible Files” table so anyone (human or agent) can jump to the right code immediately

Example table:

| Purpose | File |
|--------|------|
| Combat service | `app/services/game/combat/turn_based_combat_service.rb` |
| Stimulus controller | `app/javascript/controllers/turn_combat_controller.js` |
| View | `app/views/combat/_battle.html.erb` |
| Config | `config/gameplay/combat_actions.yml` |

This is the best “RAG corpus” you can build: docs that directly point to code.

---

## Step 5: Turn your best practices into Skills

Here’s the trick: you already wrote the workflows in prose.

Now you package them so the agent can apply them repeatedly.

### Skill ideas that map to real work
- **`rails-zero-gap-endpoint`**
  - input: requirement doc (contract), expected behavior
  - output: controller + serializer/blueprint + request specs + docs updates
  - gate: must pass `bin/verify`

- **`flow-doc-maintainer`**
  - update flow steps
  - update Responsible Files table
  - append version history (never overwrite)

- **`safe-refactor`**
  - add characterization tests first
  - refactor
  - rerun verify
  - summarize risk and coverage

- **`go-service-skeleton`**
  - standard layout (cmd/, internal/, pkg/)
  - health, metrics, config, structured logging
  - make verify/test/lint

### Skill template (conceptual)
```md
# SKILL.md
name: rails-zero-gap-endpoint
description: Implements a Rails API endpoint from a contract/spec with tests, verification, and doc updates.

## Steps
1. Read contract/spec in doc/requirements/**.
2. Identify response shapes and status codes.
3. Implement with serializers/blueprints.
4. Add request specs (success + error cases).
5. Run bin/verify; fix until green.
6. Update flow doc + PRD notes; append version history.
```

The point is not “more features.”  
The point is **standardizing your best engineering behavior**.

---

## Step 6: Add hooks so quality is automatic

Once `bin/verify` exists, hooks become a superpower.

High ROI hooks:
- **Format after edits**
- **Block sensitive files**
- **Don’t stop until verify passes**
- **Auto-add a short change log entry for docs**

This is how you get “ship faster” *and* “ship safer” at the same time.

---

## When to use RAG vs LSP vs MCP

### Use RAG when you have good docs but agents don’t see them
If you already maintain:
- contracts/specs
- flow docs
- ADRs
- runbooks

…RAG turns that into a searchable memory.

**Best practice:** write docs in chunks that can be retrieved (short sections, clear headings, explicit file names).

### Use LSP when correctness depends on understanding symbol relationships
Refactors, renames, interface changes → you want semantic certainty.

### Use MCP when the bottleneck is tool/data access
If your “context” lives outside the repo:
- DB schema details
- tickets/PRDs in trackers
- dashboards/logs
- internal service catalogs

…MCP makes that safe and standardized.

---

## A practical daily workflow that compounds productivity

### Feature workflow
1. Define/confirm contract/spec (or acceptance criteria)
2. Agent generates a plan: files + tests + risks
3. Implement smallest vertical slice
4. Run `bin/verify` until green
5. Audit for gaps (`[IMPL]` / `[DOC]`)
6. Update flow doc + PRD notes

### Bugfix workflow
1. Reproduce + write failing test
2. Minimal fix
3. `bin/verify`
4. Add a short note to flow doc/runbook if it’s a recurring class

### Refactor workflow
1. Add characterization tests (freeze behavior)
2. Refactor
3. `bin/verify`
4. Optional: second agent acts as a paranoid reviewer (coverage + edge cases)

---

## A 60-minute “starter kit” checklist

If you want immediate impact, do this in your next repo:

- [ ] Add `AGENTS.md`
- [ ] Add `bin/verify` (one truth command)
- [ ] Add `bin/test`, `bin/lint`, `bin/security`, `bin/format`
- [ ] Add `/doc/` map in README (what doc is where)
- [ ] Add 1 Skill for your most common task
- [ ] Add 1–2 hooks to enforce formatting + verify
- [ ] In CI: run `bin/verify` (same as local)

This is the shortest path to “significantly increase daily process.”

---

## Closing: the real multiplier is the system

AI doesn’t make a team fast.  
**A fast feedback loop makes a team fast.**

Agentic development works when:

- **Truth is easy to check** (`bin/verify`)
- **Intent is easy to find** (contracts + flow docs + Responsible Files)
- **Quality is enforced** (hooks + CI)
- **Workflows are reusable** (Skills)

Once those exist, models become replaceable.  
Your process stays.
