---
layout: post
title: "How I Turned AI Into a 5x Backend Force Multiplier as One Principal Engineer"
date: 2026-04-07
author: Max Lukin
tags: [ai, software-engineering, principal-engineer, rails, verification, contracts, productivity]
categories: [engineering, rails, AI, leadership]
description: "How one principal backend engineer shipped 400+ PRs, built a zero-drift delivery system, reduced onboarding to about an hour, and turned 16 years of experience into a reusable AI operating system."
---

> _"The biggest AI productivity gain I've seen wasn't faster code generation. It was turning senior judgment into a system that makes drift expensive and correctness cheap."_

## TL;DR

| Metric | Value |
| --- | ---: |
| Solo backend output | **400+ PRs** |
| Wider comparison group | **11 engineers / 1,000+ PRs** |
| Solo share of visible PR volume | **40%+** |
| Solo PR vs avg engineer | **4.4x+** |
| Validation loop | **~39s** |
| Tests | **7,445 / 0 failures** |
| Contract audit | **6/6 checks** |
| Tooling cost | **$200 vs $4,000+/month** |
| Engineering cost avoided | **$10.5k–12k/month** |
| Yearly savings (eng + QA) | **$115k–132k/year** |
| Onboarding | **~1 hour to ship** |

I effectively replaced:
- **Senior backend engineer (~$6.5k–8k/month)**
- **QA automation engineer (~$4k/month)**

By encoding both roles into a deterministic system (`AGENTS.md`, `bin/verify`, `bin/contract_audit`).



## 1. The honest math behind the “5x” claim

Here is the clean comparison:

| Metric | Value |
| --- | ---: |
| Wider comparison group | 11 engineers |
| Team mix | 5 frontend, 3 AI, 2 mobile, 1 DevOps |
| Wider visible PR output | 1,000+ PRs |
| My solo backend output | 400+ PRs |
| My share of that visible volume | 40%+ |
| Average PRs per engineer in that group | 90.9 |
| My PR volume vs that average | 4.4x+ |

If you stop there, the story is already strong.

But PR count alone still understates the backend reality.

The work I carried was not just “more tickets” or “more commits.” It included:

- Bitbucket/GitHub pipelines and CD support
- API design and implementation
- database ownership
- migrations and seeds
- security and authorization
- test strategy
- release governance
- feature architecture
- cross-team contract translation
- platform continuity

So the useful business question is not:

> How did one engineer write this many PRs?

It is:

> How did one engineer remove this much uncertainty from shipping?

That is where AI becomes multiplicative. Not when it writes code faster, but when it operates inside a system that already knows what “correct” means.

---

## 2. The work hidden under the PR count

One of the reasons backend impact gets undervalued is that the visible product surface is usually owned by UI. The invisible surfaces are where backend concentration becomes easy to miss.

The repo scan changes that.

| Surface | Value |
| --- | ---: |
| Total tracked lines | 612,468 |
| Total tracked files | 2,878 |
| Named routes | 656 |
| `/api/v1` routes | 559 |
| Controllers | 162 |
| Blueprints | 203 |
| Models | 107 |
| Services | 97 |
| Policies | 28 |
| Migrations | 100 |
| Seed files | 48 |
| Requirement docs | 108 |
| Flow docs | 110 |
| PRDs | 86 |

Taken together, those requirement docs, Flow docs, and PRDs form **304 contract/document surfaces**.
That is not paperwork. That is the translation layer that lets backend, frontend, mobile, AI, product, and operations move against the same reality.

There are also specialized platform modules under that same umbrella:

| Module | Files | Lines |
| --- | ---: | ---: |
| `Service_1` | 91 | 21,927 |
| `Service_2` | 88 | 106,788 |
| `Service_3` | 96 | 62,227 |

That is why I do not describe the result as “AI helped me code faster.”

The real story is that I carried a large backend platform **and** built the operating system that made the platform safer to change.

There is another metric that matters a lot:

- `app/**` = **56,215 lines**
- `spec/**` = **125,772 lines**
- `doc/**` = **117,953 lines**

In other words, the surrounding **proof surface** and **translation surface** are much larger than the application code itself.

