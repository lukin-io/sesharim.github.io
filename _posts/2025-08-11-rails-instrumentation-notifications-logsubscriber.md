
---
layout: post
title: "Deep Rails Instrumentation: ActiveSupport::Notifications & LogSubscriber (Rails 8+)"
date: 2025-08-11
tags: [ruby-on-rails, rails-8, instrumentation, performance, logging]
description: "Practical, copy-paste-ready patterns for ActiveSupport::Notifications and ActiveSupport::LogSubscriber in Rails 8+."
---

> **Update (typo fixes):** corrected Ruby block braces `{}` and regex escapes in code samples.

> This post combines two answers: (1) practical use cases for **ActiveSupport::Notifications**, and (2) a curated, Rails-8-friendly **cheat sheet of built-in events** you can subscribe to. It’s plug-and-play and safe for production, with dev-friendly extras.

## TL;DR
- Use **ActiveSupport::Notifications** to instrument anything (timings, payloads, cache hits, external API calls).
- Use **ActiveSupport::LogSubscriber** for **clean, structured, centralized logs** per framework (AR/AC/AV/Job/Mailer) and your own domains.
- Prefer **pattern subscriptions** (regex) and **sampling** for noisy events.
- Ship metrics to your APM (Datadog, Prometheus, etc.) by subscribing and forwarding durations.

---

# Part 1 — Useful cases for ActiveSupport::Notifications

### 1) Performance monitoring for hot paths
```ruby
# Anywhere in your code
ActiveSupport::Notifications.instrument("query.user_search") do
  User.where(active: true).limit(100).to_a
end

# e.g. config/initializers/instrumentation.rb
ActiveSupport::Notifications.subscribe("query.user_search") do |_name, start, finish, _id, payload|
  duration = (finish - start) * 1000
  Rails.logger.info("User search took #{duration.round(2)}ms")
end
```

**Why:** Quick timing without invasive changes.

---

### 2) Domain events (decouple side-effects)
```ruby
# After order is completed
ActiveSupport::Notifications.instrument("order.completed", order_id: order.id, total: order.total_cents)

ActiveSupport::Notifications.subscribe("order.completed") do |_n, _s, _f, _i, payload|
  AnalyticsService.track("Order Completed", payload) # async-friendly
end
```

**Why:** Analytics/email/etc. stay out of core logic.

---

### 3) Leverage built-in framework events
Common ones you’ll use a lot:
- **ActiveRecord:** `sql.active_record`, `instantiation.active_record`
- **ActionController:** `start_processing.action_controller`, `process_action.action_controller`, `redirect_to.action_controller`, `send_file.action_controller`
- **ActionView:** `render_template.action_view`, `render_partial.action_view`, `render_collection.action_view`
- **ActiveJob:** `enqueue.active_job`, `enqueue_at.active_job`, `perform_start.active_job`, `perform.active_job`
- **ActionMailer:** `deliver.action_mailer`, `receive.action_mailer`
- **Cache (ActiveSupport):** `cache_read.active_support`, `cache_fetch_hit.active_support`, `cache_generate.active_support`, `cache_write.active_support`, `cache_delete.active_support`, `cache_exist?.active_support`
- **ActionCable:** `perform_action.action_cable`, `broadcast.action_cable`, `transmit.action_cable`

```ruby
ActiveSupport::Notifications.subscribe("sql.active_record") do |_n, s, f, _i, payload|
  next if payload[:name] == "SCHEMA"
  ms = ((f - s) * 1000).round(1)
  Rails.logger.debug("SQL (#{ms}ms) {name=#{payload[:name]}} {sql=#{payload[:sql]}}")
end
```

**Why:** Build custom loggers, catch slow queries/N+1s, trace requests end-to-end.

---

### 4) Background job timing
```ruby
ActiveSupport::Notifications.subscribe("perform.active_job") do |_n, s, f, _i, p|
  ms = ((f - s) * 1000).round(1)
  Rails.logger.info("[job] {class=#{p[:job].class}} {id=#{p[:job].job_id}} {duration_ms=#{ms}}")
end
```

