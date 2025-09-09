---
layout: post
title: "One Source of Truth: Consolidating Our Rails API Contribution Guide for Cursor IDE"
date: 2025-09-09 09:00:00
author: Max Lukin
description: "How we merged Rails, RSpec, and Ruby rules into a single, enforceable guide—and how to attach it to Cursor prompts for consistent, efficient results."
categories: [engineering, rails, api, cursor]
tags: [Ruby on Rails, API, Blueprinter, Pundit, Kaminari, Ransack, Cursor, RSpec, Jekyll]
---

> We turned scattered conventions into a single **PROJECT_CONTRIBUTION_GUIDE_v3.md** that your editor *and* AI assistant can follow. This post explains the structure, the reasoning, and how to use it with Cursor to get consistent, high‑quality code on the first try.

---

## Why consolidate—and why target Cursor?

Keeping rules in several files (`rails.mdc`, `rspec.mdc`, `ruby.mdc`, and a contribution guide) makes context brittle: people and AIs miss details, apply conflicting standards, or burn time reconciling guidance. By merging into a **single, sectioned** guide, we make expectations **discoverable, enforceable, and prompt‑friendly**.

- **LLM‑ready structure.** The guide uses clear categories and subcategories; Cursor can “see” and apply them reliably.
- **Less back‑and‑forth.** Coders and AI helpers won’t guess response formats or pagination rules.
- **First‑class Rails defaults.** We start with Rails‑way + KISS, then add just enough structure for teams and CI.


---

## The Canonical Categories (and what they contain)

Below are the categories and representative points you’ll find in the consolidated guide. Each category is designed to be skim‑able for humans and parsable for AI assistants.

### 1) Philosophy & Principles
- **Rails‑way & KISS first.** Prefer conventions and built‑ins; avoid layers until complexity demands them.
- **Blueprinter is the single JSON source.** Controllers never hand‑craft JSON.
- **DRY, selectively SOLID.** Extract when duplication harms clarity; avoid over‑engineering.

### 2) Code Style (Ruby)
- Every file starts with:
  ```ruby
  # frozen_string_literal: true

  ```
- Naming: `snake_case` for methods/variables/files, `CamelCase` for classes/modules.
- Prefer early returns and small, intention‑revealing methods.
- Use UTC internally; serialize timestamps as ISO8601 strings.

### 3) Routing
- All endpoints are versioned: `/api/v1/` (keeps room for future breaking changes).

### 4) Controllers
**Responses**
- **Lists:** `{ data: [...], meta: { /* pagination & other meta */ } }`
- **Single item:** `{ data: { ... } }`

**Parameters & Authorization**
- Strong parameters everywhere.
- **Pundit** for authorization (deny by default).

**Search & Pagination**
- **Kaminari** for pagination, always include `meta`.
- **Ransack** for search/filters (whitelist searchable attributes).

**Attachments in *one* request**
- If an endpoint requires attachments, the model declares associations and accepts nested attributes; the API accepts multipart form data in one round trip.
  ```ruby
  # frozen_string_literal: true

  class EducationItem < ApplicationRecord
    has_many :images, class_name: "GalleryImage", as: :attachable, dependent: :destroy
    has_many :files,  class_name: "FileDocument", as: :attachable, dependent: :destroy

    accepts_nested_attributes_for :file, allow_destroy: true
  end
  ```
  ```bash
  curl -X POST "http://localhost:3000/api/v1/profiles/49/educations"     -H "Authorization: Bearer $TOKEN"     -H "Content-Type: multipart/form-data"     -F "education_item[item_type]=degree"     -F "education_item[title]=Bachelor of Science"     -F "education_item[degree]=BSc"     -F 'education_item[field_of_study]=Computer Science'     -F "education_item[currently_enrolled]=false"     -F "education_item[start_date]=2018-09-01"     -F "education_item[end_date]=2022-06-30"     -F "education_item[file_attributes][doc_type]=pdf"     -F "education_item[file_attributes][file]=@spec/fixtures/files/test.pdf;type=application/pdf"
  ```

**Global exception handling**
- Centralize error handling in `ApplicationController` to return predictable JSON:
  ```ruby
  render json: { error: e.record.errors.full_messages.to_sentence }, status: :unprocessable_content
  ```

### 5) Models
**Validations & Enums**
- Keep validations close to data.
- **Enums** are defined once (DRY) and surfaced verbatim in serializers/tests.

**Associations & Attachments**
- Use `has_many :images` / `has_many :files` as shown above when the endpoint needs attachments.
- Use `accepts_nested_attributes_for` to enable single‑request creates/updates.

**Constraints**
- **Database constraints first:** NOT NULL, FKs, and unique indexes in migrations—don’t rely solely on model validations.

