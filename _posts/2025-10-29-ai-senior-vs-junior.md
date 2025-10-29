---
layout: post
title: "AI Will Make Your Team Slower—Unless a Senior Engineer Drives It"
date: 2025-10-29
author: Max Lukin
tags: [ai, software-engineering, rails, blueprinter, rspec, codex, devex]
description: A practical control loop (with code) for turning Codex‑style assistants into force multipliers—and why experience is non‑negotiable.
categories: [engineering, rails, AI]
---

> **TL;DR**
>
> - **AI without strong engineering judgment** amplifies bad practices, bloats scope, and quietly ships risk; the result is **worse code, slower delivery, more spend**.
> - **AI paired with an experienced engineer**—with explicit guardrails, contracts, and verification gates—becomes an **execution accelerator** that still preserves maintainability and safety.

I’ve spent ~15 years building software at scale—**Staff Software Engineer at Apple**, **Senior Software Engineer** in the world’s largest medical corporation, and **Tech Lead** delivering high‑end solutions for the **Metropolitan Police (UK)**. That background is why AI (e.g., Codex‑style assistants) is a net positive in my hands and a net negative in many others. The difference isn’t the model—it’s **process control**.

Below is the practical operating model I use to make AI extremely efficient, with concrete Rails examples and checklists you can paste into your own repo.

---

## The paradox: AI helps the best and hurts the rest

AI accelerates whatever process it is given. If the process is ad‑hoc, pattern‑happy, and test‑light, AI will generate more of that—faster. If the process is **Rails‑way + KISS, contracts-first, test‑gated, and security‑checked**, AI becomes a force multiplier.

My teams encode these guardrails in two living documents:

- A **Pragmatic Engineering Guide**: Rails‑way first; **Blueprinter as single JSON source**; predictable envelopes/status codes; DRY only when duplication hurts; **DB constraints first**; Pundit/Kaminari/Ransack; N+1 prevention; deterministic tests; and a tight “Definition of Done.” fileciteturn0file0
- An **Agent Checklist** for contributors (human or AI): **verification gates** must pass (`rubocop`, `rspec`, `brakeman`, `bundle audit`, `rswag`), constrained edit scope, JSON envelope rules, deny‑by‑default authorization, minimal diffs, and a required **CHECKS** section in the result. fileciteturn0file1

These two artifacts are how I “steer the model.”

---

## The control loop that turns AI into a multiplier

Think of this as **how an experienced engineer drives**.

1) **State intent, not tasks**
Describe the behavior, constraints, and acceptance criteria. Example: “Build `/api/v1/items` list & create with Blueprinter, Pundit, Kaminari; return `{ data, meta }` on index, and envelope on create; ISO8601 timestamps; preload to avoid N+1.” fileciteturn0file0

2) **Pin contracts up front**
- **Envelope**: `{ data: [...], meta: { page, per_page, total_pages, total_count } }` for lists; success envelopes for mutations; `422 :unprocessable_content` for validation errors via centralized renderer. fileciteturn0file0
- **JSON source**: Blueprinter only (controllers never hand‑craft response hashes). fileciteturn0file0

3) **Set repo rules as the model’s “laws”**
Re-surface KISS, Rails‑way, predictable status codes, Pundit deny‑by‑default, Ransack for search, Kaminari for pagination, **UTC internally / ISO8601 in JSON**, and “no new runtime deps without justification.” fileciteturn0file1

4) **Ask AI for the minimal diff consistent with the contract**
Small, scoped changes reduce blast radius and review time. The checklist mandates this. fileciteturn0file1

5) **Gate with verification** (non‑negotiable)
Run—and expect AI to fix until green:
`bundle exec rubocop` • `bundle exec rspec` • `bundle exec brakeman -q -w2` • `bundle exec bundle audit check --update` • `bundle exec rails rswag:specs:swaggerize`. fileciteturn0file1

6) **Require tests that assert contracts**
Deterministic request specs validating envelope shape, error shape, and status codes; serializers and policy specs; freeze time; stub external IO. fileciteturn0file0