That is a huge clue about where the leverage came from.

The biggest gain was not generation.  
It was reducing ambiguity, rework, onboarding drag, review noise, and contract drift.

---

## 3. I stopped using AI as autocomplete

I think a lot of AI productivity conversations are shallow because they treat the model as the product.

That is backwards.

AI is not the product.  
**The operating model is the product.**

I like to describe my stack like this:

- `AGENTS.md` is the senior software engineer I can run on every task
- `bin/verify` is the QA automation engineer I can run in one command
- `bin/contract_audit` is the drift detector that goes beyond compiler-green

That framing matters.

I did not just ask AI to write code.

I asked AI to work inside:
- a contract system
- a planning workflow
- a verification gate
- a drift-prevention layer
- a documentation discipline
- a release model

That is a completely different level of leverage.

A principal engineer with AI but no operating system gets faster drafts.

A principal engineer with AI **and** an operating system gets safer throughput, shorter ramp time, and lower variance across the team.

That is what happened here.

---

## 4. `AGENTS.md`: turning principal judgment into a reusable senior engineer

The current `AGENTS.md` is not a prompt file. It is a **delivery runtime**.

The most revealing detail is that the tools kept evolving instead of freezing into docs nobody updates:

| Tool | March snapshot | Current attached source | Signal |
| --- | ---: | ---: | --- |
| `AGENTS.md` | 987 lines | 1,143 lines | the operating contract kept absorbing real-world lessons |
| `bin/verify` | 370 lines | 370 lines | the daily verification core stabilized early |
| `bin/contract_audit` | 452 lines | 540 lines | drift prevention kept getting sharper |

That is the opposite of a prompt blob.
It is a maintained operating system.

What makes `AGENTS.md` powerful is not file length. It is what the file externalizes.

### It defines authority before coding starts

`AGENTS.md` makes the source of truth explicit:

- process and workflow live in `AGENTS.md`
- feature behavior lives in `doc/requirements/**`
- Flow/PRD docs are derived artifacts
- requirements are read-only during implementation
- documentation updates happen only after verification is green

That one decision removes a huge amount of confusion for both humans and AI.

### It forces planning before implementation

The file creates hard no-code phases:

1. extract the contract
2. scan the repo
3. build a file-by-file plan
4. map requirements to specs
5. stop for confirmation
6. only then implement

That is senior-engineer behavior made explicit.

AI tends to jump into code too early.  
`AGENTS.md` blocks that.

### It turns “done” into something executable

This is the part I love most.

`AGENTS.md` does not stop at “follow best practices.” It defines:

- canonical success and error envelopes
- representational invariants
- safe defaults for required fields
- contract alignment checks
- verification order
- compliance audit rules
- documentation update timing
- final-output structure
- a never-list of things that must not ship

That is why I say I wrote my own senior software engineer.

Not because it sounds cool.  
Because it converts tacit judgment into repeatable constraints.

### It also solves prompt drift

One subtle but very important design choice is that the file distinguishes:

- **[NORMATIVE]** sections: actual rules
- **[ILLUSTRATIVE]** sections: examples and patterns

That stops examples from silently becoming law.

It also reduces one of the biggest AI failure modes: the model quoting guidance while violating the real rule.

### It preserves architecture under pressure

`AGENTS.md` locks down the parts that usually drift first:

- snake_case routes and JSON
- Blueprinter-only `data` payloads
- Pundit authorization
- Ransack filtering
- Kaminari pagination
- ISO8601 timestamps
- DB-agnostic queries only
- docs updated only after verification

This is what principal-level experience looks like in the AI era:

not just making better decisions personally,  
but **encoding which decisions must never become optional**.

---

## 5. `bin/verify`: the QA automation engineer I wanted next to me

A lot of teams say they care about quality, but their verification path is too slow, too manual, or too annoying to run constantly.

That means the real workflow becomes:
“verify when nervous.”

That is not a system.  
That is mood-based engineering.

`bin/verify` is the opposite.

At a glance, its structure looks simple:

