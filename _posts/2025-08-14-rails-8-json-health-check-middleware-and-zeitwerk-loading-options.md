
---
layout: post
title: "Rails 8: JSON Health Check Middleware (+ Zeitwerk loading options)"
date: 2025-08-14 12:00:00 +0300
categories: [rails, ops]
tags: [rails-8, middleware, healthcheck, zeitwerk, devops]
excerpt: A tiny Rack middleware for a fast /up endpoint in a Rails API app—configurable JSON, ENV whitelist, DB/Redis checks—and three ways to load it with Zeitwerk (require, autoload_lib, after_initialize).
---

> TL;DR: Replace the controller-based `/up` with a tiny **Rack middleware** that returns JSON, can whitelist selected `ENV` vars, and run quick dependency checks (DB/Redis). Then pick one of **three** loading strategies so the constant resolves cleanly at boot.

## Why a middleware version of `/up`?

- **Fast & resilient**: Runs before routing/controllers.
- **Configurable JSON**: Show a minimal payload in prod, richer info in dev/staging.
- **Dependency probes**: Opt-in checks (e.g., ActiveRecord connection, Redis ping).
- **Security**: Optional token gate via header `X-Health-Token` or `?token=`.

---

## 1) Middleware (drop-in)

**File:** `lib/health_check_middleware.rb`

```ruby
# frozen_string_literal: true

class HealthCheckMiddleware
  DEFAULTS = {
    path: "/up",
    require_token: nil,                 # e.g., ENV["HEALTHCHECK_TOKEN"]
    env_whitelist: [],                  # e.g., %w[RAILS_ENV GIT_SHA APP_VERSION]
    checks: { db: false, redis: false },# enable per need
    required_checks: [],                # e.g., [:db, :redis] -> 503 if any fails
    redact_values: true,                # mask secret‑ish values unless whitelisted
    extra: {},                          # extra static fields to include
  }.freeze

  def initialize(app, config = {})
    @app = app
    @config = DEFAULTS.merge(config || {})
    @path = @config[:path]
  end

  def call(env)
    req = Rack::Request.new(env)
    return @app.call(env) unless req.get? && req.path == @path

    if token_required? && !valid_token?(req)
      return json(401, { status: "unauthorized", error: "invalid_token" })
    end

    checks = run_checks
    ok = overall_ok?(checks)

    payload = base_payload(req).merge(
      env: whitelisted_env,
      checks: checks,
      status: ok ? "ok" : "degraded"
    )

    json(ok ? 200 : 503, payload)
  rescue => e
    json(500, { status: "error", error: e.class.name, message: e.message })
  end

  private

  def token_required?
    v = @config[:require_token]
    v && !v.to_s.empty?
  end

  def valid_token?(req)
    expected = @config[:require_token].to_s
    header = req.get_header("HTTP_X_HEALTH_TOKEN").to_s
    param  = req.params["token"].to_s
    ActiveSupport::SecurityUtils.secure_compare(header.presence || param, expected)
  rescue
    false
  end

  def base_payload(req)
    {
      app: Rails.application.class.module_parent_name,
      rails_env: Rails.env,
      ruby: RUBY_VERSION,
      rails: Rails.version,
      time_utc: Time.now.utc.iso8601,
      pid: Process.pid,
      hostname: Socket.gethostname rescue nil,
      request_id: req.get_header("action_dispatch.request_id"),
      path: @path
    }.merge(@config[:extra] || {})
  end

  def whitelisted_env
    names = Array(@config[:env_whitelist]).map(&:to_s).uniq
    out = {}
    names.each do |k|
      v = ENV[k]
      next if v.nil?
      out[k] = redact?(k, v) ? redact(v) : v
    end
    out
  end

  def redact?(key, value)
    return false unless @config[:redact_values]
    key.match?(/secret|key|token|password|pass|credential/i) || value.length > 64
  end

  def redact(value)
    "*****#{value[-4..] || ''}"
  end

  def run_checks
    enabled = @config[:checks] || {}
    results = {}

    if enabled[:db]
      results[:db] = timeboxed(2.0) do
        active = ActiveRecord::Base.connection.active? rescue false
        { ok: active }
      end
    end

    if enabled[:redis]
      results[:redis] = timeboxed(1.5) do
        client = defined?(Redis) && (Redis.respond_to?(:current) ? Redis.current : Redis.new)
        pong = client&.ping == "PONG"
        { ok: pong }
      end
    end

    # Custom lambdas allowed: checks: { cache: -> {{ ... }} }
    enabled.each do |name, handler|
      next if [:db, :redis].include?(name)
      next unless handler.respond_to?(:call)
      results[name] = timeboxed(1.5) {{ handler.call }}
    end

    results.transform_values {{ |v| normalize_check(v) }}
  end

  def timeboxed(seconds)
    start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    result = yield
    dur = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start
    (result || {}).merge(duration_s: dur.round(4))
  rescue => e
    {{ ok: false, error: e.class.name, message: e.message }}
  end

  def normalize_check(v)
    v.is_a?(Hash) ? {{ ok: !!v[:ok], error: v[:error], message: v[:message], duration_s: v[:duration_s] }} :
      {{ ok: !!v }}
  end

  def overall_ok?(checks)
    required = Array(@config[:required_checks]).map(&:to_sym)
    return true if required.empty?
    required.all? {{ |c| checks[c] && checks[c][:ok] }}
  end

  def json(status, body)
    headers = {
      "Content-Type" => "application/json; charset=utf-8",
      "Cache-Control" => "no-store, no-cache, must-revalidate, max-age=0",
    }
    [status, headers, [JSON.generate(body)]]
  end
end
```