7) **Enforce data integrity at the DB**
Not‑nulls, unique indexes, FKs; seed representative data with new schema so environments stay usable. fileciteturn0file0

8) **Document the change**
Update `CHANGELOG.md` and, for flows/PRDs, follow the repo’s exact templates **after** verification passes. fileciteturn0file0

This loop—intent → contracts → minimal diff → verification—keeps AI on the rails (pun intended).

---

## A concrete example (Rails): “bad AI” vs “senior‑driven AI”

**The task**: Ship `index` and `create` for `Item`.

### What the *inexperienced+AI* path often produces (anti‑pattern)

```ruby
# app/controllers/api/v1/items_controller.rb (problematic)
def index
  items = Item.all
  render json: items # ❌ raw AR to JSON, no envelope, N+1 risk
end

def create
  item = Item.create!(item_params)
  render json: { success: true, item: item }, status: 200 # ❌ wrong envelope, wrong status, handcrafted JSON
end
```

Typical issues:
- No pagination or preload (N+1); status codes wrong; camelCase sneaks in; **controllers become serializers**; no Pundit; no predictable error shape; no tests to lock contracts. This is how AI **makes work worse**—it’s fast, but it’s **fast wrong**.

### What the *senior‑driven+AI* path looks like

```ruby
# app/controllers/api/v1/items_controller.rb
class Api::V1::ItemsController < ApplicationController
  before_action :authenticate_user!
  after_action :verify_authorized

  def index
    items = policy_scope(Item)
              .includes(:owner)                 # avoid N+1
              .order(created_at: :desc)
              .page(params[:page]).per(params[:per_page] || 20)

    authorize Item

    render_collection_envelope(
      collection: items,
      blueprint: ItemBlueprint
    )
  end

  def create
    item = current_user.items.new(item_params)
    authorize item

    if item.save
      render_success_envelope(
        message: "Item created successfully",
        resource: item,
        blueprint: ItemBlueprint,
        status: :created
      )
    else
      render_validation_errors(item)           # 422 with { error, errors }
    end
  end

  private

  def item_params
    params.require(:item).permit(
      :title, :description, :price_cents, :status,
      files_attributes:  [:id, :doc_type, :file, :_destroy],
      images_attributes: [:id, :alt, :file, :position, :_destroy]
    )
  end
end
```

- **Blueprinter is the only JSON source;** controllers build the envelope.
- **Predictable envelopes & status codes**; `422 :unprocessable_content` via centralized handler.
- **Pundit** for authorization, **Kaminari** for pagination, **includes** for N+1, **snake_case** params.
All of this is spelled out in the **Pragmatic Engineering Guide** and **Agents checklist** we hand to AI. fileciteturn0file0 fileciteturn0file1

> **Why this matters:** When AI is forced to work inside these constraints, you get **consistent, testable endpoints** that match the client contract and survive refactors.

---

## Verification: the non‑negotiable gates

Before a patch is even considered, these must pass and be **reported back**:

1. `bundle exec rubocop`
2. `bundle exec rspec`
3. `bundle exec brakeman -q -w2`
4. `bundle exec bundle audit check --update`
5. `bundle exec rails rswag:specs:swaggerize`

In my repos, contributors (including AI) must include a **CHECKS** section listing each command and the final exit code. If any fail, the patch is rejected. This single habit is why AI becomes safe and efficient. fileciteturn0file1

---

## Prompt patterns that keep AI aligned (steal these)

**“System prompt” for Codex in this repo (abridged):**

- Follow **Rails‑way + KISS**; add services only when complexity demands.
- **Blueprinter only** for `data`; controllers construct `{ success, message, data, meta }`.
- Status codes: index `200`, create `201`, update `200`, destroy `200`, validation errors `422`.
- Use **Kaminari**, **Ransack**, **Pundit (deny‑by‑default)**; **UTC** internally; **ISO8601** in JSON.
- Avoid N+1 (`includes`/`preload`).
- DB constraints first (NOT NULL, FKs, unique indexes).
- Small, scoped diffs; no new runtime deps without explicit note.
- Output format must include: **RATIONALE** (3–5 bullets) and **CHECKS** (show commands + exit codes). fileciteturn0file0 fileciteturn0file1

