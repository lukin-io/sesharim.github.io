---
layout: post
title: "Mastering ActiveSupport::LogSubscriber (Rails 8+): JSON logs, per-tenant routing, and production patterns"
date: 2025-08-11
tags: [ruby-on-rails, rails-8, logging, logsubscriber, observability, json-logs]
description: "A practical, production-grade guide to ActiveSupport::LogSubscriber for Rails 8+: structured JSON logs, log tags, and per-tenant log routing."
---

This post is a deep dive into **ActiveSupport::LogSubscriber**. You’ll get **production-ready** patterns for:
- **Structured JSON** logs that are ingestion-friendly (ELK, Loki, Datadog, etc.).
- **Tagged context** (request/tenant/user) included in every log line.
- **Per-tenant log routing** with safe rotation and minimal overhead.
- Clean, copy‑pasteable subscribers for **controllers**, **SQL**, and **background jobs**.

> If you’re using `ActiveSupport::Notifications` already, use `LogSubscriber` to centralize **formatting and routing** of your logs. Keep metrics/auditing/side-effects in Notifications subscribers.

---

## 0) Minimal mental model

- Rails emits events (`"process_action.action_controller"`, `"sql.active_record"`, etc.).
- A **LogSubscriber** class defines methods matching the **event name prefix** (`process_action` for `"process_action.action_controller"`).
- You bind the subscriber to a **namespace** with `attach_to :action_controller`, `:active_record`, `:active_job`, etc.
- Inside the method you get an `event` with `event.duration`, and `event.payload` (hash). You write logs however you like.

---

## 1) Base JSON logger (container friendly)

Use a **JSON formatter** so you can log Hashes and they become JSON automatically:

```ruby
# config/initializers/json_logger.rb
require "json"

class JsonFormatter < ::Logger::Formatter
  def call(severity, time, progname, msg)
    event = msg.is_a?(Hash) ? msg : { message: msg.to_s }
    event[:severity] = severity
    event[:time]     = time.utc.iso8601(6)
    JSON.generate(event) + "\n"
  end
end

base = ActiveSupport::Logger.new($stdout) # good for Docker/Heroku/Render/etc.
base.formatter = JsonFormatter.new

Rails.logger = ActiveSupport::TaggedLogging.new(base)
```

> From now on, when you do `Rails.logger.info({foo: "bar"})`, it prints JSON.

---

## 2) Current attributes & request tags

Expose common context that you want **in every line**.

```ruby
# app/models/current.rb
class Current < ActiveSupport::CurrentAttributes
  attribute :request_id, :tenant_id, :user_id
end

# app/controllers/application_controller.rb
class ApplicationController < ActionController::Base
  before_action do
    Current.request_id = request.request_id
    Current.tenant_id  = request.headers["X-Tenant-Id"].presence
    Current.user_id    = try(:current_user)&.id
  end
end
```

> You can still use `config.log_tags = [:request_id]`, but placing core IDs on `Current` keeps things explicit and makes JSON logging dead simple.

Helper:

```ruby
# app/lib/logging/helpers.rb
module Logging
  module Helpers
    def redact_params(params)
      return params unless params.is_a?(Hash)
      params.deep_dup.tap do |h|
        %w[password password_confirmation token authorization].each do |k|
          h[k] = "[FILTERED]" if h.key?(k)
        end
      end
    end

    def current_tags
      { request_id: Current.request_id, tenant_id: Current.tenant_id, user_id: Current.user_id }.compact
    end
  end
end
```

---

## 3) Controller log subscriber — JSON with tags

```ruby
# app/log_subscribers/controller_log_subscriber.rb
require "json"
require Rails.root.join("app/lib/logging/helpers")

class ControllerLogSubscriber < ActiveSupport::LogSubscriber
  include Logging::Helpers

  def process_action(event)
    p = event.payload
    data = {
      at:          "end",
      controller:  p[:controller],
      action:      p[:action],
      method:      p[:method],
      path:        p[:path],
      status:      p[:status],
      view_ms:     p[:view_runtime],
      db_ms:       p[:db_runtime],
      duration_ms: event.duration.round(1),
      params:      redact_params(p[:params] || {})
    }.merge(tags: current_tags)

    # Write to the normal Rails logger (JSON via formatter)
    info(data)

    # Also route to a per-tenant file (see Section 4)
    tenant_logger(Current.tenant_id).info(data)
  end
end

ControllerLogSubscriber.attach_to :action_controller
```

---

## 4) Per-tenant log routing

Write a **copy** of selected events into a per-tenant file. This is handy for B2B debugging, SOC2 audit trails, or noisy customers.

```ruby
# config/initializers/tenant_logging.rb
require "fileutils"

TENANT_LOG_DIR = Rails.root.join("log/tenants")
FileUtils.mkdir_p(TENANT_LOG_DIR)

TENANT_LOGGER_MUTEX = Mutex.new
TENANT_LOGGERS = {}

def tenant_logger(tenant_id)
  id = tenant_id.presence || "public"
  TENANT_LOGGER_MUTEX.synchronize do
    TENANT_LOGGERS[id] ||= begin
      path = TENANT_LOG_DIR.join("#{id}.log")
      # rotate 10 files, 10MB each; adjust to your ops constraints
      logger = ActiveSupport::Logger.new(path, 10, 10 * 1024 * 1024)
      logger.formatter = Rails.logger.formatter # same JSON formatter
      logger
    end
  end
end

# Optional: clean up rarely used tenant loggers every day
Rails.application.config.after_initialize do
  Thread.new do
    loop do
      sleep 86_400 # 24h
      TENANT_LOGGER_MUTEX.synchronize do
        TENANT_LOGGERS.delete_if do |id, logger|
          # close stale loggers (this is a naive example; adapt as needed)
          false
        end
      end
    end
  end
end
```

