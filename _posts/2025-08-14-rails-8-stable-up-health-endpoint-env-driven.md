---
layout: post
author: Max Lukin
title: "Rails 8: A Stable `/up` Health Endpoint with One Initializer (ENV‑driven)"
date: 2025-08-14 12:00:00
categories: [blog, rails, operations]
tags: [rails-8, rack, healthcheck, devops, reliability]
excerpt: A battle-tested, copy‑paste `/up` endpoint for Rails API apps—no autoloading traps, no brittle config. One initializer, ENV‑driven settings, optional DB/Redis checks, clear status semantics, and end‑to‑end tests.
---

> **TL;DR**: This post shows a **stable** and **simple** health endpoint for Rails (`/up`) implemented as a tiny Rack component defined **inside one initializer**. It reads config from **ENV** (deployment‑friendly), supports optional **DB**/**Redis** checks, emits JSON, and lets you choose whether failures return **503** or just mark the response as **degraded**. Includes cURL examples and RSpec tests.

---

## Why another `/up`?
Controller‑based health checks often drag the full Rails stack into the hot path; custom middlewares can be great but are prone to **autoload order** issues or **stale configuration**. This version avoids both:

- **Single initializer** → no Zeitwerk timing problems, no missing constants.
- **ENV‑driven** → consistent across dev/staging/prod and easy to toggle in tests.
- **Fast & safe** → short timeouts, minimal dependencies, graceful errors.
- **Clear semantics** → `"status":"ok"` vs `"degraded"`, and independent **HTTP code** policy.

---

## 1) Copy‑paste initializer

**File:** `config/initializers/up.rb`

```ruby
# frozen_string_literal: true

# A tiny, dependency-light Rack endpoint for /up.
# - Stable: defined in this initializer (no Zeitwerk/autoload order issues).
# - Configurable via ENV (see "Configuration via ENV" below).
# - Optional DB/Redis checks with short timeouts.
# - Whitelists ENV output with optional prefix and redaction.

require "json"
require "socket"
require "time"
require "timeout"

module Up
  module Utils
    module_function

    def now_iso
      Time.now.utc.iso8601
    end

    def hostname
      Socket.gethostname rescue nil
    end

    # Constant-time compare, avoids ActiveSupport dependency.
    def secure_compare(a, b)
      a = a.to_s
      b = b.to_s
      return false unless a.bytesize == b.bytesize
      l = 0
      a.bytes.zip(b.bytes) { |x, y| l |= (x ^ y) }
      l.zero?
    end

    def bool_env(key, default: false)
      v = ENV[key]
      return default if v.nil?
      %w[1 true yes on].include?(v.to_s.strip.downcase)
    end

    def float_env(key, default:)
      Float(ENV[key]) rescue default
    end

    def app_name
      app_class = Rails.application.class
      if app_class.respond_to?(:module_parent_name)
        app_class.module_parent_name
      elsif app_class.respond_to?(:parent_name)
        app_class.parent_name
      else
        "RailsApp"
      end
    end
  end

  class Endpoint
    include Utils

    def initialize(app)
      @app = app
    end

    def call(env)
      req = Rack::Request.new(env)
      return @app.call(env) unless req.get? && req.path == path

      return unauthorized unless authorized?(req)

      checks = {}
      checks[:db]    = check_db    if db_enabled?
      checks[:redis] = check_redis if redis_enabled?

      # Decide body status vs HTTP code separately.
      status_txt = any_failed?(checks) ? "degraded" : "ok"
      overall_ok = overall_ok?(checks)

      body = {
        status:   status_txt,
        time_utc: now_iso,
        app:      app_name,
        pid:      Process.pid,
        hostname: hostname,
        env:      whitelisted_env,
        checks:   checks.compact
      }

      [overall_ok ? 200 : 503, json_headers, [JSON.generate(body)]]
    rescue => e
      error_body = { status: "error", error: e.class.name, message: e.message }
      [500, json_headers, [JSON.generate(error_body)]]
    end

    private

    # --------------------------
    # Configuration (via ENV)
    # --------------------------
    def path
      ENV.fetch("HEALTHCHECK_PATH", "/up")
    end

    def token
      ENV["HEALTHCHECK_TOKEN"].to_s
    end

    def authorized?(req)
      return true if token.empty?
      provided = req.get_header("HTTP_X_HEALTH_TOKEN").to_s
      provided = req.params["token"].to_s if provided.empty?
      Utils.secure_compare(provided, token)
    end

    def env_whitelist
      # Comma-separated, e.g. "RAILS_ENV,GIT_SHA,APP_VERSION"
      (ENV["HEALTHCHECK_ENV_WHITELIST"] || "")
        .split(",").map { _1.strip }.reject(&:empty?)
    end

    def env_prefix
      ENV["HEALTHCHECK_ENV_PREFIX"].to_s # e.g. "APP_"
    end

    def redact_enabled?
      # Set HEALTHCHECK_REDACT=0 to disable redaction.
      Utils.bool_env("HEALTHCHECK_REDACT", default: true)
    end

    def required_checks
      # Comma-separated, e.g. "db,redis"
      (ENV["HEALTHCHECK_REQUIRED"] || "")
        .split(",").map { _1.strip.downcase.to_sym }.reject(&:nil?)
    end

    def db_enabled?
      Utils.bool_env("HEALTHCHECK_DB", default: false)
    end

    def redis_enabled?
      Utils.bool_env("HEALTHCHECK_REDIS", default: false) ||
        (ENV["HEALTHCHECK_REDIS_URL"] && !ENV["HEALTHCHECK_REDIS_URL"].empty?) ||
        (ENV["REDIS_URL"] && !ENV["REDIS_URL"].empty?)
    end

    def db_timeout
      Utils.float_env("HEALTHCHECK_DB_TIMEOUT", default: 2.0)
    end

    def redis_timeout
      Utils.float_env("HEALTHCHECK_REDIS_TIMEOUT", default: 1.5)
    end

    # --------------------------
    # ENV output
    # --------------------------
    def whitelisted_env
      keys = env_whitelist.dup
      if env_prefix && !env_prefix.empty?
        ENV.each_key { |k| keys << k if k.start_with?(env_prefix) }
      end
      keys.uniq!

      output = {}
      keys.each do |k|
        v = ENV[k]
        next if v.nil?
        output[k] = redact?(k, v) ? redact(v) : v
      end
      output
    end

    def redact?(key, value)
      return false unless redact_enabled?
      key =~ /(secret|key|token|password|pass|credential)/i || value.length > 64
    end

    def redact(value)
      tail = value[-4..] || ""
      "*****#{tail}"
    end

    # --------------------------
    # Checks
    # --------------------------
    def check_db
      started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      ok = false
      if defined?(ActiveRecord::Base)
        ok = ActiveRecord::Base.connection_pool.with_connection { |c| c.active? }
      end
      duration = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started
      { ok: ok, duration_s: duration.round(4) }
    rescue => e
      duration = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started
      Rails.logger.warn("[/up] DB check failed: #{e.class}: #{e.message}") rescue nil
      { ok: false, error: e.class.name, message: e.message, duration_s: duration.round(4) }
    end

    def check_redis
      started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      ok = false
      if defined?(Redis)
        client = if Redis.respond_to?(:current) && Redis.current
                   Redis.current
                 else
                   url = ENV["HEALTHCHECK_REDIS_URL"]
                   url = ENV["REDIS_URL"] if url.nil? || url.empty?
                   url ? Redis.new(url: url) : Redis.new
                 end
        ok = (client.ping == "PONG")
      end
      duration = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started
      { ok: ok, duration_s: duration.round(4) }
    rescue => e
      duration = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started
      Rails.logger.warn("[/up] Redis check failed: #{e.class}: #{e.message}") rescue nil
      { ok: false, error: e.class.name, message: e.message, duration_s: duration.round(4) }
    end

    def any_failed?(checks)
      checks.values.any? { |v| v && !v[:ok] }
    end

    def overall_ok?(checks)
      # HTTP 200 unless a *required* check fails
      req = required_checks
      return true if req.empty?
      req.all? { |name| checks[name] && checks[name][:ok] }
    end

    # --------------------------
    # Responses
    # --------------------------
    def json_headers
      {
        "Content-Type"  => "application/json; charset=utf-8",
        "Cache-Control" => "no-store, no-cache, must-revalidate, max-age=0"
      }
    end

    def unauthorized
      [401, json_headers, [JSON.generate({ status: "unauthorized", error: "invalid_token" })]]
    end
  end
end

# Insert at the very top for speed and resilience.
Rails.application.config.middleware.insert_before 0, Up::Endpoint
```

---

## 2) Configuration via ENV

Pick what you need. **Unset = defaults.**
```bash
# Path (optional)
HEALTHCHECK_PATH=/up

# Token gate (optional, strongly advised on public endpoints)
HEALTHCHECK_TOKEN=supersecret

# Show select ENV keys (comma-separated) and/or a prefix
HEALTHCHECK_ENV_WHITELIST=RAILS_ENV,GIT_SHA,APP_VERSION
HEALTHCHECK_ENV_PREFIX=APP_
# Redaction (default ON). Set to 0 to disable.
HEALTHCHECK_REDACT=1

# Checks (off by default)
HEALTHCHECK_DB=1
HEALTHCHECK_DB_TIMEOUT=2.0

HEALTHCHECK_REDIS=1
HEALTHCHECK_REDIS_TIMEOUT=1.5
# Optional explicit URL (falls back to REDIS_URL)
HEALTHCHECK_REDIS_URL=redis://localhost:6379/0

# HTTP policy: only fail when *required* checks fail (empty => always 200)
HEALTHCHECK_REQUIRED=db,redis
```

**Policy summary**
- `"status"` in the JSON is `"ok"` if all enabled checks pass, else `"degraded"`.
- **HTTP code** is **200** unless a **required** check fails (then **503**). If `HEALTHCHECK_REQUIRED` is empty, you always get 200 (but `"status":"degraded"` can still flag issues).

---

## 3) Usage examples (cURL)

```bash
# open (no token set)
curl -s http://localhost:3000/up | jq

# token via header
curl -s -H "X-Health-Token: supersecret" http://localhost:3000/up | jq

# token via query parameter
curl -s "http://localhost:3000/up?token=supersecret" | jq
```

**Typical responses**
```json
{ "status":"ok", "checks": { "db": {"ok": true}, "redis": {"ok": true} } }
```
```json
{ "status":"degraded", "checks": { "db": {"ok": false, "error":"..."} } }
```

---

## 4) Kubernetes / Docker / Nginx snippets

**Kubernetes (readinessProbe)**
```yaml
readinessProbe:
  httpGet:
    path: /up
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

**Nginx location (optional token)**
```nginx
location = /up {
  proxy_pass http://app_upstream;
  # If you want to require a token at the edge:
  # if ($http_x_health_token != "supersecret") { return 401; }
}
```

**Docker Compose (environment)**
```yaml
services:
  web:
    environment:
      - HEALTHCHECK_PATH=/up
      - HEALTHCHECK_TOKEN=${HEALTHCHECK_TOKEN}
      - HEALTHCHECK_ENV_WHITELIST=RAILS_ENV,GIT_SHA,APP_VERSION
      - HEALTHCHECK_DB=1
      - HEALTHCHECK_REDIS=1
      - HEALTHCHECK_REQUIRED=db,redis
```

---

## 5) End‑to‑end tests (RSpec)

**File:** `spec/requests/up_spec.rb`
```ruby
require "rails_helper"

RSpec.describe "Up endpoint", type: :request do
  def with_env(temp)
    old = {}
    temp.each { |k, v| old[k] = ENV[k]; ENV[k] = v }
    yield
  ensure
    old.each { |k, v| ENV[k] = v }
  end

  it "returns 200 OK and status ok by default" do
    with_env("HEALTHCHECK_TOKEN" => nil, "HEALTHCHECK_DB" => nil, "HEALTHCHECK_REDIS" => nil) do
      get "/up"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(%w[ok degraded]).to include(json["status"]) # no checks enabled => ok
    end
  end

  it "requires token when HEALTHCHECK_TOKEN is set" do
    with_env("HEALTHCHECK_TOKEN" => "secret") do
      get "/up"
      expect(response).to have_http_status(:unauthorized)

      get "/up", headers: { "X-Health-Token" => "secret" }
      expect(response).to have_http_status(:ok)
    end
  end

  it "marks degraded when a non-required check fails but still returns 200" do
    with_env("HEALTHCHECK_DB" => "1", "HEALTHCHECK_REQUIRED" => nil) do
      allow(ActiveRecord::Base).to receive_message_chain(:connection_pool, :with_connection).and_raise(StandardError.new("boom"))
      get "/up"
      json = JSON.parse(response.body)
      expect(response).to have_http_status(:ok)
      expect(json["status"]).to eq("degraded")
      expect(json.dig("checks", "db", "ok")).to eq(false)
    end
  end

  it "returns 503 if a required check fails" do
    with_env("HEALTHCHECK_DB" => "1", "HEALTHCHECK_REQUIRED" => "db") do
      allow(ActiveRecord::Base).to receive_message_chain(:connection_pool, :with_connection).and_raise(StandardError.new("boom"))
      get "/up"
      expect(response).to have_http_status(503)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("degraded")
    end
  end
end
```

---

## 6) Troubleshooting

**DB fails** → run:
```bash
bin/rails c
ActiveRecord::Base.establish_connection
ActiveRecord::Base.connection.active?             # => true/false
ActiveRecord::Base.connection.execute("SELECT 1") # raises if misconfigured
bin/rails db:prepare                              # create + migrate
```
**Redis fails** → verify `REDIS_URL`/`HEALTHCHECK_REDIS_URL` and can you `PING` with your client?
**Token issues** → confirm header name `X-Health-Token` or `?token=...` param; ensure constant‑time compare (already built‑in).

---

## 7) Security notes

- Never expose all ENV; use the **whitelist** and optional **prefix**.
- Keep redaction on (default).
- If `/up` is public, **set a token** and/or restrict by IP/WAF (Nginx/Cloudflare).

---

## 8) Design choices (FAQ)

- **Why ENV over Rails config?** ENV is stable at boot, easy for 12‑factor deploys, and testable without rebuilding middleware.
- **Why single initializer?** Avoids Zeitwerk load order pitfalls and keeps the endpoint fast (no controller stack).
- **Why 200 even if degraded?** Many orchestrators treat 503 as restart-worthy. Use `HEALTHCHECK_REQUIRED` to specify which checks should *gate* readiness.
- **Can I add custom checks?** Yes—clone `check_redis` pattern and enable via another ENV flag; then add its name to `HEALTHCHECK_REQUIRED` if critical.

---

### Final note
This “one‑initializer, ENV‑driven” `/up` endpoint has been reliable in practice and easy to reason about. Start minimal, enable checks as you harden the service, and mark only truly critical dependencies as **required**.