```ruby
CHECK_PROFILES = {
  fast: %i[rubocop rspec swagger].freeze,
  full: %i[rubocop rspec brakeman audit swagger seeds].freeze
}.freeze
```

But the important part is not that there are two characters.  
It is that the script is **diff-aware**, **parallelized**, and **cheap enough to use every day**.

### What the fast character really does

The default path is intentionally practical:

- RuboCop
- RSpec
- Swagger generation only when API-relevant surfaces changed

That last point is not cosmetic.

The script checks changed files and auto-skips swagger if controllers, blueprints, routes, or API specs were untouched. That means routine work stays fast.

### What the full character adds

For heavier changes, `--full` adds:

- Brakeman
- bundle audit
- db seed replant

This split matters.

A daily verification loop must be cheap enough to become muscle memory.  
A full compliance loop must be available when the change deserves it.

That is exactly what this script gives you.

### It is optimized like build infrastructure, not like a shell alias

There are several details in the actual source that matter a lot:

#### 1) Parallel RSpec by default
The script runs `parallel_rspec` with **8 workers** by default, with a sequential mode available when needed.

#### 2) Fast character excludes heavy specs
Fast mode excludes specs tagged `:full_only`, which keeps the common path fast without deleting deeper coverage.

#### 3) Schema-aware parallel DB preparation
It fingerprints `db/schema.rb`, `db/structure.sql`, and migrations with SHA256 and only re-runs `rails parallel:prepare` when the schema actually changed.

That is not just convenient. That is exactly the kind of thing that keeps a fast path fast in real life.

#### 4) Locking and stamp files
The script uses a lock file and a stamp file so multiple runs do not do redundant work.

#### 5) Targeted ergonomics
It supports:
- `--only`
- `--fail-fast`
- `--workers`
- `--sequential`
- `--list`

That means the tool is not only strict. It is usable.

And usable tools are the only ones teams run every day.

### Why that mattered to output

The audit snapshot gives the result:

| Verification signal | Value |
| --- | ---: |
| Fast verification runtime | ~39s |
| Test examples | 7,445 |
| Failures | 0 |
| Pending | 19 |
| RuboCop offenses | 0 |

A **39-second** default path is the real productivity feature here.

That is short enough to run again.  
And again.  
And again.

That is what turns AI from “dangerous but fast” into “safe enough to accelerate.”

This is why I say `bin/verify` is the QA automation engineer I built for myself.

---

## 6. `bin/contract_audit`: going beyond compiler-green

This is the tool that most directly reflects how I think about engineering.

Compilers tell you whether code is valid syntax.  
Tests tell you whether known behavior still passes.  
But neither one guarantees that the implementation still matches:
- the contract
- the docs
- the route style
- the serializer discipline
- the portability constraints
- the team’s rules about how APIs are supposed to evolve

That is why I built `bin/contract_audit`.

Its top-level checks are explicit:

```ruby
CHECKS = {
  requirements_read_only: "Requirements docs remain untouched (doc/requirements/**)",
  swagger_generated_source: "Swagger YAML not edited alone (must be driven by rswag specs)",
  db_specific_sql: "No DB-specific SQL tokens introduced",
  route_style: "Route literals avoid kebab-case and trailing slashes",
  controller_manual_json: "No new ad-hoc render json hash payloads in controllers",
  docs_templates: "Changed Flow/PRD docs follow required section templates"
}.freeze
```

That list says a lot about the philosophy behind it.

This is not a generic lint script.  
It is a **drift-prevention script**.

### The most important design choice: it is legacy-safe

By default, `bin/contract_audit` does **not** try to police the whole repository every time.

Its default mode audits:
- changed files
- added lines
- untracked files

And only `--all` audits the full repository.

That is a brilliant practical design.

It means you can introduce strictness into a real, imperfect codebase without freezing delivery until every old inconsistency is cleaned up.

That is one of the most important lessons in this entire system:

> The best guardrail is not the strictest one.  
> It is the strict one people can actually adopt.

### It audits exactly the class of mistakes that usually slip through

The script blocks the kinds of drift that generate long-term chaos:

#### 1) Requirements are protected
`doc/requirements/**` stays read-only during normal implementation.

