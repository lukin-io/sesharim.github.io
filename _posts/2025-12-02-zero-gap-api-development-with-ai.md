---
layout: post
title: "Zero-Gap API Development: A Contract-First Framework for AI-Assisted Rails Engineering"
date: 2025-12-02
author: Max Lukin
tags: [ai, software-engineering, rails, api, blueprinter, rspec, cursor, contracts, documentation]
categories: [engineering, rails, AI, best-practices]
description: "A complete framework for shipping regression-free Rails APIs with AI assistants—combining contract-first development, systematic verification, and gap-free documentation."
---

> **TL;DR**
>
> - **Contract-first development** with TypeScript interfaces as the single source of truth eliminates ambiguity and prevents frontend/backend drift.
> - **Systematic verification gates** catch implementation gaps before they ship—not after.
> - **Discrepancy classification** (`[IMPL]` vs `[DOC]`) ensures you fix what's broken and flag what's misaligned.
> - **Mandatory dual documentation** (Flow + PRD) creates institutional memory that survives team changes.

This post is the evolution of our previous guides on [consolidating Rails contribution standards](/2025-09-09-consolidating-rails-api-guide-for-cursor-ide) and [senior-driven AI development](/2025-10-29-ai-senior-vs-junior). After shipping dozens of endpoints with zero regressions, we've refined the process into a complete framework.

---

## The Problem: Death by a Thousand Gaps

Every API project eventually faces the same failure modes:

1. **Contract drift**: Backend returns `userId`, frontend expects `user_id`
2. **Silent regressions**: v1.1 breaks v1.0 behaviors nobody tested
3. **Incomplete implementations**: 8 of 10 required fields shipped, 2 "forgot"
4. **Documentation rot**: Flow docs describe behavior from 3 sprints ago
5. **AI amplification**: LLMs generate plausible-looking code that fails edge cases

The root cause isn't carelessness—it's **missing systematic verification**. Humans (and AIs) make errors. Systems catch them.

---

## The Solution: Three-Layer Architecture

