---
layout: post
title: "From Zero-Gap to Zero-Drift: Making AI Follow Rails Rules (Frozen vs Strict)"
date: 2026-01-07
author: Max Lukin
tags: [ai, software-engineering, rails, api, governance, prompts, verification, contracts]
categories: [engineering, rails, AI, best-practices]
description: "A practical upgrade to the Zero-Gap framework: how we reduced AI rule drift using a single entry-point prompt, Hard-Fail rules, evidence-based audits, negative examples, and bin/verify—with Frozen and Strict modes."
---

> **TL;DR**
>
> - Contract-first + verification gates eliminate *gaps* (missing fields, regressions). fileciteturn2file0  
> - But LLMs still create **rule drift** (they quote rules, then violate them).
> - We fixed drift with **guardrails**, not more prose: **Hard-Fail rule IDs**, **STOP gates**, **mandatory evidence audits**, and **negative examples**.
> - Entry point stays tiny and stable; the enforcement lives in versioned docs.
> - We keep two profiles: **Frozen (v1.0)** for speed, **Strict (v1.1)** for enforcement.

---

## Why this follow-up exists

In **Zero-Gap API Development**, the goal was “ship APIs with zero regressions” by turning implementation into a contract + verification problem: TypeScript interfaces as canonical truth, safe defaults, systematic verification gates, and discrepancy classification (`[IMPL]` vs `[DOC]`). fileciteturn2file0

That framework works. The problem we hit next was different:

> **AI doesn’t drift because rules are unclear. It drifts because rules have no consequences.**

Even when an agent reads `AGENTS.md` and repeats rules back, it can still “helpfully” shortcut:
- “Use Ransack for filtering/searching.” → agent writes custom `where(...)` anyway.
- “Avoid DB-specific SQL.” → agent sneaks in `ILIKE`, `IFNULL`, `REGEXP`, etc.
- “Controllers only wrap envelopes.” → agent hand-builds JSON in controller.

So this session was about adding an enforcement layer on top of Zero-Gap.

---

## The goal of this session

We wanted a system where a reviewer can say:

> “This violates **two rules**: HF-1 and HF-2”

…**and the agent itself is forced to detect and correct that before shipping code.**

To do that, we restructured the workflow into a toolchain:

- `PROMPT.md` → execution runtime (phases, STOP gates, verification receipts)
- `AGENTS.md` → **hard authority** (Hard-Fail rules, failure semantics)
- `GUIDE.md` → patterns & examples (non-authority, includes anti-patterns)
- `bin/verify` → canonical verifier

---

## The single entry point (stable forever)

Instead of embedding giant prompts in README/issues, every task uses the same tiny entry point:

```text
Task: WEB-485 – User Notifications

Refs:
- Requirements: doc/requirements/users/USER_NOTIFICATIONS.md
- Flow: doc/flow/WEB-485_user_notifications.md
- PRD: doc/prd/WEB-485_user_notifications_PRD.md

Execute per PROMPT.md.
```

**Important property:** the task block never changes.  
Strictness evolves only inside `PROMPT.md`, `AGENTS.md`, and `GUIDE.md`.

This prevents the most common drift source: copying outdated prompt blobs across tickets.

---

## Frozen vs Strict: why we keep both

We ended up with two prompt profiles:

### Frozen (v1.0)
- Optimized for: **brevity**, human readability, speed
- Best for: trusted contributors, small refactors, quick spikes
- Weakness: rules are descriptive (“MUST”), so AI can rationalize shortcuts

### Strict (v1.1)
- Optimized for: **compliance**, auditability, “no surprises” AI execution
- Best for: contract-sensitive endpoints, anything touching search/filtering/auth/pagination
- Weakness: longer text (but it’s enforcement scaffolding, not noise)

The key is: **both share the same entry point.** You swap the runtime, not the call site.

---

## What actually stops drift (the 4 mechanisms)