#### 2) Swagger stays generated, not hand-edited
If swagger YAML changes without integration spec changes, it fails.

#### 3) DB-specific SQL is blocked
It explicitly checks for drift like:
- `ILIKE`
- `IFNULL`
- `REGEXP`
- `RLIKE`
- JSON extraction operators

That matters because “small shortcuts” become portability debt fast.

#### 4) Route style stays clean
No kebab-case. No trailing slashes.

#### 5) Controllers cannot quietly hand-build JSON
The script looks for `render json: { ... }` in changed controllers and blocks ad-hoc response shapes outside the known envelope helpers.

#### 6) Docs must still follow the required structure
Changed Flow and PRD docs are checked against required heading sequences.

That is not just documentation hygiene.  
It is contract hygiene.

### It is strict without being stupid

There is another subtle design choice I really like.

The script auto-allows a requirement-doc handoff when:
- a new `Version ...` heading was added
- and no old version heading was removed

That means the audit can support a sane workflow where product/requirements evolved upstream and implementation is catching up.

Again: strict, but practical.

That combination is where good engineering systems live.

### This is what “drift-free” actually means

When I say I wanted a tool that validates more than compilation, this is what I mean.

I wanted something that checks whether the implementation still matches the intent.

Not just:
- “Does it run?”
- “Do tests pass?”

But also:
- “Did we preserve the contract?”
- “Did we keep route law?”
- “Did we avoid portability shortcuts?”
- “Did we keep the serializer boundary?”
- “Did docs stay structurally valid?”
- “Did anyone bypass the system in a hurry?”

That is requirement-green, not just compiler-green.

If I had to describe the stack in compiler terms, it would be this:

- `doc/requirements/**` is the source program for intent
- `AGENTS.md` is the language law
- `bin/verify` is the fast test runner
- `bin/contract_audit` is the semantic checker that blocks drift

And that is why a `6/6` audit pass matters so much more than a green test line by itself.

---

## 7. Why onboarding collapsed from months to about an hour

One of the strongest signals in this whole story had nothing to do with me.

A newly joined engineer came in, onboarded in about **an hour**, and started high-priority work immediately.

That reaction mattered to me more than a vanity metric, because it proved the system was doing real work outside my own output.

It also explains why even frontend engineers started wanting to pick up tasks in the backend flow.

Why did that happen?

Because the repo answers the questions that usually stay trapped in tribal knowledge:

- what is the source of truth?
- where does behavior live?
- what must not drift?
- what command proves the change is safe?
- what docs have to reflect the change?
- what does “done” mean here?

That is what makes onboarding fast.

People usually think onboarding is about reading architecture docs.

It is not.

Onboarding is about removing ambiguity from the first real task.

This system does that because:
- requirements define behavior
- `AGENTS.md` defines execution
- `bin/verify` defines proof
- `bin/contract_audit` defines drift boundaries
- Flow docs define implementation traceability
- PRDs define product context

The result is not just faster ramp.  
It is **faster trust**.

And trust is what lets new engineers start shipping instead of shadowing.

---

## 8. Why this is language-agnostic

Yes, the current implementation is Rails-heavy.

It uses:
- Blueprinter
- Pundit
- Ransack
- Kaminari
- RSpec
- RuboCop
- Brakeman
- rswag

But the underlying model is not Ruby-specific at all.

The reusable pattern is this:

1. requirements are explicit
2. implementation follows contract
3. verification is one command
4. drift is checked separately from tests
5. docs are derived from verified behavior
6. onboarding happens against the system, not folklore

That ports cleanly.

### TypeScript / Node
- requirements: TypeScript interfaces, Zod, OpenAPI
- verify: ESLint, Jest/Vitest, OpenAPI generation, security checks
- audit: route naming, response-shape discipline, docs templates, SQL portability

### Python
- requirements: Pydantic models, OpenAPI, JSON Schema
- verify: Ruff, pytest, mypy, security checks
- audit: serializer boundaries, route shape, docs structure, query portability

### Go
- requirements: structs, OpenAPI, protobuf/JSON schema
- verify: `go test`, lint, vuln checks, generated spec validation
- audit: handler response discipline, route law, portability, docs templates

