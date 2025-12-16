
# Designing a Production‑Grade LLM Chat Architecture with Ruby on Rails & FastAPI

> **Audience**: Senior backend engineers, tech leads, architects  
> **Scope**: End‑to‑end architecture, security, performance, streaming, async processing, and real‑world trade‑offs  
> **Stack**: Ruby on Rails API + FastAPI (Python) + Next.js frontend  
> **Terminology**: “LLM” refers to any Large Language Model backend (OpenAI, Anthropic, self‑hosted, etc.)

---

## 1. Why LLM integration is *not* just “add a chat endpoint”

Adding an LLM to a production system introduces **new architectural dimensions**:

- Long‑lived connections (streaming)
- Token‑based billing & metering
- Session state that spans services
- Mixed latency profiles (milliseconds vs seconds)
- Security boundaries between app code and AI code
- Failure modes that didn’t exist before

This article shows **how to integrate LLM chat correctly**, without breaking your existing Rails architecture.

---

## 2. Baseline system assumptions

We assume a mature Rails API with:

- Devise + JWT authentication
- Pundit authorization
- Centralized billing / credits
- Redis + Sidekiq
- ActionCable available
- Next.js frontend
- A dedicated FastAPI service that:
  - Runs LLM inference
  - Handles embeddings / vector search
  - Stores conversation state (e.g. MongoDB)

---

## 3. Integration patterns overview

### Option A — Rails API Gateway (Recommended starting point)

**Rails is the single public entry point.**

```
Frontend → Rails API → FastAPI (internal)
```

Rails handles:
- Auth & authorization
- Billing & credits
- Input validation
- Auditing
- Session ownership

FastAPI focuses only on:
- LLM logic
- Intent classification
- Vector search
- Streaming tokens

**Best for**
- Security‑first systems
- Centralized billing
- Small to medium scale
- Teams already invested in Rails

**Trade‑off**
- +1 network hop (~30–50ms)
- Rails threads involved in streaming

---

### Option B — Shared JWT / Direct Access

**Frontend talks directly to FastAPI for LLM calls.**

```
Frontend → Rails (auth, token)
Frontend → FastAPI (LLM, streaming)
```

Rails issues short‑lived **LLM tokens** (JWT).

**Best for**
- Ultra‑low latency streaming
- 100+ concurrent streams
- Independent LLM scaling

**Trade‑off**
- FastAPI becomes public
- JWT secret sharing
- Post‑facto billing via webhooks

---

### Option C — Service Mesh (Istio / Linkerd)

**Infrastructure handles auth, routing, retries.**

```
Frontend → Istio → Rails / FastAPI
```

**Best for**
- Kubernetes‑native teams
- Zero‑trust networking
- Built‑in tracing (Jaeger, Prometheus)

**Trade‑off**
- High infra complexity
- Overkill for 2–3 services

---

### Option D — Message Queue (Async / Batch)

**Non‑interactive LLM workloads.**

```
Frontend → Rails → Queue → FastAPI Workers
```

Results delivered via:
- Webhooks
- Polling
- ActionCable

**Best for**
- Batch analysis
- “Analyze 500 profiles”
- Long‑running jobs

**Not suitable for**
- Interactive chat UX

---

## 4. Streaming architecture (SSE)

### Why SSE (not WebSockets)?

- Simple
- HTTP‑native
- Works well with proxies
- Perfect for token streams

### Streaming flow (Option A)

```
Frontend ──► Rails (SSE)
              └──► FastAPI (SSE)
FastAPI streams tokens
Rails forwards tokens
Frontend renders incrementally
```

### Rails streaming controller (simplified)

```ruby
class LlmStreamsController < ApplicationController
  include ActionController::Live

  def stream
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"

    sse = SSE.new(response.stream)

    FastapiStreamingClient.stream(query: params[:query]) do |chunk|
      sse.write(chunk)
    end
  ensure
    sse.close
  end
end
```

### FastAPI streaming endpoint

```python
@router.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    async for token in llm.stream(request.query):
        yield f"data: {json.dumps({'content': token})}\n\n"
```

---

## 5. Session management (cross‑service)

**Rule**: Only one system owns session state.

Recommended:
- FastAPI owns conversation history (MongoDB)
- Rails mirrors minimal session metadata:
  - session_id
  - last_activity_at
  - credits_used
  - user_id / company_id

Rails never reconstructs chat history — it **queries FastAPI**.

---

## 6. Billing & credit safety

### Option A (Gateway)

- Credits checked **before** request
- Deducted synchronously
- Request fails if insufficient

### Option B (Direct)

- FastAPI reports usage via webhook
- Rails reconciles asynchronously
- Periodic reconciliation job required

### Option D (Queue)

- Credits reserved upfront
- Released or finalized on completion

---

## 7. Error handling strategy

| Scenario | Strategy |
|--------|---------|
| No results | Friendly LLM response |
| Invalid filters | Structured validation error |
| FastAPI timeout | 504 + retry advice |
| Session not found | Graceful fallback |
| Streaming disconnect | Safe cleanup |
| LLM crash | Circuit breaker / retry |

Always attach:
- `request_id`
- `session_id`
- `response_time_ms`

---

## 8. Security boundaries

### Do
- Keep FastAPI private if possible
- Validate all inputs in Rails
- Use short‑lived tokens
- Log usage, not prompts
- Enforce scopes

### Avoid
- Exposing raw LLM APIs publicly
- Sharing long‑lived secrets
- Letting frontend call OpenAI directly
- Mixing billing logic into FastAPI

---

## 9. Decision matrix

| Requirement | Best Option |
|-----------|-------------|
| Fastest time‑to‑market | Option A |
| Best streaming performance | Option B |
| Best security | Option A / C |
| Kubernetes native | Option C |
| Batch workloads | Option D |
| Hybrid system | A + D |
| Future‑proof | A → Hybrid → B |

---

## 10. Recommended evolution path

```
Start: Option A (Gateway)
↓
Add Option D for batch jobs
↓
If streaming becomes bottleneck:
→ Hybrid (Rails auth + FastAPI streaming)
↓
If scale demands:
→ Option B or Service Mesh
```

---

## 11. Key takeaway

**LLM integration is a system design problem, not a controller problem.**

If you:
- Centralize auth
- Treat streaming as first‑class
- Separate billing from inference
- Respect service boundaries

…you get an AI feature that **scales with your product**, not against it.

---

## Appendix

- SSE vs WebSockets comparison
- JWT vs OAuth trade‑offs
- Credit reconciliation strategies
- Observability checklists

---

*Author: Engineering Architecture Notes*  
*Last updated: 2025*