### 1) Hard-Fail rule IDs (HF-*)
Instead of “Rule #5,” we introduced stable IDs:

- **HF-1** — Ransack-only search/filtering
- **HF-2** — DB-agnostic queries only (no raw SQL / DB-specific funcs)
- **HF-3** — Blueprinter-only JSON
- **HF-4** — snake_case only
- **HF-5** — Required fields never null (safe defaults)

**Why IDs matter:** they turn “standards” into enforceable references:
- easy review comments (“HF-2 violation”)
- easy self-audit checkboxes
- easy future evolution (rename content, keep ID stable)

### 2) STOP gates (control flow, not suggestions)
Strict mode adds explicit control flow:
- Phase 0–2: **NO CODE**
- Stop after planning
- If any HF-* would be violated → **STOP** and report

LLMs follow control flow better than prose.

### 3) Mandatory Rule Compliance Audit (proof, not vibes)
Before final output, the agent must produce:

```text
RULE COMPLIANCE AUDIT
HF-1: COMPLIANT — evidence: UsersController#index uses User.ransack(params[:q])
HF-2: COMPLIANT — evidence: no raw SQL; only ActiveRecord/Arel
...
```

This forces the agent to *prove* it complied.
If it can’t produce evidence, it typically self-corrects before shipping.

### 4) Negative examples (anti-pattern firewall)
Guides that only show “good” patterns still allow AI to invent “bad” ones.
So we added explicit “DO NOT COPY” snippets:

```ruby
# ❌ HF-1 violation (manual SQL filtering)
User.where("email ILIKE ?", "%#{params[:email]}%")

# ✅ Correct (Ransack owns filtering)
User.ransack(params[:q]).result
```

LLMs imitate examples aggressively. Negative examples prevent “helpful improvisation.”

---

## Example: the exact drift we’re preventing

### Bad (HF-1 + HF-2 violation)
```ruby
# ❌ don't do this
users = User.where("email ILIKE ?", "%#{params[:email]}%")
```

### Good (HF-1 compliant)
```ruby
search = User.ransack(params[:q])
users  = search.result.page(params[:page]).per(params[:per_page] || 20)
```

In strict mode, if an agent proposes the bad version, it must output:

```text
❌ RULE VIOLATION
Rule: HF-1
Location: app/controllers/...:12
Reason: manual filtering used instead of Ransack
Required Fix: replace with Model.ransack(params[:q]).result
```

No debate. Fix it or stop.

---

## Verification: one command, one receipt

Zero-Gap already required verification gates. fileciteturn2file0  
The strict upgrade makes verification harder to “forget” by standardizing:

- Preferred: `bin/verify`
- Legacy commands remain in docs as commented fallback

And the final output requires a **CHECKS** section with exit codes.

That turns “I think I ran tests” into a receipt.

---

## Operational guidance: when to use which mode

Use **Frozen (v1.0)** when:
- small refactor
- low contract risk
- you want short prompts and fast iteration

Use **Strict (v1.1)** when:
- building/upgrading endpoints
- touching filtering/search/pagination/auth
- upgrading versioned requirement docs
- AI is doing most of the work

If in doubt: default to **Strict**.

---

## Closing: Zero-Gap is the architecture; Zero-Drift is governance

Zero-Gap prevents missing fields and regressions by making contracts and verification non-negotiable. fileciteturn2file0  
Zero-Drift makes AI reliably follow your engineering rules by adding:

- failure semantics
- proof requirements
- anti-pattern training
- a stable entry point
- a canonical verifier

In practice, this reduces review churn dramatically:
you spend less time catching “obvious violations” and more time on product decisions.

---

### Appendix: quick mental model

- `REQUIREMENT_DOC` = spec
- `PROMPT.md` = runtime
- `AGENTS.md` = language law + compiler errors (HF-*)
- `GUIDE.md` = standard library + examples
- `bin/verify` = test runner