---

## 2) Configuration & insertion

**File:** `config/initializers/health_check_middleware.rb`

```ruby
# frozen_string_literal: true

# OPTION A: (explicit require) — simplest & most robust
# require Rails.root.join("lib/health_check_middleware")

Rails.application.configure do
  config.health_check = {
    path: "/up",
    require_token: (Rails.env.production? ? ENV["HEALTHCHECK_TOKEN"] : nil),
    env_whitelist: %w[RAILS_ENV GIT_SHA APP_VERSION],
    checks: {
      db: true,    # ActiveRecord connection ping
      redis: false # enable if you have Redis
      # cache: -> {{
      #   ok = Rails.cache.write("__hc__", "1", expires_in: 5) && Rails.cache.read("__hc__") == "1"
      #   {{ ok: ok }}
      # }}
    },
    required_checks: [:db],
    redact_values: true,
    extra: { service: "api", region: ENV["REGION"] }
  }

  # Insert early for speed & resilience
  config.middleware.insert_before 0, HealthCheckMiddleware, config.health_check
end
```

---

## 3) Three ways to load the class

### **Option A — Explicit `require` (recommended quick fix)**
Add at the top of the initializer:
```ruby
require Rails.root.join("lib/health_check_middleware")
```
Pros: deterministic, works even if `lib/` isn't eager-loaded.  
Cons: one manual `require`.

### **Option B — Zeitwerk helper (Rails 7.1+/8)**
In `config/application.rb`:
```ruby
# Autoload and eager-load lib/ except assets/tasks
config.autoload_lib(ignore: %w[assets tasks])
```
Ensure file/constant match:
- `lib/health_check_middleware.rb`
- `class HealthCheckMiddleware; end` at top-level (no module wrapping)

### **Option C — Defer insertion until after boot**
```ruby
# config/initializers/health_check_middleware.rb
Rails.application.configure do
  config.health_check = { path: "/up", checks: { db: true }, required_checks: [:db] }
end

Rails.application.config.after_initialize do
  Rails.application.config.middleware.insert_before 0, HealthCheckMiddleware, Rails.application.config.health_check
end
```
This ensures Zeitwerk has initialized when we reference the constant.

> **Don’t forget Spring**: it caches boots. If you change loader settings, run:
>
> ```bash
> bin/spring stop
> ```

---

## 4) cURL examples

Dev/Staging:
```bash
curl -s http://localhost:3000/up | jq
```

Prod (token via header or param):
```bash
curl -s -H "X-Health-Token: $HEALTHCHECK_TOKEN" https://your.api/up | jq
# or
curl -s "https://your.api/up?token=$HEALTHCHECK_TOKEN" | jq
```

---

## 5) Request spec (RSpec)

```ruby
# spec/requests/health_check_middleware_spec.rb
require "rails_helper"

RSpec.describe "HealthCheckMiddleware", type: :request do
  it "returns 200 with ok when DB check passes" do
    get "/up"
    expect(response).to have_http_status(:ok)
    json = JSON.parse(response.body)
    expect(json["status"]).to eq("ok")
    expect(json["checks"]["db"]).to include("ok" => true)
  end

  it "requires token if configured" do
    allow(Rails.configuration).to receive(:health_check)
      .and_return(Rails.configuration.health_check.merge(require_token: "secret"))
    get "/up"
    expect(response).to have_http_status(:unauthorized)

    get "/up", headers: { "X-Health-Token" => "secret" }
    expect(response).to have_http_status(:ok)
  end
end
```

---

## 6) Security notes

- Only expose **strictly whitelisted** ENV keys.
- Keep `redact_values: true`; mask secret-looking values.
- In prod, set `require_token` and/or restrict by IP/WAF (Nginx, Cloudflare, etc.).

---

## 7) Bonus: dynamic ENV prefix (optional)

If you prefer to auto-include variables by prefix, change `whitelisted_env`:
```ruby
# Example: include all APP_* vars, plus explicit keys
prefix = "APP_"
names = ENV.keys.grep(/^{{Regexp.escape(prefix)}}/) + Array(@config[:env_whitelist])
names.uniq!
```
Then use `env_whitelist: %w[RAILS_ENV]` and it will also pick up `APP_*`.

---

Happy shipping! If you want Sidekiq queue depth, S3 head-bucket, or feature-flagged payload sizes, you can extend `checks:` with small lambdas and add them to `required_checks:` if they’re critical.