**Task prompt (example):**

> Implement `Api::V1::ItemsController#index,#create` per repo rules.
> - Contracts: list returns `{ data, meta }` with pagination; create returns success envelope with `201`.
> - Serialization with `ItemBlueprint` only.
> - Policy: `ItemPolicy` must authorize `index, create`.
> - Tests: request specs for both success and failure; validation errors return `422` with `{ error, errors }`.
> - Avoid N+1, preload `owner`.
> - Return minimal diff and the **CHECKS** section.

---

## Failure modes when experience is missing

1. **Speculative abstractions**: junior+AI introduces services/commands for simple CRUD because “it looks enterprise.” You inherit ceremony, not clarity. The guide explicitly says **KISS** and **only** add layers when complexity demands it. fileciteturn0file0
2. **Handcrafted JSON**: inconsistent shapes, hard‑to‑change clients. Blueprinter prevents this. fileciteturn0file0
3. **Status code drift**: `200` everywhere. Your monitoring and client error handling become noise. The envelope rules fix this. fileciteturn0file0
4. **Security blind spots**: no Pundit, no authZ tests, optimistic assumptions; Brakeman never run. The agent checklist enforces both. fileciteturn0file1
5. **Performance foot‑guns**: N+1 queries in hot paths; no pagination; no indexes. The guide mandates preload + DB constraints first. fileciteturn0file0
6. **Change drift**: no `CHANGELOG`, no flow/PRD docs; institutional memory evaporates. The guide defines exact doc locations/templates. fileciteturn0file0

When you “just use AI,” these anti‑patterns compound. You don’t net out at zero—you go **backwards**.

---

## Why an experienced engineer + AI is the *only* productive path

- **Context compression:** Seniors encode the domain into **contracts**, not just code. AI needs those contracts to be useful.
- **Risk management:** Seniors pick the right guardrails—authZ, envelopes, data constraints—so acceleration doesn’t equal breach or outage.
- **Taste for trade‑offs:** Knowing when not to abstract, when to index, when to paginate, when to split responsibilities—that’s the difference between 1× and 10× output.
- **Scientific feedback loop:** Seniors run the verification gates and **close the loop**; juniors often skip or misinterpret failures. fileciteturn0file1

---

## A 30‑minute “AI sprint” I run with teams

1. **Frame** (5 min): write behavior, contracts, and acceptance tests.
2. **Generate** (10 min): ask AI for a minimal diff aligned to the repo rules.
3. **Verify** (10 min): run the five checks; fix or ask AI to fix until green.
4. **Document** (5 min): `CHANGELOG` and (if applicable) flow/PRD stubs. fileciteturn0file0

Teams ship **fewer lines**, **fewer bugs**, and **more predictably**.

---

## Action checklist (paste into your project)

- [ ] Create/refresh a **Pragmatic Engineering Guide** with: Rails‑way + KISS, Blueprinter, envelopes/status codes, Pundit/Kaminari/Ransack, DB constraints, deterministic tests, DoD. fileciteturn0file0
- [ ] Adopt an **Agent Checklist**: verification gates + edit scope + minimal diffs + **CHECKS** reporting. fileciteturn0file1
- [ ] Put **contract tests** in place (request specs asserting envelope shapes & codes). fileciteturn0file0
- [ ] Make **N+1 prevention** and **authZ** part of code review. fileciteturn0file0
- [ ] Require **CHANGELOG** updates and flow/PRD docs post‑verification. fileciteturn0file0

---

## Closing

AI isn’t a senior engineer. **You are.**
With explicit contracts, repo‑level laws, and non‑negotiable verification, tools like Codex become the best pair you’ve ever had. Without that experience and control, the same tool will quietly undermine your codebase, your budget, and your delivery.

**Choose the driver.**