Our framework operates on three layers, each with a specific purpose:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: REQUIREMENT_DOC (doc/requirements/**)         │
│  - TypeScript interfaces = canonical truth              │
│  - Read-only, never modified by implementers            │
│  - Versioned (v1.0, v1.1, v1.2...)                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Implementation (app/**, spec/**)              │
│  - Must satisfy ALL versions cumulatively               │
│  - Blueprinter for JSON, Pundit for auth                │
│  - Contract Compliance Verification before merge        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Documentation (doc/flow/**, doc/prd/**)       │
│  - Generated AFTER verification passes                  │
│  - Reflects actual implementation, not intent           │
│  - Version history preserved, never overwritten         │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: Contract-First Development

The REQUIREMENT_DOC is the **single source of truth**. It contains TypeScript interfaces that define the exact response shape:

```typescript
// doc/requirements/PROFILE_CARD.md
interface ProfileCard {
  id: number;                    // required
  username: string;              // required
  avatar_url: string | null;     // optional
  skills: Skill[];               // required, min 0 items
  availability: {
    status: 'now' | 'two_weeks' | 'offer' | 'na';
    updated_at: string;          // ISO8601
  };
}
```

**The rules are simple:**

1. Every field in the interface **must** exist in your Blueprint
2. Required fields **never** return `null`—use safe defaults
3. No extra fields beyond what's documented
4. Version changes are **cumulative** unless explicitly marked as breaking

### Safe Defaults Strategy

When database data is sparse, required fields still must satisfy the contract:

```ruby
# app/blueprints/profile_card_blueprint.rb
class ProfileCardBlueprint < Blueprinter::Base
  identifier :id

  field :username do |profile|
    profile.username.presence || ""  # String → empty string
  end

  field :skills do |profile|
    profile.skills.presence || []    # Array → empty array
  end

  field :availability do |profile|
    {
      status: profile.availability_status || "na",  # Enum → default value
      updated_at: (profile.availability_updated_at || Time.current).iso8601
    }
  end
end
```

**Safe defaults by type:**

| Type | Default |
|------|---------|
| String (required) | `""` (empty string) |
| Number (required) | `0` or minimum valid value |
| Boolean (required) | `false` |
| Array (required) | `[]` (empty array) |
| Object (required) | Minimal valid object with nested defaults |
| Timestamp | `Time.current.iso8601` |

---

## Layer 2: Implementation with Verification Gates

### The Verification Checklist

Every implementation must pass these gates **in order**:

```bash
# 1. Code quality
bundle exec rubocop

# 2. Test suite (establishes baseline, catches regressions)
bundle exec rspec

# 3. Security scan
bundle exec brakeman -q -w2

# 4. Dependency audit
bundle exec bundle audit check --update

# 5. API documentation generation
bundle exec rails rswag:specs:swaggerize
```

**If any gate fails, stop and fix.** Do not proceed to documentation.

### Contract Compliance Verification (NO GAPS)

After all tests pass, systematically audit against REQUIREMENT_DOC:

**1. Endpoints Audit**
- [ ] Every path in REQUIREMENT_DOC exists in routes
- [ ] HTTP methods match (GET/POST/PATCH/DELETE)
- [ ] URL and query params match documented names
- [ ] Auth requirements match (public vs authenticated, role restrictions)

**2. Response Shape Audit**
- [ ] Every field in TypeScript interface exists in Blueprint
- [ ] No extra fields emitted beyond REQUIREMENT_DOC
- [ ] Required fields never return null/nil
- [ ] Nested objects match documented structure exactly

**3. Validation & Error Audit**
- [ ] All documented validations implemented
- [ ] Error responses use correct status codes:
  - `422` → Validation errors (`:unprocessable_content`)
  - `400` → Bad request / malformed params
  - `401` → Unauthorized (missing/invalid auth)
  - `403` → Forbidden (authenticated but not permitted)
  - `404` → Not found

**4. Version Compliance Audit**
- [ ] v1.0 requirements still satisfied
- [ ] v1.1+ additions implemented correctly
- [ ] Breaking changes only where REQUIREMENT_DOC explicitly declares

### Discrepancy Classification

When gaps are found, classify them correctly:

**Type A: Implementation Issues** — Your code doesn't match REQUIREMENT_DOC

```
[IMPL] GET /profiles/:id - [EXPECTED: returns avatar_url] vs [ACTUAL: field missing from Blueprint]
[IMPL] POST /users - [EXPECTED: 422 for invalid email] vs [ACTUAL: returns 400]
```

→ **Fix ALL before proceeding.** Re-run verification after fixes.

**Type B: Requirement Doc Discrepancies** — REQUIREMENT_DOC doesn't match existing DB/model

```
[DOC] visible_within enum - [DOC: 'local'|'state'|'country'] vs [DB: '5'|'10'|'25'|'50' miles]
[DOC] Availability.status - [DOC: 'available'|'unavailable'] vs [Model: 'now'|'two_weeks'|'offer'|'na']
```

→ **Do NOT modify `doc/requirements/**`** (read-only).
→ Blueprint returns actual DB values (correct behavior).
→ Flag for product/doc owner to reconcile.

---

## Layer 3: Mandatory Documentation

**Both Flow docs and PRDs are mandatory for every task.** Generate only **after** verification passes.

### Flow Doc Template (WEB-286 structure)

```markdown
# TASK_ID — Feature Name

## Metadata
- **Task:** TASK_ID
- **Status:** Implemented
- **Version:** 1.0

## Table of Contents
1. General Description
2. Validation Use Cases
3. Pundit Policy
4. Implementation Notes
5. Status Codes
6. Flow
7. Responsible Files

## General Description
[What the feature does, who can access it]

## Validation Use Cases
| Field | Rule | Error Code |
|-------|------|------------|
| email | required, format | 422 |

## Pundit Policy
- `index?` → authenticated users
- `create?` → owner only

## Status Codes
| Code | Condition |
|------|-----------|
| 200 | Success |
| 422 | Validation failed |
| 403 | Not authorized |

## Responsible Files
- `app/controllers/api/v1/items_controller.rb`
- `app/blueprints/item_blueprint.rb`
- `app/policies/item_policy.rb`
- `spec/requests/api/v1/items_spec.rb`
```

### PRD Template (WEB-240 structure)

```markdown
# TASK_ID — Feature Name PRD

## Problem Statement
[What problem does this solve?]

## Goals
- [Goal 1]
- [Goal 2]

## Scope
### In Scope
- [Feature A]

### Out of Scope
- [Feature B]

## User Stories
- As a [role], I want to [action] so that [benefit]

## Technical Considerations
- [Database changes]
- [API contract]

## Metrics
- [How will success be measured?]

## Rollout Plan
- [Deployment strategy]

## Dependencies
- [External services, gems, etc.]
```

### Version History

Both docs must maintain explicit version history:

```markdown
## Version History

### Version 1.1 (2025-12-02)
- Added `avatar_url` field to response
- Changed `status` enum values

### Version 1.0 (2025-11-15)
- Initial implementation
```

**Never overwrite—always append.**

---

## The Complete Prompt Template

When using AI assistants, use this universal prompt:

```text
Task: TASK_ID – FEATURE_LABEL (Ruby on Rails API)

Context:
- Requirements (single source of truth): REQUIREMENT_DOC
- Flow doc: FLOW_DOC
- PRD doc: PRD_DOC

Global constraints:
- Read and follow AGENTS.md and GUIDE.md before changing anything
- JSON via Blueprinter only; controllers handle envelopes
- Never bypass serializers, never use camelCase keys

Core contract rules:
- TypeScript interfaces in REQUIREMENT_DOC are the ONLY truth
- Required fields never return null (use safe defaults)
- All versions (v1.0, v1.1, ...) satisfied cumulatively

Implementation:
- Upgrade existing code to satisfy ALL versions in REQUIREMENT_DOC
- Do NOT remove behaviors that already match the contract
- Build JSON via Blueprinter with exact field sets

Verification (all must pass):
1. bundle exec rubocop
2. bundle exec rspec
3. bundle exec brakeman -q -w2
4. bundle exec bundle audit check --update
5. bundle exec rails rswag:specs:swaggerize

Contract Compliance (NO GAPS):
- Audit: endpoints, response shape, validations, versions
- Classify discrepancies: [IMPL] = fix code, [DOC] = flag for doc owner

Final documentation (AFTER verification):
- Generate/update FLOW_DOC and PRD_DOC
- Include version history
```

---

## Controller Patterns That Work

### Index with Pagination

```ruby
def index
  items = Item.includes(:owner)
              .order(created_at: :desc)
              .page(params[:page]).per(params[:per_page] || 20)

  render_collection_envelope(
    collection: items,
    blueprint: ItemBlueprint
  )
end
```

Response:
```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total_pages": 5,
    "total_count": 100
  }
}
```

### Create with Validation

```ruby
def create
  item = current_user.items.new(item_params)

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
```

Success (201):
```json
{
  "success": true,
  "message": "Item created successfully",
  "data": { ... }
}
```

Validation Error (422):
```json
{
  "error": "Title can't be blank and Price must be greater than 0",
  "errors": {
    "title": ["can't be blank"],
    "price": ["must be greater than 0"]
  }
}
```

---

## Spec Coverage Requirements

Every implementation ships with:

- [ ] **Request spec** for each endpoint (success + ALL documented error cases)
- [ ] **RSwag integration spec** for Swagger generation
- [ ] **Policy spec** for authorization rules
- [ ] **Model spec** for validations/associations/scopes
- [ ] **Blueprint spec** when output shape is complex

### Regression Prevention

```ruby
# Before modifying existing code:
# 1. Run existing specs → establish baseline (all green)
# 2. Make changes
# 3. Run specs again → ALL prior specs must still pass
# 4. If any fail, treat as regression and fix before proceeding
```

---

## Why This Works

| Without Framework | With Framework |
|-------------------|----------------|
| "It works on my machine" | Verification gates catch issues |
| Frontend discovers missing fields | Contract compliance audit prevents gaps |
| v1.1 breaks v1.0 | Cumulative version compliance |
| Docs are always stale | Docs generated from actual implementation |
| AI generates plausible bugs | AI follows explicit contracts |

---

## The Efficiency Multiplier

This framework turns AI from a liability into an accelerator:

1. **Fewer review cycles** — Envelopes, pagination, and auth are consistent from the start
2. **Predictable output** — AI synthesizes code that matches contracts
3. **Lower context cost** — One authoritative source means less ambiguity
4. **Safer by default** — Verification gates catch errors before merge
5. **Institutional memory** — Documentation survives team changes

---

## Quick Reference

**Response Envelopes:**
- List: `{ data: [...], meta: { page, per_page, total_pages, total_count } }`
- Success: `{ success: true, message: "...", data: {...} }`
- Error: `{ error: "...", errors: {...} }`

**Status Codes:**
- `200` → OK (read, update, delete)
- `201` → Created
- `400` → Bad request
- `401` → Unauthorized
- `403` → Forbidden
- `404` → Not found
- `422` → Validation failed

**Discrepancy Tags:**
- `[IMPL]` → Fix your code
- `[DOC]` → Flag for doc owner

**Safe Defaults:**
- String → `""`
- Number → `0`
- Boolean → `false`
- Array → `[]`
- Timestamp → `Time.current.iso8601`

---

## Conclusion

Zero-gap development isn't about perfection—it's about **systematic verification**. By treating TypeScript interfaces as contracts, running verification gates religiously, and generating documentation from working code, you eliminate entire categories of bugs.

AI amplifies whatever process you give it. Give it contracts, gates, and verification—and it becomes the best pair programmer you've ever had.

**The framework is the force multiplier. Experience is choosing to use it.**