**Why:** Observe job latency and failures by class/queue.

---

### 5) Track external HTTP requests
```ruby
ActiveSupport::Notifications.instrument("http.request", url: url, service: "billing") do
  HTTP.timeout(20).get(url)
end

ActiveSupport::Notifications.subscribe("http.request") do |_n, s, f, _i, p|
  Rails.logger.info("[http] {service=#{p[:service]}} {url=#{p[:url]}} {ms=#{((f-s)*1000).round(1)}}")
end
```

**Why:** Watch third-party latency, alert on anomalies.

---

### 6) Centralized auditing
```ruby
ActiveSupport::Notifications.instrument("user.login", user_id: user.id)

ActiveSupport::Notifications.subscribe("user.login") do |_n, _s, _f, _i, payload|
  AuditLog.create!(event: "login", user_id: payload[:user_id])
end
```

**Why:** One pipeline for audit events.

---

### 7) Conditional logging (dev/staging only)
```ruby
if Rails.env.development?
  ActiveSupport::Notifications.subscribe("render_template.action_view") do |_n, s, f, _i, p|
    puts "Rendered {view=#{p[:identifier]}} in {ms=#{((f-s)*1000).round(1)}}"
  end
end
```

**Why:** Keep prod quiet, keep dev noisy.

---

# Part 2 — Cheat sheet: Built-in Rails events & a ready initializer

## Copy-paste initializer
Create **`config/initializers/instrumentation.rb`**:

```ruby
# config/initializers/instrumentation.rb

def redact_params(params)
  return params unless params.is_a?(Hash)
  params.deep_dup.tap do |h|
    %w[password password_confirmation token Authorization].each { |k| h[k] = "[FILTERED]" if h.key?(k) }
  end
end

def log_event(name, start, finish, _id, payload)
  ms = ((finish - start) * 1000).round(1)
  safe = payload.is_a?(Hash) ? payload.except(:connection, :binds, :mail) : payload
  if name == "process_action.action_controller" && safe[:params]
    safe = safe.merge(params: redact_params(safe[:params]))
  end
  Rails.logger.info("[#{name}] {ms=#{ms}} {payload=#{safe}}")
end

EVENTS = %w[
  start_processing.action_controller
  process_action.action_controller
  redirect_to.action_controller
  send_file.action_controller

  render_template.action_view
  render_partial.action_view
  render_collection.action_view

  sql.active_record
  instantiation.active_record

  enqueue.active_job
  enqueue_at.active_job
  perform_start.active_job
  perform.active_job

  deliver.action_mailer
  receive.action_mailer

  cache_read.active_support
  cache_fetch_hit.active_support
  cache_generate.active_support
  cache_write.active_support
  cache_delete.active_support
  cache_exist?.active_support

  perform_action.action_cable
  broadcast.action_cable
  transmit.action_cable
]

EVENTS.each { |e| ActiveSupport::Notifications.subscribe(e, method(:log_event)) }

# Example: sample noisy events (only 5%) in production
if Rails.env.production?
  ActiveSupport::Notifications.subscribe(/\.active_record$/) do |name, start, finish, id, payload|
    next if rand > 0.05
    log_event(name, start, finish, id, payload)
  end
end
```

## What each family carries (payload highlights)
- **ActionController**: `:controller, :action, :params, :format, :method, :path, :status, :view_runtime, :db_runtime`
- **ActionView**: `:identifier, :layout, :count`
- **ActiveRecord**: `:sql, :name, :binds, :cached`
- **ActiveJob**: `:job, :queue, :priority, :scheduled_at, :exception`
- **ActionMailer**: `:mail` (with headers, recipients, subject)
- **Cache**: `:key, :hit, :expires_in`
- **ActionCable**: `:channel_class, :action, :data` / `:broadcasting, :message` / `:via`

> Tip: To discover adapter-specific events (e.g., ActiveStorage), temporarily subscribe to `/\.active_storage$/` and log names as they appear.

---

# Part 3 — LogSubscriber: clean, centralized log formatting