### 6) Serialization
- **Blueprinter** owns the shape of `data` (and error payloads, if you standardize them). Controllers just compose the envelope.
- Provide `ApplicationBlueprint` with a small `timestamps` helper to emit ISO8601 `created_at/updated_at`.

### 7) Search / Pagination / Sorting
- **Kaminari** for limits & pages; add caps and include `meta` in every list response.
- **Ransack** for filters; expose only allow‑listed fields.
- **Sorting**: allow‑list the columns/direction to prevent injection or invalid columns.

### 8) Security
- Devise (JWT) for API authentication.
- Pundit for authorization; default deny.
- Strong parameters throughout; no unpermitted mass‑assignment.
- Keep secrets in Rails Credentials; never commit them.

### 9) Performance & Data
- **Avoid N+1** using `includes`/`preload` when rendering associated data.
- Add indexes for foreign keys and high‑cardinality lookups.
- Consider simple caching (ETag/Last‑Modified) and minimal payloads.
- Light instrumentation via `request_id` tags and `ActiveSupport::Notifications`.

### 10) Testing (RSpec)
- **Request specs**, **model specs**, **policy specs**, and **serializer** (Blueprinter) snapshots.
- **FactoryBot + Faker** for data.
- Determinism: `freeze_time` / `travel_to` for ISO8601 assertions; stub external calls (WebMock/VCR).
- Force English locale in tests by default for predictable assertions; add targeted locale tests when needed.

### 11) Definition of Done (DoD)
- Rails‑way + KISS adhered to.
- Blueprinter for all JSON.
- `{ data, meta }` for lists; `{ data }` for single item.
- Pundit + Kaminari + Ransack in place as applicable.
- DB constraints, enums, no N+1.
- Tests for controllers (requests), models, policies, and serialization.

---

## How to attach the Guide to your Cursor prompt (exact steps)

**Option A — Replace scattered rules with one file**
1. Add the consolidated `PROJECT_CONTRIBUTION_GUIDE_v3.md` to your repo.
2. In Cursor, open your workspace settings and **pin** this file (or paste it into your global “Rules” file).
3. In Chat, reference it explicitly: “Follow the rules in PROJECT_CONTRIBUTION_GUIDE_v3.md. Respect Blueprinter envelopes and the ‘attachments in one request’ policy.”

**Option B — Keep rules separate but link to one source**
1. Keep `rails.mdc`, `rspec.mdc`, `ruby.mdc`, but add at the top of each: “This file defers to PROJECT_CONTRIBUTION_GUIDE_v3.md; if conflicts arise, the Guide wins.”
2. Pin all files in Cursor; the Guide becomes the conflict resolver.

**Prompt snippet to paste in Cursor (pin this):**
```text
You are assisting on a Rails API project. Follow PROJECT_CONTRIBUTION_GUIDE_v3.md strictly:
- Rails-way + KISS; Blueprinter is the single JSON source.
- List endpoints return { data, meta }; single returns { data }.
- Use Pundit for authz, Kaminari for pagination (with meta), Ransack for filters.
- For endpoints with attachments, one request with nested attributes is mandatory.
- Add `# frozen_string_literal: true` at the top of every Ruby file.
- Use UTC + ISO8601 timestamps.
Return only the requested code + file paths; do not invent fields outside the schema.
```
This pinned prompt reduces retries and keeps generated code aligned with our conventions.

---

## Why this improves efficiency

- **Fewer review cycles.** Response envelopes, pagination, and authz are consistent from the start.
- **Predictable AI output.** Cursor synthesizes code that already matches our structure (controllers, models, serializers).
- **Lower context cost.** One authoritative file means fewer tokens and less ambiguity.
- **Safer by default.** DB constraints + allow‑listed search/sorting reduce production risks.
- **Testable from day 1.** RSpec guidance ensures deterministic, CI‑friendly suites.

---

## Quick Reference (copy/paste)

**List response pattern**
```ruby
# frozen_string_literal: true

def index
  resources = paginate(scope) # Kaminari
  render json: { data: Blueprint.render_as_hash(resources), meta: pagination_meta(resources) }
end
```

**Single response pattern**
```ruby
# frozen_string_literal: true

render json: { data: Blueprint.render_as_hash(record) }, status: :created
```

**Global exception example**
```ruby
# frozen_string_literal: true

render json: { error: e.record.errors.full_messages.to_sentence }, status: :unprocessable_content
```

**Attachments in one request (model)**
```ruby
# frozen_string_literal: true

has_many :images, class_name: "GalleryImage", as: :attachable, dependent: :destroy
has_many :files,  class_name: "FileDocument", as: :attachable, dependent: :destroy
accepts_nested_attributes_for :file, allow_destroy: true
```

---

By unifying our standards and making them prompt‑aware, we get the best of both worlds: **Rails defaults** that keep us fast, and **clear rules** that keep humans and AI aligned. The result is higher‑quality code with far less friction.
