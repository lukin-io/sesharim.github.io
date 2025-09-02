---
layout: post
title:  Principles for Writing Maintainable Code
date:   2020-09-12 12:00:00
<!-- categories: jekyll update -->
<!-- tags: ruby rails -->
author: Max Lukin
<!-- excerpt: How to create your own simple blog -->
---
Applications always change. This post collects **practical principles and Rails‑friendly patterns** I use to keep code maintainable over the long run—leaning on Ruby on Rails conventions, small POROs, and simple seams you can scale as your app (or game) grows.

> **What’s new in this revision?**
> It expands the original article with concrete Rails examples, explains how to apply the ideas in production code, and adds a checklist you can drop into your workflow *today*. It also aligns examples with a modern Rails monolith (Hotwire/Turbo, API responses via Blueprinter, presenters, and snake_case JSON keys).

---

## At a glance: the roadmap

1. **Foundations** — KISS, DRY, YAGNI, SOLID, Law of Demeter, TRUE, Rails Way, PORO.
2. **Rails‑friendly “seams”** — Query Objects (CQS), Service Objects (idempotent + transactional), Domain Events, Ports & Adapters.
3. **Presentation boundaries** — Blueprinter & Presenters for clean JSON/UI separation.
4. **Safety & speed** — Transactions, invariants, observability, performance, security.
5. **Tests & docs** — BDD/TDD, contract tests, ADRs.
6. **How to use these in your app** — short, copy‑paste examples.
7. **Checklist** — adopt in small steps.

---

# 1) Foundations

Below, each principle is shown as **Action → Rule → Example → Explanation**.

### 1.1 KISS (Keep it simple, stupid) [Rail’s way of saying “convention over configuration”]
**Action →** Prefer the obvious Rails convention before inventing a custom abstraction.
**Rule →** Reach for generators, models, concerns, presenters before custom frameworks.
**Example →** Don’t build a custom background job runner when Active Job + Sidekiq works.
**Explanation →** Simplicity reduces maintenance and makes it easy for teammates to help.

### 1.2 DRY (Don’t Repeat Yourself) [dry]
**Action →** Extract *stable* duplication—the stuff that’s obviously the same.
**Rule →** Duplicate twice, abstract on the third (see AHA/Rule‑of‑Three below).
**Example →** Extract shared JSON serialization into a Blueprint (see §3).
**Explanation →** DRY keeps behavior consistent and reduces bug surface area.

### 1.3 YAGNI (You Aren’t Gonna Need It) [yagni] + AHA (Avoid Hasty Abstractions)
**Action →** Ship the simplest thing that works for the next milestone.
**Rule →** Prefer a small, local duplication over a premature base class.
**Example →** Keep `MeleeDamageCalculator` and `MagicDamageCalculator` separate until a third type appears.
**Explanation →** You can always generalize later—after you see the real pattern.

### 1.4 SOLID (OO design guardrails)
**Action →** Design objects with one job, and depend on interfaces, not implementations.
**Rule →** SRP, OCP, LSP, ISP, DIP guide refactors and extensions.
**Example →** A `GrantGold` service updates balances; it *publishes* an event instead of directly sending notifications (DIP).
**Explanation →** SOLID keeps modules extensible without ripple effects.

### 1.5 Law of Demeter (LoD)
**Action →** Ask objects to *do things*; avoid “train‑wreck” calls (`a.b.c.d`).
**Rule →** Talk to friends, not strangers; hide internal structure.
**Example →** Provide `character.inventory.overweight?` instead of summing item weights externally.
**Explanation →** Reduces coupling and eases refactors.

### 1.6 TRUE Code (Transparent, Reasonable, Usable, Exemplary)
**Action →** Make the consequences of change obvious and local.
**Rule →** Favor small, well‑named methods and data structures.
**Example →** A Query Object that says what it returns in its name and docstring.
**Explanation →** TRUE code supports today’s features and tomorrow’s changes.

### 1.7 Rails Way + PORO
**Action →** Start with Rails primitives; move domain logic to POROs as it grows.
**Rule →** Keep controllers thin, models focused, services/presenters clear.
**Example →** Business rules in `app/services/…` and `app/queries/…`, rendering in Blueprints/Presenters.
**Explanation →** Balances Rails productivity with separation of concerns.