Use **ActiveSupport::LogSubscriber** when you want to **format** how events are logged in one place (per namespace) instead of sprinkling `subscribe` blocks.

### Example: Custom SQL log subscriber (highlight slow queries)
```ruby
# app/log_subscribers/sql_log_subscriber.rb
class SqlLogSubscriber < ActiveSupport::LogSubscriber
  SLOW_MS = 150.0

  def sql(event)
    payload = event.payload
    return if payload[:name] == "SCHEMA"

    ms = event.duration.round(1)
    msg = "SQL (#{ms}ms) #{payload[:name]} -- #{payload[:sql]}"
    ms >= SLOW_MS ? warn(msg) : debug(msg) # uses Rails logger levels
  end
end

SqlLogSubscriber.attach_to :active_record
```

### Example: Structured controller logs as JSON
```ruby
# app/log_subscribers/controller_log_subscriber.rb
class ControllerLogSubscriber < ActiveSupport::LogSubscriber
  def process_action(event)
    p = event.payload
    data = {
      at: "end",
      controller: p[:controller],
      action:     p[:action],
      status:     p[:status],
      method:     p[:method],
      path:       p[:path],
      view_ms:    p[:view_runtime],
      db_ms:      p[:db_runtime],
      duration_ms: event.duration.round(1),
      request_id: Current.request_id # if you set this in a middleware
    }
    info(data.to_json)
  end
end

ControllerLogSubscriber.attach_to :action_controller
```

### Example: Job logs to a separate file
```ruby
# config/initializers/job_logger.rb
JOB_LOGGER = ActiveSupport::Logger.new(Rails.root.join("log/jobs.log"))

# app/log_subscribers/job_log_subscriber.rb
class JobLogSubscriber < ActiveSupport::LogSubscriber
  def perform(event)
    job = event.payload[:job]
    msg = "[job] class={#{job.class}} id={#{job.job_id}} ms={#{event.duration.round(1)}}"
    JOB_LOGGER.info(msg)
  end
end

JobLogSubscriber.attach_to :active_job
```

### Tips
- Use **`attach_to :namespace`** where namespace matches the event suffix (e.g., `:active_record`, `:action_controller`, `:active_job`).
- Prefer **LogSubscriber** for **formatting and routing logs**, and **Notifications** for **wiring side-effects** (metrics, auditing, async work).
- Combine with **`ActiveSupport::TaggedLogging`** to add `request_id`, `user_id`, `tenant`, etc.

```ruby
# config/application.rb
config.log_tags = [:request_id]
```

---

# Part 4 — Bonus power patterns

### A) Quick N+1 detector (dev only)
```ruby
if Rails.env.development?
  ActiveSupport::Notifications.subscribe("sql.active_record") do |_n, _s, _f, _i, payload|
    if payload[:name] !~ /SCHEMA/ && payload[:sql].match?(/SELECT/i) && caller.any? { |c| c.include?("app/views") }
      Rails.logger.warn("[N+1?] {sql=#{payload[:sql].truncate(140)}}")
    end
  end
end
```

### B) Prometheus/StatsD metrics
```ruby
ActiveSupport::Notifications.subscribe("process_action.action_controller") do |_n, s, f, _i, p|
  duration_ms = (f - s) * 1000
  PROM.histogram(:http_request_duration_ms,
    labels: { action: "#{p[:controller]}##{p[:action]}", status: p[:status] }
  ).observe(duration_ms)
end
```

### C) Sample noisy families in production
```ruby
ActiveSupport::Notifications.subscribe(/\.active_record$/) do |name, start, finish, id, payload|
  next if rand > 0.05
  Rails.logger.info("[sampled] {event=#{name}} {ms=#{((finish-start)*1000).round(1)}}")
end
```

---

## Wrap-up
- Start with the copy-paste initializer to get **visibility fast**.
- Add **LogSubscribers** where you need **consistent formatting** or **separate sinks**.
- Instrument your own domain events so analytics/auditing stay **decoupled**.
- Use **sampling** and **redaction** to keep production logs usable.

Happy instrumenting! ✨