The language-specific parts are adapters.

The actual product is the operating model.

That matters because this is not really a “Rails productivity” story.

It is a **principal-engineering systems** story.

---

## 9. The business math is stronger than the PR math

Raw PR throughput already makes the case:
- average engineer in the 11-person comparison group: **90.9 PRs**
- my solo output: **400+ PRs**
- ratio: **4.4x+**

But the business value gets stronger when you add the surrounding system.

### Tooling efficiency

The provided context says:
- my tooling cost: **$200/month**
- comparison-side tooling cost: **$4,000+/month**

That is at least a **$3,800/month** delta.

Over **11 months**, that is at least **$41,800** in tooling-cost difference alone.

### Ramp-time compression

I am deliberately conservative here, because this part is business translation rather than a repo metric.

If your normal onboarding for meaningful contribution is **4 to 8 weeks**, and this system gets a new engineer into high-priority work in about **1 hour**, then you are recovering roughly **159 to 319 engineer-hours** per engineer.

That is not a tiny productivity win.  
That is a planning-level advantage.

### Safe speed beats raw speed

The most important thing I did **not** want was fake velocity.

Fast delivery only matters if it is safe enough to merge without fear.

The reason the speed here matters is that it sits on top of:
- **7,445 examples**
- **0 failures**
- **6/6 audit checks passed**
- **39s** fast verification
- explicit documentation and traceability

That is what businesses actually buy when they say they want “10x engineering.”

They do not want more code.  
They want more **safe change per unit of time**.

---

## 10. What I think people still miss

After re-reading all of the attached material, including the actual `bin/verify` and `bin/contract_audit` sources, I think there are four especially important ideas hiding in this story.

### 1) The best systems are strict and ergonomic at the same time
Fast character vs full character.  
Changed-lines mode vs `--all`.  
`--only`.  
`--fail-fast`.  
Schema-aware prepare.  
Swagger auto-skip.

That is not polish. That is adoption strategy.

### 2) “Legacy-safe” is a force multiplier
`bin/contract_audit` does not demand a perfect repo before it becomes useful. It prevents **new drift** first.

That is how serious systems actually get adopted.

### 3) Proof is part of the product
When `spec/**` and `doc/**` together dwarf `app/**`, that is not overhead. That is the mechanism that lets a platform change quickly without dissolving into review theater.

### 4) Principal engineering in the AI era is about externalized judgment
The old model was:
- senior engineers make better decisions in their head

The new model is:
- principal engineers turn those decisions into reusable infrastructure

That is the real upgrade.

Experience matters more, not less, once AI enters the loop.

But experience is most valuable when it becomes system design.

---

## 11. Closing

I do not think the most important AI question is:

> Can the model write code?

I think the real question is:

> Can the engineering system make correctness cheap enough that the model can safely accelerate it?

That is the difference between novelty and leverage.

In my case, one principal backend engineer shipped **400+ PRs**, carried **40%+** of the visible PR volume of an **11-engineer** comparison group, validated daily work in about **39 seconds**, passed **7,445 tests with 0 failures**, passed **6/6 contract-audit checks**, reduced onboarding to about **an hour**, and did it with **20x+ lower tooling cost**.

I did not get there by asking AI to be smarter.

I got there by building a system where:
- requirements are explicit
- execution is governed
- verification is fast
- drift is blocked
- docs are derived
- onboarding is compressed
- and the only truly acceptable final response becomes:

> all good — merge PR

That is what 16 years of experience bought me in the AI era.

Not better autocomplete.  
A better engineering operating system.

---

## Short shareable version

One principal backend engineer shipped **400+ PRs solo** while the wider **11-engineer** org shipped **1,000+**, which is **40%+** of that visible output and **4.4x+** the average engineer PR volume in the comparison. The real multiplier came from turning senior judgment into a reusable AI operating system: `AGENTS.md` for execution law, `bin/verify` for fast proof, `bin/contract_audit` for zero-drift guardrails, and a codebase that lets new engineers start high-priority work in about **an hour**, not months.
