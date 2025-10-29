---
layout: post
title: "AI Will Make Your Team Slower—Unless a Senior Engineer Drives It"
date: 2025-10-29
author: Max Lukin
tags: [ai, software-engineering, rails, blueprinter, rspec, codex, devex]
categories: [engineering, rails, AI]
description: A practical control loop (with code) for turning Codex-style assistants into force multipliers—and why experience is non-negotiable.
---

> **TL;DR**
>
> - **AI without strong engineering judgment** amplifies bad practices, bloats scope, and quietly ships risk; the result is **worse code, slower delivery, more spend**.
> - **AI paired with an experienced engineer**—with explicit guardrails, contracts, and verification gates—becomes an **execution accelerator** that still preserves maintainability and safety.

I’ve spent ~15 years building software at scale—**Staff Software Engineer at Apple**, **Senior Software Engineer** in the world’s largest medical corporation, and **Tech Lead** delivering high-end solutions for the **Metropolitan Police (UK)**. That background is why AI (e.g., Codex-style assistants) is a net positive in my hands and a net negative in many others. The difference isn’t the model—it’s **process control**.

Below is the practical operating model I use to make AI extremely efficient, with concrete Rails examples and checklists you can paste into your own repo.

---

## The paradox: AI helps the best and hurts the rest

AI accelerates whatever process it is given. If the process is ad-hoc, pattern-happy, and test-light, AI will generate more of that—faster. If the process is **Rails-way + KISS, contracts-first, test-gated, and security-checked**, AI becomes a force multiplier.

My teams encode these guardrails in two living documents:

- A **Pragmatic Engineering Guide**: Rails-way first; **Blueprinter as single JSON source**; predictable envelopes/status codes; DRY only when duplication hurts; **DB constraints first**; Pundit/Kaminari/Ransack; N+1 prevention; deterministic tests; and a tight “Definition of Done.”
- An **Agent Checklist** for contributors (human or AI): **verification gates** must pass (`rubocop`, `rspec`, `brakeman`, `bundle audit`, `rswag`), constrained edit scope, JSON envelope rules, deny-by-default authorization, minimal diffs, and a required **CHECKS** section in the result.

These two artifacts are how I “steer the model.”

---

## The control loop that turns AI into a multiplier

Think of this as **how an experienced engineer drives**.

1. **State intent, not tasks**
   Describe the behavior, constraints, and acceptance criteria. Example: “Build `/api/v1/items` list & create with Blueprinter, Pundit, Kaminari; return `{ data, meta }` on index, and envelope on create; ISO8601 timestamps; preload to avoid N+1.”

2. **Pin contracts up front**
   - **Envelope**: `{ data: [...], meta: { page, per_page, total_pages, total_count } }` for lists; success envelopes for mutations; `422 :unprocessable_content` for validation errors via centralized renderer.
   - **JSON source**: Blueprinter only (controllers never hand-craft response hashes).

3. **Set repo rules as the model’s “laws”**
   Re-surface KISS, Rails-way, predictable status codes, Pundit deny-by-default, Ransack for search, Kaminari for pagination, **UTC internally / ISO8601 in JSON**, and “no new runtime deps without justification.”

4. **Ask AI for the minimal diff consistent with the contract**
   Small, scoped changes reduce blast radius and review time.

5. **Gate with verification** (non-negotiable)
   Run—and expect AI to fix until green:
   `bundle exec rubocop` • `bundle exec rspec` • `bundle exec brakeman -q -w2` • `bundle exec bundle audit check --update` • `bundle exec rails rswag:specs:swaggerize`.

6. **Require tests that assert contracts**
   Deterministic request specs validating envelope shape, error shape, and status codes; serializers and policy specs; freeze time; stub external IO.

7. **Enforce data integrity at the DB**
   Not-nulls, unique indexes, FKs; seed representative data with new schema so environments stay usable.

8. **Document the change**
   Update `CHANGELOG.md` and, for flows/PRDs, follow the repo’s exact templates **after** verification passes.

This loop—intent → contracts → minimal diff → verification—keeps AI on the rails (pun intended).

---

## A concrete example (Rails): “bad AI” vs “senior-driven AI”

**The task**: Ship `index` and `create` for `Item`.

### What the *inexperienced+AI* path often produces (anti-pattern)

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
- No pagination or preload (N+1)
- Wrong status codes
- Inconsistent JSON shapes
- No Pundit
- No tests or contracts

This is how AI **makes work worse**—it’s fast, but it’s **fast wrong**.

### What the *senior-driven+AI* path looks like

```ruby
# app/controllers/api/v1/items_controller.rb
class Api::V1::ItemsController < ApplicationController
  before_action :authenticate_user!
  after_action :verify_authorized

  def index
    items = policy_scope(Item)
              .includes(:owner)
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
      render_validation_errors(item)
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

**Key differences:**
- Uses **Blueprinter** for consistent JSON.
- Proper **status codes** and envelopes.
- **Pundit**, **Kaminari**, and **includes** for clean, performant code.
- Predictable, contract-driven results.

---

## Verification gates

Before merging, all must pass:

```
bundle exec rubocop
bundle exec rspec
bundle exec brakeman -q -w2
bundle exec bundle audit check --update
bundle exec rails rswag:specs:swaggerize
```

Any failure means the patch is rejected. This keeps AI output safe and consistent.

---

## Why experience is everything

- **Context compression**: Seniors encode the domain into contracts, not code.
- **Risk management**: Experience means setting the right guardrails.
- **Trade-offs**: Knowing when not to abstract.
- **Feedback loops**: Seniors run and fix verification gates—juniors skip them.

---

## Final thoughts

AI isn’t a senior engineer. **You are.**
With explicit contracts, repo-level laws, and non-negotiable verification, tools like Codex become the best pair you’ve ever had. Without that control, they quietly degrade your codebase.

**Choose the driver.**