> Don’t route **everything** to per-tenant logs—just events that matter (e.g., controller completions, domain events, security-sensitive flows).

---

## 5) SQL log subscriber — highlight slow queries

```ruby
# app/log_subscribers/sql_log_subscriber.rb
class SqlLogSubscriber < ActiveSupport::LogSubscriber
  SLOW_MS = 150.0

  def sql(event)
    payload = event.payload
    return if payload[:name] == "SCHEMA"

    data = {
      at:          "sql",
      name:        payload[:name],
      sql:         payload[:sql],
      cached:      payload[:cached],
      duration_ms: event.duration.round(1),
      tags:        { request_id: Current.request_id, tenant_id: Current.tenant_id }
    }

    if event.duration >= SLOW_MS
      warn(data)
    else
      debug(data)
    end
  end
end

SqlLogSubscriber.attach_to :active_record
```

> For privacy, avoid logging bind values. If you must, log names only: `payload[:binds].map { |attr| attr.name }`.

---

## 6) Job log subscriber — queue, retries, exceptions

```ruby
# app/log_subscribers/job_log_subscriber.rb
class JobLogSubscriber < ActiveSupport::LogSubscriber
  def perform(event)
    job = event.payload[:job]
    ex  = event.payload[:exception_object]

    data = {
      at:          "job.perform",
      job_class:   job.class.name,
      job_id:      job.job_id,
      queue_name:  job.queue_name,
      duration_ms: event.duration.round(1),
      error:       ex && { type: ex.class.name, message: ex.message },
      tags:        { tenant_id: Current.tenant_id }
    }

    if ex
      error(data)
      tenant_logger(Current.tenant_id).error(data)
    else
      info(data)
    end
  end
end

JobLogSubscriber.attach_to :active_job
```

---

## 7) Multiplexing logs (broadcasting)

Sometimes you want **the same JSON line** to go to multiple sinks (stdout + file). Ruby’s logger can broadcast:

```ruby
# config/initializers/broadcast_logger.rb
json_stdout = Rails.logger # from Section 1
json_file   = ActiveSupport::Logger.new(Rails.root.join("log/combined.json.log"))
json_file.formatter = json_stdout.formatter

Rails.logger.extend(ActiveSupport::Logger.broadcast(json_file))
```

> You can also broadcast only **inside** subscribers for specific events (e.g., only controller completions).

---

## 8) Sampling & noise control

High-volume apps need sampling to keep costs sane:

```ruby
# app/log_subscribers/sql_log_subscriber.rb (variation)
class SqlLogSubscriber < ActiveSupport::LogSubscriber
  SAMPLE = 0.1 # 10%
  SLOW_MS = 150.0

  def sql(event)
    payload = event.payload
    return if payload[:name] == "SCHEMA"
    return if rand > SAMPLE && event.duration < SLOW_MS

    info({
      at: "sql",
      name: payload[:name],
      sql: payload[:sql],
      duration_ms: event.duration.round(1),
      tags: { request_id: Current.request_id, tenant_id: Current.tenant_id }
    })
  end
end
```

---

## 9) Domain-specific subscribers

You can define your own **namespace** and attach a `LogSubscriber` to it. Combine with `Notifications` to emit domain events:

```ruby
# app/log_subscribers/orders_log_subscriber.rb
class OrdersLogSubscriber < ActiveSupport::LogSubscriber
  def checkout(event)
    data = { at: "orders.checkout", duration_ms: event.duration.round(1), payload: event.payload, tags: { tenant_id: Current.tenant_id } }
    info(data)
    tenant_logger(Current.tenant_id).info(data)
  end
end
OrdersLogSubscriber.attach_to :orders
```

Emit events from your code:
```ruby
ActiveSupport::Notifications.instrument("checkout.orders", order_id: order.id, total_cents: order.total_cents)
```

---

## 10) Production checklist

- ✅ **JSON** base logger to stdout (containers).
- ✅ **Tags**: request_id, tenant_id, user_id (via `Current`).
- ✅ **Subscribers**: controller, SQL (slow/high volume), job (errors).
- ✅ **Per‑tenant routing** only for important events.
- ✅ **Sampling** for noisy data.
- ✅ **Redaction** for secrets (`password`, `token`, `authorization`).
- ✅ Rotate files and set sensible size limits.

---

## Appendix: Quick test snippet

```ruby
# spec/log_subscribers/controller_log_subscriber_spec.rb
require "rails_helper"

RSpec.describe ControllerLogSubscriber do
  it "logs process_action with JSON" do
    payload = { controller: "HomeController", action: "index", method: "GET", path: "/", status: 200, params: {} }
    event = ActiveSupport::Notifications::Event.new("process_action.action_controller", Time.now, Time.now + 0.012, "1", payload)
    expect { ControllerLogSubscriber.new.process_action(event) }.not_to raise_error
  end
end
```

That’s it—you now have a **clean, structured** logging pipeline powered by `ActiveSupport::LogSubscriber`, with JSON, tags, and per‑tenant routing you can turn on/off as needed.