---

# 2) Rails‑friendly “seams”

## 2.1 Query Objects (CQS: separate reads from writes)
**Action →** Put non‑trivial reads in PORO query objects; commands mutate, queries don’t.

**`app/queries/top_guilds_by_power_query.rb`**
```ruby
# Example usage:
#   TopGuildsByPowerQuery.call(limit: 10)
# Returns:
#   ActiveRecord::Relation<Guild> ordered by total_power desc, limited.
class TopGuildsByPowerQuery
  def self.call(limit:)
    Guild.select('guilds.*, SUM(players.power) AS total_power')
         .joins(:players)
         .group('guilds.id')
         .order('total_power DESC')
         .limit(limit)
  end
end
```

## 2.2 Service Objects (idempotent, transactional)
**Action →** Wrap side‑effects in a single transaction; make them safe to retry.

**`app/models/idempotency_key.rb`**
```ruby
class IdempotencyKey < ApplicationRecord
  validates :key, presence: true, uniqueness: true
end
# Migration: add_index :idempotency_keys, :key, unique: true
```

**`app/services/economy/grant_gold.rb`**
```ruby
module Economy
  class GrantGold
    # Example usage:
    #   Economy::GrantGold.call(
    #     player_id: 42,
    #     amount: 100,
    #     key: "grant_gold:quest:123:player:42"
    #   )
    # Returns:
    #   Player (updated) if applied; Player (unchanged) if idempotency key was already used.
    def self.call(player_id:, amount:, key:)
      new(player_id, amount, key).call
    end

    def initialize(player_id, amount, key)
      @player_id, @amount, @key = player_id, amount, key
    end

    def call
      ApplicationRecord.transaction do
        IdempotencyKey.create!(key: @key) # raises if reused
        player = Player.lock.find(@player_id)
        player.update!(current_gold: player.current_gold + @amount)
        DomainEvents.publish('economy.gold_granted',
                             player_id: player.id,
                             amount: @amount,
                             key: @key)
        player
      end
    rescue ActiveRecord::RecordNotUnique
      Player.find(@player_id) # no‑op: already granted
    end
  end
end
```

## 2.3 Domain Events (decouple via publish/subscribe)
**Action →** Publish high‑level events; let subscribers react independently.

**`app/lib/domain_events.rb`**
```ruby
module DomainEvents
  def self.publish(name, payload = {})
    ActiveSupport::Notifications.instrument(name, payload)
  end

  def self.subscribe(name, &block)
    ActiveSupport::Notifications.subscribe(name) do |*args|
      event = ActiveSupport::Notifications::Event.new(*args)
      block.call(event.payload)
    end
  end
end
```

**`app/subscribers/analytics/economy_subscriber.rb`**
```ruby
module Analytics
  class EconomySubscriber
    def self.boot!
      DomainEvents.subscribe('economy.gold_granted') do |payload|
        Rails.logger.info(event: 'gold_granted',
                          player_id: payload[:player_id],
                          amount: payload[:amount])
      end
    end
  end
end
```

**`config/initializers/subscribers.rb`**
```ruby
Analytics::EconomySubscriber.boot!
```

## 2.4 Ports & Adapters (hexagonal‑lite)
**Action →** Depend on interfaces; swap adapters at the edges.

**`app/interfaces/notifiers/global_notifier.rb`**
```ruby
module Notifiers
  class GlobalNotifier
    # Example usage:
    #   Notifiers::ActionCableNotifier.new.broadcast("Server restart in 5 minutes")
    # Returns:
    #   void
    def broadcast(_message) = raise NotImplementedError
  end
end
```

**`app/adapters/notifiers/action_cable_notifier.rb`**
```ruby
module Notifiers
  class ActionCableNotifier < GlobalNotifier
    def broadcast(message)
      ActionCable.server.broadcast('global', message:)
    end
  end
end
```

---

# 3) Presentation boundaries (JSON/UI)

**Goal:** Keep API/UI code out of domain logic; keep JSON keys **snake_case** to match DB fields.

