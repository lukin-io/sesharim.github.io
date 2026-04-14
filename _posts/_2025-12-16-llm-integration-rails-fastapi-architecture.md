---
layout: post
title: "Integrating LLM Services into Your Rails API: A Complete Architecture Guide"
date: 2025-12-16
author: Max Lukin
tags: [rails, llm, ai, fastapi, integration, architecture, sse, streaming, api-gateway, microservices]
categories: [engineering, rails, ai, architecture]
description: "A comprehensive guide to integrating a FastAPI LLM backend with an existing Ruby on Rails API—covering architecture patterns, streaming strategies, authentication reconciliation, and the case for internal gem isolation."
published: false
hide: true
---

> _"The best integration isn't the most technically impressive—it's the one that fits your existing patterns while leaving room to evolve."_

We needed to integrate a custom LLM chat service (FastAPI/Python) with our existing Ruby on Rails API. The challenge wasn't just "call an HTTP endpoint"—it was designing an architecture that handles real-time streaming, centralized billing, authentication reconciliation, and future scalability without rewriting our entire stack.

This post documents our architectural analysis, the top integration patterns we evaluated, and why we chose an internal gem approach that mirrors our existing `fraudify` and `notify` engines.

---

## Table of Contents

1. [The Challenge: Two Worlds Colliding](#1-the-challenge-two-worlds-colliding)
2. [Understanding the Integration Landscape](#2-understanding-the-integration-landscape)
3. [Top 3 Recommended Integration Patterns](#3-top-3-recommended-integration-patterns)
4. [Streaming Architecture: ActionController::Live vs Direct SSE](#4-streaming-architecture-actioncontrollerlive-vs-direct-sse)
5. [HTTP Client Patterns with Faraday](#5-http-client-patterns-with-faraday)
6. [Authentication Reconciliation Strategies](#6-authentication-reconciliation-strategies)
7. [The Case for Internal Gem Isolation](#7-the-case-for-internal-gem-isolation)
8. [Security Considerations](#8-security-considerations)
9. [Performance Optimization](#9-performance-optimization)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Key Takeaways](#11-key-takeaways)

---

## 1. The Challenge: Two Worlds Colliding

### 1.1 The Starting Point

Our Rails API is a mature, JWT-based backend serving a Next.js frontend:

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Authentication** | Devise + JWT (HS256) | 1-day expiration, JTIMatcher revocation |
| **Authorization** | Pundit | Deny-by-default policies |
| **Serialization** | Blueprinter | Envelope pattern (`success`, `message`, `data`, `meta`) |
| **Real-time** | ActionCable | `solid_cable` adapter in production |
| **HTTP Client** | Faraday | OAuth character fetching with retry logic |
| **Background Jobs** | Sidekiq + Redis | Queues: critical, default, mailers, low |
| **Rate Limiting** | Rack::Attack | IP/user throttling, blocklists |

### 1.2 The New Requirement

We needed to integrate an **AI Chat Service**—a FastAPI LLM backend that provides:

- **Conversational candidate search** via natural language
- **Intent classification** (search, chat, user_action)
- **Session management** in MongoDB
- **Vector search** with pgvector
- **Real-time streaming** for AI responses

### 1.3 The Core Questions

| Question | Why It Matters |
|----------|----------------|
| How do users authenticate to the LLM service? | FastAPI expects OAuth2 + scopes; Rails uses Devise JWT |
| Who owns billing/credits? | Must deduct before or after AI response |
| How do we stream responses? | LLM generates tokens incrementally |
| Where does session state live? | MongoDB (FastAPI) vs PostgreSQL (Rails) |
| How do we maintain our API patterns? | Frontend expects consistent envelopes |

---

## 2. Understanding the Integration Landscape

### 2.1 Six Integration Patterns Analyzed

We evaluated six distinct architectural patterns:

| Option | Pattern | Best For |
|--------|---------|----------|
| **A: API Gateway** ⭐ | Rails proxies all requests | Security, billing, simplicity |
| **B: Shared JWT** | Frontend calls both services | Low latency, independent scaling |
| **C: Service Mesh** | Istio/Linkerd handles routing | Kubernetes environments |
| **D: Message Queue** | Async via Redis/RabbitMQ | High-volume batch processing |
| **E: GraphQL Federation** | Schema-stitched gateway | GraphQL-first teams |
| **F: Hybrid** | Gateway + direct streaming | Best streaming UX |

### 2.2 Comparison Matrix

| Criteria | A: Gateway | B: Shared JWT | C: Mesh | D: Queue | E: GraphQL | F: Hybrid |
|----------|:----------:|:-------------:|:-------:|:--------:|:----------:|:---------:|
| **Setup Complexity** | Low | Medium | High | Medium | High | Medium |
| **Latency** | +50ms | Lowest | Low | Variable | Medium | Mixed |
| **Security** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Billing Accuracy** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Streaming UX** | Good | Best | Good | Poor | Good | Best |
| **Scalability** | Medium | High | High | High | Medium | High |
| **Fits Rails API** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |

---

## 3. Top 3 Recommended Integration Patterns

Based on our analysis, we recommend a **progressive approach**: start simple, evolve when needed.

### 3.1 🥇 #1: Option A — API Gateway (Start Here)

**Pattern**: Rails acts as the sole entry point; all AI requests proxy through Rails to FastAPI.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                             │
│                              │                                       │
│                    JWT Bearer Token (Devise)                         │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Rails API Gateway                           │  │
│  │  • Authenticate (Devise JWT)                                   │  │
│  │  • Authorize (Pundit)                                          │  │
│  │  • Check/Deduct Credits                                        │  │
│  │  • Call FastAPI via Faraday                                    │  │
│  │  • Transform Response                                          │  │
│  │  • Audit Log                                                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                    X-Service-Token + User Context                    │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI LLM Backend                         │  │
│  │  • Intent Classification                                       │  │
│  │  • Vector Search (pgvector)                                    │  │
│  │  • AI Response Generation                                      │  │
│  │  • Session State (MongoDB)                                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**Advantages:**

| Advantage | Why It Matters |
|-----------|----------------|
| ✅ Single auth layer | No JWT sharing across services |
| ✅ Centralized billing | Credits deducted in Rails before response |
| ✅ FastAPI never exposed | Better security posture |
| ✅ Consistent API patterns | Frontend gets standard envelopes |
| ✅ Full audit trail | Every request logged in Rails |
| ✅ Matches existing patterns | Faraday already used for OAuth |

**Disadvantages:**

| Disadvantage | Mitigation |
|--------------|------------|
| ⚠️ +50ms latency | Acceptable for most use cases |
| ⚠️ Rails becomes bottleneck | Evolve to Option F if needed |
| ⚠️ Thread usage for streaming | Monitor Puma pool exhaustion |

**Security Aspects:**

- FastAPI not publicly accessible (network isolation)
- Service token validates internal traffic
- Pundit enforces authorization in Rails
- Rate limiting via Rack::Attack

**Performance Aspects:**

- Single additional network hop
- Connection pooling via Faraday
- Caching possible at gateway layer
- Streaming adds thread pressure

---

### 3.2 🥈 #2: Option F — Hybrid Gateway + Direct Streaming (Evolve To)

**Pattern**: Rails proxies sync requests; streaming goes directly to FastAPI with short-lived tokens.

```
                    ┌──── REST ────► Rails (auth, billing, sessions)
Frontend ───────────┤
                    └──── SSE ─────► FastAPI directly (streaming)
```

**When to adopt:**

- Streaming latency > 200ms through Rails
- Rails Puma thread pool exhausted during peak
- Need to scale streaming independently

**Advantages:**

| Advantage | Why It Matters |
|-----------|----------------|
| ✅ Best streaming latency | No proxy for token-by-token delivery |
| ✅ Rails not blocked | Threads freed during streaming |
| ✅ Billing still centralized | Via webhook completion |
| ✅ Independent scaling | Streaming scales separately |

**Disadvantages:**

| Disadvantage | Mitigation |
|--------------|------------|
| ⚠️ Two auth mechanisms | Short-lived tokens (2-5 min TTL) |
| ⚠️ CORS complexity | FastAPI needs CORS for streaming endpoint |
| ⚠️ Billing post-facto | Webhook reconciliation required |
| ⚠️ More complex frontend | Two endpoints to manage |

**Security Aspects:**

- Short-lived stream tokens limit exposure
- FastAPI validates token signature
- Webhook authentication for completion events
- Network still restricts non-streaming endpoints

**Performance Aspects:**

- Lowest possible streaming latency
- No Rails threads tied up during streams
- Scales horizontally (add FastAPI instances)
- Webhook adds small billing delay

---

### 3.3 🥉 #3: OAuth Strategy 2 — Service JWT with Scopes (Enhancement)

**Pattern**: Rails issues short-lived internal JWT with scope claims for FastAPI.

```json
{
  "sub": 123,
  "company_id": 456,
  "role": "client",
  "scopes": ["llm:chat:send", "llm:chat:read"],
  "aud": "llm-chat",
  "iss": "rails-api",
  "exp": 1702500000,
  "iat": 1702499700
}
```

**When to adopt:**

- FastAPI team wants scope enforcement
- Planning to expose FastAPI directly later
- Need audit trail of which scopes were used

**Advantages:**

| Advantage | Why It Matters |
|-----------|----------------|
| ✅ FastAPI can enforce scopes | Independent authorization layer |
| ✅ Short TTL limits exposure | 2-5 minute tokens |
| ✅ Maintains scope semantics | Aligns with OAuth requirements |
| ✅ Future-proof | Ready for direct access patterns |

**Disadvantages:**

| Disadvantage | Mitigation |
|--------------|------------|
| ⚠️ Two JWT secrets | Separate internal vs public secrets |
| ⚠️ Token generation overhead | Minimal (~1ms) |
| ⚠️ FastAPI needs JWT validation | Standard library available |

---

### 3.4 Evolution Path

```
Week 1-2              Week 3-4              If Needed
────────────────────────────────────────────────────────►

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Option A     │───►│   + Strategy 2  │───►│    Option F     │
│ (Gateway + SSE) │    │   (JWT Scopes)  │    │    (Hybrid)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        ▲                      ▲                      ▲
        │                      │                      │
   Start here           If FastAPI needs        If streaming
                       scope enforcement        bottlenecks
```

---

## 4. Streaming Architecture: ActionController::Live vs Direct SSE

### 4.1 The Streaming Decision

Real-time AI responses require streaming—the LLM generates tokens incrementally, and users expect to see them appear progressively. We evaluated two approaches:

| Option | Streaming Path | `ActionController::Live`? |
|--------|----------------|:-------------------------:|
| **Option A (Gateway)** | Frontend → **Rails** → FastAPI | ✅ Yes |
| **Option F (Hybrid)** | Frontend → **FastAPI directly** | ❌ No |

### 4.2 Option A: Rails Proxies Streaming with ActionController::Live

```ruby
# app/controllers/api/v1/llm_gateway/streams_controller.rb
module Api
  module V1
    module LlmGateway
      class StreamsController < ApplicationController
        include ActionController::Live

        def chat_stream
          response.headers["Content-Type"] = "text/event-stream"
          response.headers["Cache-Control"] = "no-cache"
          response.headers["X-Accel-Buffering"] = "no"  # Disable nginx buffering
          response.headers["Connection"] = "keep-alive"

          sse = SSE.new(response.stream, retry: 300, event: "message")

          begin
            LlmGateway::StreamingClient.chat_stream(
              query: params[:query],
              user: current_user,
              session_id: params[:session_id]
            ) do |chunk|
              sse.write(chunk, event: "chunk")
            end

            sse.write({ done: true }, event: "complete")
          rescue IOError, ActionController::Live::ClientDisconnected
            Rails.logger.info "[LLM Gateway] Client disconnected"
          ensure
            sse.close
          end
        end
      end
    end
  end
end
```

**ActionController::Live Advantages:**

| Advantage | Description |
|-----------|-------------|
| ✅ Full control | Credits deducted, audit logged, errors transformed |
| ✅ FastAPI hidden | No public exposure of LLM service |
| ✅ Consistent patterns | Same auth/error handling as REST endpoints |
| ✅ Simpler frontend | One endpoint, one auth mechanism |

**ActionController::Live Disadvantages:**

| Disadvantage | Impact |
|--------------|--------|
| ⚠️ Thread per stream | Puma thread tied up for duration |
| ⚠️ Added latency | +10-50ms per hop for token forwarding |
| ⚠️ Memory pressure | Long-lived connections use memory |
| ⚠️ Nginx buffering | Must disable with `X-Accel-Buffering: no` |

### 4.3 Option F: Direct FastAPI Streaming

```
┌──────────┐     1. POST /chat/init      ┌──────────┐
│ Frontend │ ───────────────────────────► │  Rails   │
│          │ ◄─────────────────────────── │          │
│          │     { stream_token, url }    │          │
│          │                              └──────────┘
│          │
│          │     2. GET /stream?token=xxx
│          │ ─────────────────────────────►
│          │                              ┌──────────┐
│          │ ◄─────────────────────────── │ FastAPI  │
│          │     SSE: data chunks          │          │
└──────────┘                              │          │
                                          │          │
                 3. POST /webhook          │          │
           ┌──────────────────────────────│          │
           │    { session_id, tokens }    └──────────┘
           ▼
      ┌──────────┐
      │  Rails   │  → Deduct credits
      └──────────┘
```

**Direct Streaming Advantages:**

| Advantage | Description |
|-----------|-------------|
| ✅ Lowest latency | No proxy between client and LLM |
| ✅ No thread pressure | Rails threads not blocked |
| ✅ Independent scaling | Streaming scales separately |
| ✅ Better UX | Faster token delivery |

**Direct Streaming Disadvantages:**

| Disadvantage | Impact |
|--------------|--------|
| ⚠️ Token management | Rails must issue/validate short-lived tokens |
| ⚠️ CORS complexity | FastAPI needs cross-origin configuration |
| ⚠️ Billing timing | Post-facto via webhook |
| ⚠️ Two auth flows | Frontend handles two authentication patterns |

### 4.4 When to Choose Each

| Scenario | Recommendation |
|----------|----------------|
| Starting out, simpler architecture | Option A (`ActionController::Live`) |
| High concurrent streams (100+) | Option F (direct) |
| Streaming latency critical (<50ms) | Option F (direct) |
| Don't want FastAPI exposed | Option A (gateway) |
| Need real-time credit validation | Option A (gateway) |
| Rails server resource constrained | Option F (direct) |

---

## 5. HTTP Client Patterns with Faraday

### 5.1 Why Faraday?

Our codebase already uses Faraday for OAuth character fetching. Extending this pattern to the LLM service maintains consistency:

```ruby
# Existing pattern: app/services/oauth/google_character_fetcher.rb
def connection
  @connection ||= Faraday.new(url: GOOGLE_API_URL) do |f|
    f.request :json
    f.request :retry, max: 2, interval: 0.1, backoff_factor: 2
    f.response :raise_error
    f.adapter Faraday.default_adapter
    f.options.timeout = 5
  end
end
```

### 5.2 LlmGateway Client with Faraday

```ruby
# app/services/llm_gateway/client.rb
module LlmGateway
  class Client
    class Error < StandardError; end
    class TimeoutError < Error; end
    class ServiceUnavailable < Error; end

    def chat(query:, user:, session_id: nil)
      response = connection.post("/api/v1/llm-chat/recruiter/chat") do |req|
        req.headers.merge!(auth_headers(user))
        req.body = { query: query, session_id: session_id }.compact.to_json
      end

      JSON.parse(response.body, symbolize_names: true)
    rescue Faraday::TimeoutError
      raise TimeoutError, "AI service timeout"
    rescue Faraday::ConnectionFailed
      raise ServiceUnavailable, "AI service unavailable"
    end

    private

    def connection
      @connection ||= Faraday.new(url: config.base_url) do |f|
        f.request :json
        f.request :retry,
          max: 2,
          interval: 0.5,
          backoff_factor: 2,
          exceptions: [Faraday::TimeoutError, Faraday::ConnectionFailed]
        f.response :raise_error
        f.adapter Faraday.default_adapter
        f.options.timeout = 30  # LLM needs longer timeout
        f.options.open_timeout = 5
      end
    end

    def auth_headers(user)
      {
        "Content-Type" => "application/json",
        "X-Service-Token" => config.service_token,
        "X-User-Id" => user.id.to_s,
        "X-Company-Id" => user.company_id.to_s,
        "X-User-Role" => user.role.to_s,
        "X-Request-Id" => SecureRandom.uuid
      }
    end
  end
end
```

### 5.3 Faraday Advantages

| Advantage | Description |
|-----------|-------------|
| ✅ Consistent with codebase | Same pattern as OAuth services |
| ✅ Built-in retry | Automatic backoff for transient failures |
| ✅ Middleware stack | Request/response transformation |
| ✅ Configurable timeouts | Per-connection settings |
| ✅ Connection pooling | Reuse connections efficiently |

### 5.4 Faraday Disadvantages

| Disadvantage | Mitigation |
|--------------|------------|
| ⚠️ Not streaming-native | Use `Net::HTTP` for SSE streaming |
| ⚠️ Sync by default | Wrap in background job if needed |
| ⚠️ Memory for large responses | Stream to file if needed |

### 5.5 Streaming Client (Net::HTTP)

For SSE streaming, we use `Net::HTTP` directly:

```ruby
# app/services/llm_gateway/streaming_client.rb
module LlmGateway
  class StreamingClient
    def chat_stream(query:, user:, session_id: nil, &block)
      uri = URI.parse("#{config.base_url}/api/v1/llm-chat/recruiter/chat/stream")

      request = Net::HTTP::Post.new(uri)
      request["Content-Type"] = "application/json"
      request["Accept"] = "text/event-stream"
      request["X-Service-Token"] = config.service_token
      request["X-User-Id"] = user.id.to_s

      request.body = { query: query, session_id: session_id }.compact.to_json

      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == "https"
      http.read_timeout = 120

      http.request(request) do |response|
        buffer = ""
        response.read_body do |chunk|
          buffer += chunk
          while (line_end = buffer.index("\n"))
            line = buffer.slice!(0, line_end + 1).strip
            next if line.empty? || !line.start_with?("data: ")

            data = line[6..]
            next if data == "[DONE]"

            parsed = JSON.parse(data, symbolize_names: true) rescue nil
            block.call(parsed) if parsed
          end
        end
      end
    end
  end
end
```

---

## 6. Authentication Reconciliation Strategies

### 6.1 The Problem

FastAPI requirements specify **OAuth2 Bearer + scopes** (`llm:chat:send`, `llm:chat:read`, `llm:chat:delete`), while Rails uses **Devise JWT (HS256)**. How do we reconcile these?

### 6.2 Three Strategies

| Strategy | Frontend → Rails | Rails → FastAPI | FastAPI Validates |
|----------|------------------|-----------------|-------------------|
| **1. Gateway Auth** | Current JWT | Service token + headers | `X-Service-Token` |
| **2. Service JWT** | Current JWT | Short-lived JWT (2-5 min) | Internal JWT signature |
| **3. Central IdP** | IdP JWT | Same IdP JWT | IdP public key |

### 6.3 Strategy Comparison

| Criteria | Strategy 1 | Strategy 2 | Strategy 3 |
|----------|:----------:|:----------:|:----------:|
| **Migration Effort** | None | Low | High |
| **FastAPI Complexity** | Minimal | Moderate | Moderate |
| **Scope Enforcement** | Rails only | Both services | Both services |
| **Token Lifetime** | N/A | 2-5 minutes | ~1 hour |
| **Public FastAPI** | ❌ | ❌ | ✅ |
| **Fits Option A** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Fits Option F** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

### 6.4 Our Recommendation: Start with Strategy 1

```
X-Service-Token: <shared-secret>
X-User-Id: 123
X-Company-Id: 456
X-User-Role: client
X-Company-Role: owner
X-Request-Id: uuid-for-tracing
```

**Why:**

- Zero auth migration on main product API
- FastAPI stays simple (no JWT library needed)
- Pundit enforces scope-like permissions in Rails
- Network isolation keeps FastAPI internal

---

## 7. The Case for Internal Gem Isolation

### 7.1 The Pattern: Internal Rails Engines

We already use internal gems for cross-cutting concerns:

| Gem | Path | Purpose |
|-----|------|---------|
| `fraudify` | `./fraudify` | Fraud detection, risk scoring, OTP gating |
| `notify` | `./notify` | SMS/email delivery, provider routing, templates |

Both are Rails engines with isolated namespaces, configurations, and test suites.

### 7.2 Why Create a `llm_gateway` Gem?

**Same pattern, new domain:**

```
llm_gateway/
├── Gemfile
├── llm_gateway.gemspec
├── lib/
│   ├── llm_gateway.rb              # Configuration + entry point
│   ├── llm_gateway/
│   │   ├── version.rb
│   │   ├── engine.rb           # Rails engine
│   │   └── configuration.rb
│   └── generators/
│       └── llm_gateway/
│           └── install_generator.rb
├── app/
│   ├── services/llm_gateway/
│   │   ├── client.rb           # HTTP client
│   │   ├── streaming_client.rb # SSE streaming
│   │   └── validator.rb        # Input validation
│   ├── models/llm_gateway/
│   │   └── session.rb          # Session tracking
│   └── jobs/llm_gateway/
│       └── cleanup_sessions_job.rb
├── db/migrate/
├── spec/
└── doc/
```

### 7.3 Advantages of Gem Isolation

| Advantage | Description |
|-----------|-------------|
| ✅ **Single responsibility** | Gem handles only AI gateway logic |
| ✅ **Independent testing** | `cd llm_gateway && bundle exec rspec` |
| ✅ **Clear boundaries** | Host app sees only public API |
| ✅ **Versioned** | Own changelog, semantic versioning |
| ✅ **Reusable** | Could be used by other Rails apps |
| ✅ **Team ownership** | Clear ownership of AI integration |
| ✅ **Configuration isolation** | `LlmGateway.configure` separate from app config |

### 7.4 Disadvantages of Gem Isolation

| Disadvantage | Mitigation |
|--------------|------------|
| ⚠️ More files | Generator creates boilerplate |
| ⚠️ Indirection | Clear documentation |
| ⚠️ Dependency management | Careful version pinning |
| ⚠️ Learning curve | Follow existing gem patterns |

### 7.5 Configuration Pattern

```ruby
# lib/llm_gateway.rb
module LlmGateway
  class << self
    attr_accessor :configuration

    def configure
      self.configuration ||= Configuration.new
      yield(configuration)
    end
  end

  class Configuration
    attr_accessor :base_url, :service_token, :timeout, :stream_timeout, :sandbox, :logger

    def initialize
      @base_url       = ENV.fetch("LLM_SERVICE_BASE_URL", "http://localhost:8000")
      @service_token  = ENV.fetch("LLM_SERVICE_TOKEN", nil)
      @timeout        = 30
      @stream_timeout = 120
      @sandbox        = Rails.env.development? || Rails.env.test?
      @logger         = ->(level, msg) { Rails.logger.public_send(level, "[llm_gateway] #{msg}") }
    end
  end
end
```

### 7.6 Host App Integration

```ruby
# Gemfile
gem "fraudify", path: "fraudify"
gem "notify", path: "notify"
gem "llm_gateway", path: "llm_gateway"  # ← NEW

# config/initializers/llm_gateway.rb
LlmGateway.configure do |config|
  config.base_url      = ENV.fetch("LLM_SERVICE_BASE_URL")
  config.service_token = ENV.fetch("LLM_SERVICE_TOKEN")
  config.timeout       = 30
  config.sandbox       = Rails.env.development?
end
```

---

## 8. Security Considerations

### 8.1 Network Isolation

```
┌─────────────────────────────────────────────────────────────────┐
│                         PUBLIC INTERNET                          │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Load Balancer                           │  │
│  │                    (HTTPS only)                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Rails API                               │  │
│  │                    (Authenticates, Authorizes)             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                    INTERNAL NETWORK ONLY                         │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    FastAPI LLM                             │  │
│  │                    (Trusts X-Service-Token)                │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Rate Limiting

```ruby
# config/initializers/rack_attack.rb

# General AI endpoint limit
Rack::Attack.throttle("llm_gateway/user", limit: 100, period: 1.minute) do |req|
  if req.path.start_with?("/api/v1/llm-chat")
    req.env["HTTP_AUTHORIZATION"].presence
  end
end

# Stricter streaming limit
Rack::Attack.throttle("llm_gateway/stream", limit: 10, period: 1.minute) do |req|
  req.ip if req.path.include?("/chat/stream")
end

# Credit check before expensive operations
Rack::Attack.blocklist("llm_gateway/no_credits") do |req|
  if req.path.start_with?("/api/v1/llm-chat") && req.post?
    # Check company credits via cache
    LlmGateway::CreditChecker.blocked?(req)
  end
end
```

### 8.3 Input Validation

```ruby
# app/services/llm_gateway/validator.rb
module LlmGateway
  class Validator
    MAX_QUERY_LENGTH = 2000
    ALLOWED_INTENTS = %w[search chat user_action].freeze

    # Forward-compatible character ID regex
    CHARACTER_ID_PATTERN = /\A(id_[a-f0-9]{8}|[a-f0-9]{24})\z/

    class ValidationError < StandardError; end

    def self.validate_chat_params!(params)
      validate_query!(params[:query])
      validate_intent!(params[:user_intent]) if params[:user_intent]
      validate_character_id!(params[:character_id]) if params[:character_id]
    end

    private_class_method def self.validate_query!(query)
      raise ValidationError, "Query is required" if query.blank?
      raise ValidationError, "Query too long" if query.length > MAX_QUERY_LENGTH
    end

    private_class_method def self.validate_character_id!(id)
      return if id.match?(CHARACTER_ID_PATTERN)
      raise ValidationError, "Invalid character_id format"
    end
  end
end
```

### 8.4 Audit Logging

```ruby
# app/services/llm_gateway/audit_logger.rb
module LlmGateway
  class AuditLogger
    def self.log_request(user:, action:, params:, metadata: {})
      Rails.logger.info(
        "[LLM Gateway Audit] " \
        "user_id=#{user.id} " \
        "company_id=#{user.company_id} " \
        "action=#{action} " \
        "query_preview=#{params[:query]&.truncate(50)} " \
        "metadata=#{metadata.to_json}"
      )
    end
  end
end
```

---

## 9. Performance Optimization

### 9.1 Connection Pooling

```ruby
# Use connection_pool gem for high-traffic scenarios
gem "connection_pool"

# app/services/llm_gateway/client.rb
def connection
  @connection_pool ||= ConnectionPool.new(size: 10, timeout: 5) do
    Faraday.new(url: config.base_url) do |f|
      f.request :json
      f.request :retry, max: 2
      f.response :raise_error
      f.adapter :net_http_persistent  # Keep-alive connections
    end
  end
end

def chat(...)
  @connection_pool.with { |conn| conn.post(...) }
end
```

### 9.2 Caching Session Lookups

```ruby
# app/models/llm_gateway/session.rb
class LlmGateway::Session < ApplicationRecord
  # Cache recent sessions for listing
  def self.recent_for(user, limit: 10)
    Rails.cache.fetch("llm_gateway:sessions:#{user.id}", expires_in: 5.minutes) do
      where(user: user)
        .order(last_activity_at: :desc)
        .limit(limit)
        .to_a
    end
  end
end
```

### 9.3 Background Processing for Heavy Operations

```ruby
# For long-running AI tasks, use Sidekiq
class LlmGateway::ProcessQueryJob < ApplicationJob
  queue_as :default

  def perform(user_id, query, session_id)
    user = User.find(user_id)
    result = LlmGateway::Client.chat(query: query, user: user, session_id: session_id)

    # Broadcast result via ActionCable
    LlmGatewayChannel.broadcast_to(user, event: "query_complete", data: result)
  end
end
```

### 9.4 Timeouts and Circuit Breaking

```ruby
# app/services/llm_gateway/client.rb
TIMEOUT = 30
OPEN_TIMEOUT = 5

def connection
  @connection ||= Faraday.new(url: config.base_url) do |f|
    f.options.timeout = TIMEOUT
    f.options.open_timeout = OPEN_TIMEOUT

    # Circuit breaker via middleware
    f.use Faraday::Response::RaiseError
    f.request :retry,
      max: 2,
      interval: 0.5,
      backoff_factor: 2,
      retry_statuses: [502, 503, 504]
  end
end
```

---

## 10. Implementation Roadmap

### 10.1 Phase 0: Pre-Implementation Decisions

| Decision | Choice |
|----------|--------|
| Integration Pattern | Option A (API Gateway) |
| OAuth Strategy | Strategy 1 (Gateway Auth) |
| Streaming | SSE via `ActionController::Live` |
| Package Structure | Internal gem (`llm_gateway`) |
| Session Storage | Dual (Rails for billing, FastAPI for conversation) |

### 10.2 Phase 1: Foundation (Week 1)

```
✅ Create llm_gateway gem structure
✅ Implement LlmGateway::Client with Faraday
✅ Add LlmGateway::Session model and migration
✅ Configure routes
✅ Add environment variables to .env.example
```

### 10.3 Phase 2: Core Endpoints (Week 1-2)

```
✅ Implement RecruiterController (chat, sessions CRUD)
✅ Create Blueprints for responses
✅ Add Pundit policy (LlmGatewayRecruiterPolicy)
✅ Integrate with CreditTransaction system
✅ Add input validation
```

### 10.4 Phase 3: Streaming (Week 2)

```
✅ Implement StreamsController with ActionController::Live
✅ Add LlmGateway::StreamingClient
✅ Create ActionCable channel for notifications
✅ Add Redis Pub/Sub event publisher
```

### 10.5 Phase 4: Production Readiness (Week 3)

```
✅ Add Rack::Attack rate limiting
✅ Implement audit logging
✅ Write specs (request, model, service)
✅ Create RSwag documentation
✅ Update flow/PRD docs
✅ Load testing and optimization
```

### 10.6 Phase 5: Evolution (If Needed)

```
⏳ Monitor streaming latency
⏳ If bottleneck: implement Option F (Hybrid)
⏳ Add Redis Streams for durable events
⏳ Scale FastAPI independently
```

---

## 11. Key Takeaways

### 11.1 Architecture Decisions

1. **Start with the simplest pattern that works** — Option A gives you full control without complexity
2. **Plan for evolution** — Design boundaries that allow migrating to Option F later
3. **Keep auth in one place** — Rails as gateway simplifies security model
4. **Streaming adds complexity** — Understand thread implications before committing

### 11.2 Implementation Patterns

1. **Follow existing codebase patterns** — Use Faraday if you already use Faraday
2. **Isolate as internal gem** — Clear boundaries, independent testing, reusability
3. **Forward-compatible validation** — Accept future ID formats, don't hardcode
4. **Correlation IDs everywhere** — End-to-end tracing saves debugging hours

### 11.3 Security & Performance

1. **Network isolation is your friend** — FastAPI never public = simpler security
2. **Rate limit aggressively** — AI endpoints are expensive; protect them
3. **Cache wisely** — Session lookups, credit checks, not AI responses
4. **Monitor thread usage** — `ActionController::Live` ties up Puma threads

### 11.4 The Evolution Mindset

```
Don't overbuild:
  ✗ "Let's add Kafka for events" → Start with Redis Pub/Sub
  ✗ "Let's use Option F from day one" → Start with Option A
  ✗ "Let's add GraphQL federation" → REST proxy works fine

Do plan for growth:
  ✓ Design boundaries that allow swapping implementations
  ✓ Use feature flags to toggle between streaming modes
  ✓ Keep metrics on latency and thread usage
  ✓ Document decision triggers for evolution
```

---

## Resources

- **Faraday HTTP Client**: [lostisland.github.io/faraday](https://lostisland.github.io/faraday/)
- **ActionController::Live**: [api.rubyonrails.org/classes/ActionController/Live.html](https://api.rubyonrails.org/classes/ActionController/Live.html)
- **Server-Sent Events (SSE)**: [developer.mozilla.org/docs/Web/API/Server-sent_events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- **Rails Engines Guide**: [guides.rubyonrails.org/engines.html](https://guides.rubyonrails.org/engines.html)
- **Rack::Attack**: [github.com/rack/rack-attack](https://github.com/rack/rack-attack)
- **Devise JWT**: [github.com/waiting-for-dev/devise-jwt](https://github.com/waiting-for-dev/devise-jwt)
- **Pundit Authorization**: [github.com/varvet/pundit](https://github.com/varvet/pundit)
- **Blueprinter Serialization**: [github.com/procore/blueprinter](https://github.com/procore/blueprinter)

---

*This post documents our architectural analysis for integrating an LLM chat service with our Rails API. The patterns described here—API Gateway, progressive streaming, internal gem isolation—are applicable to any Rails application integrating external AI/ML services. The key insight: start simple, plan boundaries, evolve when metrics justify it.*
