---
layout: post
author: Max Lukin
title: Optimizing Complex Rails Endpoints with Preloading, Includes, and Smart Payload Design
date: 2025-08-14 12:01:00
categories: rails performance optimization
tags: [rails-8, performance]
excerpt: Optimizing Complex Rails Endpoints with Preloading, Includes, and Smart Payload Design
---

When you have a **Rails endpoint** returning a large object graph — like a `Profile` model with many nested relationships — it’s easy to fall into the **N+1 query trap** or generate *one giant SQL JOIN* that’s slow and hard for the DB to optimize.

This post walks you through a **practical strategy** for optimizing such endpoints, using a real-world `/api/v1/profiles/:id` example.

## 1. Don’t Load Everything — Make It Opt-In

We can expose `include=` and `fields=` parameters (JSON:API-style) so that clients request only the data they need.

```ruby
module IncludeParams
  ALLOWED_INCLUDES = %w[user contact_infos skills work_experiences.work_references].freeze

  def parsed_includes
    raw = params[:include].to_s.split(',').map(&:strip)
    raw & ALLOWED_INCLUDES
  end
end
```

## 2. Preload Only What’s Requested

By default, use **`preload`** to avoid giant JOINs. Use `joins` only for associations you filter/sort on.

```ruby
scope = Profile.preload(preload_tree(parsed_includes))
```

## 3. Serializer Views: Compact → Standard → Extended

Using Blueprinter, define multiple views. Clients choose what detail level they want.

```ruby
view :compact do
  fields :username, :role
end

view :extended do
  include_view :compact
  association :work_experiences, blueprint: WorkExperienceBlueprint
end
```

## 4. Separate Filtering JOINs from Preloads

This keeps the query planner happy and avoids over-fetching.

```ruby
joins_needed = []
joins_needed << :user if filter_on_user?
scope = scope.joins(*joins_needed).preload(preload_tree(parsed_includes))
```

## 5. HTTP Caching

Leverage ETag and Last-Modified headers for unchanged profiles.

```ruby
fresh_when etag: @profile.cache_key_with_version, last_modified: @profile.updated_at
```

## 6. Async Preloading (Rails 7+)

Run queries in parallel to shave off latency.

```ruby
Profile.preload(:skills, :languages).load_async.find(params[:id])
```

## 7. Paginate Heavy Nested Associations

Cap child record counts to avoid huge payloads.

```ruby
MAX_CHILDREN = 25
```

## 8. Sideload Heavy Data

Return IDs in the main payload, then let the client fetch details in a separate endpoint.

---

**In short:** Make the API payload *client-driven*, load data selectively, and avoid both N+1 queries and monster JOINs.

Performance gains can be huge, and maintainability improves because you’re explicit about what’s being fetched.
