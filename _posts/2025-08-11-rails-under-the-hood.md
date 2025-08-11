---
layout: post
title: "Under-the-Hood Mechanisms of Ruby on Rails You Should Know"
date: 2025-08-11  00:01:01
author: Max Lukin
<!-- tags: rails, jwt, tools -->
# categories: ruby-on-rails rails-internals performance optimization
---

If you’re comfortable writing Rails apps but want to *really* understand what’s going on under the hood—and use that knowledge to make better technical decisions—this is your map.

## Boot & Code Loading

- **Railties / initializers** – Rails boots by loading frameworks via Railties, then `/config/initializers/**/*`.
  *Tip:* Keep initializers idempotent; prefer `config.after_initialize` when you need app code.

- **Zeitwerk autoloader** – Constant names map to file paths; reloading in dev runs through `Rails.application.reloader`.
  *Command:* `bin/rails zeitwerk:check` to catch autoloading mistakes.

## Rack & Middleware

- **Rack request lifecycle** – Controllers are just Rack endpoints after a middleware pipeline.
  *Command:* `bin/rails middleware` to see the stack; add custom middleware for cross-cutting concerns.

- **Useful built-ins** – `Rack::Deflater` (gzip), `Rack::Attack` (rate limit).
  *Note:* Middleware runs for everything—including 404s and assets—so keep it lean.

## Controllers & Execution

- **ActionPack & executors** – Requests run inside an `ActionController::Metal` stack with `ActiveSupport::Executor`.
  *Tip:* Use `CurrentAttributes` for per-request state.

- **Strong Parameters** – Permit/require guards data flow into models.
  *Gotcha:* Nested params that *look* permitted but aren’t.

## Observability & Instrumentation

- **ActiveSupport::Notifications** – Everything emits events: `sql.active_record`, `process_action.action_controller`.
  *Example:*
  ```ruby
  ActiveSupport::Notifications.subscribe("sql.active_record") do |*args|
    payload = args.last
    Rails.logger.debug("[SQL] #{payload[:name]} (#{payload[:duration].round(1)}ms): #{payload[:sql]}")
  end
  ```

- **LogSubscribers** – Control how events are logged; easy to extend.

## Active Record Internals

- **Connection pool** – Thread-safe pool; deadlocks often mean pool exhaustion.
  *Command:* `bin/rails r 'p ActiveRecord::Base.connection_pool.stat'`.

- **Query cache** – Per-request SELECT cache; invalidated on writes.
  *Tip:* `ActiveRecord::Base.cache { … }` for short-lived caching.

- **Lazy relations** – Chains don’t execute until used; `.load` materializes.

- **Arel** – Query builder under AR for advanced SQL without string-SQL.

- **Transactions, savepoints, locking** – `transaction(joinable: false)`, `with_lock`.

- **Dirty tracking** – `saved_change_to_attribute?` shows changes after save.

## Caching

- **Low-level cache** (`Rails.cache.fetch`), **fragment caching**, **Russian doll caching**.
  *Tip:* Namespace keys with `"model/#{record.cache_key_with_version}"`.

- **HTTP caching** – `fresh_when`, `stale?`, ETags, Last-Modified.

## Background & Async

- **Active Job** – Adapter for Sidekiq, Resque, etc.
  *Tip:* Pass IDs, not objects.

- **Async queries** – Offload long reports to background jobs.

## Storage & Files

- **Active Storage** – Validations and content-type checks are your job.
  *Tip:* Attach variants with strict processors.

## Security & Crypto

- **MessageVerifier/Encryptor** – Signed & encrypted cookies.
- **Credentials** – `bin/rails credentials:edit` for secrets.
- **Active Record Encryption** – Column-level encryption.

## Concurrency & Performance

- **Puma threads/processes** – Tune `WEB_CONCURRENCY × RAILS_MAX_THREADS` to DB pool and CPU.
- **Bootsnap** – Speeds boot; clear cache when needed.

## Routing

- **Constraints & mounts** – Route constraints for multi-tenancy, health checks.

## I18n, Zones, and Time

- **Time zone awareness** – App zone vs UTC in DB.

## Engines & Modularization

- **Rails Engines** – Mini apps inside your app for better boundaries.

## Hidden (but killer) Tools & Gems

- `strong_migrations` – Detect unsafe migrations.
- `rack-mini-profiler` – See endpoint SQL/N+1.
- `derailed_benchmarks` – Memory/boot breakdowns.
- `brakeman` – Security scanning.
- `lograge` – Structured logs.
- `anyway_config` – Typed runtime config.
- `scenic` – DB views as migrations.

---

**Quick Health Commands:**
- Middleware: `bin/rails middleware`
- Routes: `bin/rails routes -g profiles`
- DB pool: `bin/rails r 'p ActiveRecord::Base.connection_pool.stat'`
- Eager load check: `bin/rails zeitwerk:check`

---

*Mastering these internals means fewer surprises, faster debugging, and Rails that scales with you.*