**`app/blueprints/player_blueprint.rb`**
```ruby
class PlayerBlueprint < Blueprinter::Base
  identifier :id

  field :name do |player|
    player.name
  end

  field :current_gold do |player|
    player.current_gold
  end

  field :level do |player|
    player.level
  end
end
```

**Presenter example (namespaced path):**
**`app/presenters/avatars/predefined_avatar.rb`**
```ruby
module Avatars
  class PredefinedAvatar
    def initialize(code)
      @code = code
    end

    def url
      "/images/avatars/#{@code}.png"
    end
  end
end
```

---

# 4) Safety, speed & operability

## 4.1 Transactions, concurrency & invariants
- Wrap multi‑row updates in a transaction.
- Lock rows you read‑modify‑write (e.g., `Player.lock.find`).
- Keep invariant checks close to the data (model validations + DB constraints).

## 4.2 Observability
- Add `config.log_tags = [:request_id]` in `config/environments/production.rb`.
- Prefer structured logs: `Rails.logger.info(event: 'battle_started', player_ids: [p1.id, p2.id])`.
- Publish domain events for key actions (see §2.3).

## 4.3 Performance guardrails
- Paginate by default; beware N+1 (use `includes`).
- Cache read‑heavy endpoints; memoize inside request scope.
- Budget queries per request; measure with logs.

## 4.4 Security defaults
- Validate/whitelist params; **never** map camelCase to snake_case in controllers—use native `snake_case` everywhere.
- Least‑privilege roles; rate‑limit sensitive endpoints.

---

# 5) Tests & documentation

## 5.1 BDD/TDD (short feedback loops)
- Drive services/queries with fast unit tests.
- Add a few request/system tests for the happy path.
- Use contract tests around external ports (adapters).

## 5.2 Documentation‑as‑code
- Keep lightweight ADRs in `doc/adr/` to record decisions.
- Add README.md per top‑level folder explaining responsibilities.

---

# 6) How you’ll call this from your app

**Grant gold from a controller**
**`app/controllers/economy/gold_grants_controller.rb`**
```ruby
module Economy
  class GoldGrantsController < ApplicationController
    def create
      player = Economy::GrantGold.call(
        player_id: params[:player_id],
        amount: params[:amount].to_i,
        key: "quest:#{params[:quest_id]}:grant_gold:player:#{params[:player_id]}"
      )

      render json: PlayerBlueprint.render(player) # snake_case keys
    end
  end
end
```

**Use a query object in a controller**
**`app/controllers/guilds_controller.rb`**
```ruby
class GuildsController < ApplicationController
  def index
    limit   = params.fetch(:limit, 10).to_i
    @guilds = TopGuildsByPowerQuery.call(limit: limit)
  end
end
```

**Notify via a port (adapter injected where needed)**
```ruby
notifier = Notifiers::ActionCableNotifier.new
notifier.broadcast("Double XP weekend starts now!")
```

---

# 7) Adoption checklist

- [ ] Create `app/services/`, `app/queries/`, `app/interfaces/`, `app/adapters/`, `app/subscribers/`, `app/blueprints/`, `app/presenters/`.
- [ ] Add `IdempotencyKey` + unique index on `key`.
- [ ] Convert one heavy controller scope into a **Query Object**.
- [ ] Wrap one risky write in a **Service** with transaction + row lock.
- [ ] **Publish one Domain Event** and log a subscriber reaction.
- [ ] Introduce one **Port** (notifier) and one **Adapter** (ActionCable).
- [ ] Move one JSON response to **Blueprinter** (multi‑line fields).
- [ ] Turn on structured logging with `request_id`.
- [ ] Delete obsolete files after refactors (keep PRs small and reversible).

---

*Eating your own dog food* matters too—use your own API/UI flows end‑to‑end to feel the rough edges daily. [eyodf]

---

[dry]: https://en.wikipedia.org/wiki/Don%27t_repeat_yourself
[kiss]: https://en.wikipedia.org/wiki/KISS_principle
[yagni]: https://en.wikipedia.org/wiki/You_aren%27t_gonna_need_it
[eyodf]: https://en.wikipedia.org/wiki/Eating_your_own_dog_food
