---
layout: post
title: "Building a Browser-Based MMORPG with Ruby on Rails: Documentation-Driven Development with AI"
date: 2025-11-27
tags: [rails, mmorpg, game-development, hotwire, actioncable, ai, documentation, architecture]
categories: [engineering, rails, game-development, AI]
description: A comprehensive guide to building a turn-based browser MMORPG using Ruby on Rails, Hotwire, and AI-assisted development. Learn how documentation-driven workflows, feature decomposition, and "inspired-by" patterns enable rapid development of complex game systems.
author: Max Lukin
---

> _"The hardest part of building a game isn't the code—it's keeping 50+ interconnected systems coherent while shipping features fast."_

Most game development tutorials show you how to build a simple demo. Real games need **authentication**, **real-time combat**, **economies**, **social systems**, **moderation**, and dozens of other features that must work together seamlessly.

In this post, I'll share our experience building **Elselands**—a browser-based, turn-based MMORPG inspired by classic games like Neverlands.ru. We'll cover:

- **Documentation-driven development** that scales with complexity
- **Feature decomposition** from Game Design Document to implementation
- **Flow documentation** as the source of truth for implementation
- **"Inspired-by" patterns** for borrowing proven mechanics
- **Testing strategies** for game systems
- **AI-assisted development** that actually works for senior engineers
- **Practical lessons** from building 100+ interconnected systems

---

## 1. The Challenge: Building an MMORPG as a Rails Monolith

### 1.1 Why Rails for a Game?

Browser-based MMORPGs have unique requirements:

| Requirement | Why Rails Works |
|-------------|-----------------|
| Server-authoritative logic | All game state lives in PostgreSQL, no client-side cheating |
| Real-time updates | ActionCable + Redis pub/sub handles chat, combat, presence |
| Rapid iteration | Convention over configuration means less boilerplate |
| Rich UI without SPA complexity | Hotwire (Turbo + Stimulus) delivers reactive UIs server-side |
| Moderation & admin tools | ActiveAdmin, Flipper, audit logging come free |

Our stack:

- **Ruby 3.4.4 + Rails 8.1.1** (full-stack Hotwire monolith)
- **PostgreSQL 18** (primary datastore)
- **Redis** (cache, Action Cable, Sidekiq)
- **Hotwire** (Turbo Frames, Turbo Streams, Stimulus)
- **Sidekiq 8** (background jobs for combat/chat/events)

### 1.2 The Complexity Problem

A typical MMORPG has:

- 10+ major systems (auth, combat, economy, crafting, quests, etc.)
- 50+ models with complex relationships
- Hundreds of services, jobs, and controllers
- Real-time features requiring WebSockets
- Moderation, analytics, and admin tooling

Without a structured approach, this becomes unmaintainable. We solved it with **documentation-driven development**.

---

## 2. Documentation-Driven Development: From GDD to Implementation

### 2.1 The Documentation Hierarchy

We structured our documentation in three layers:

```
doc/
├── design/
│   └── gdd.md              # Game Design Document (WHAT we're building)
├── features/
│   ├── 0_technical.md      # Infrastructure & architecture
│   ├── 1_auth.md           # Authentication & accounts
│   ├── 3_player.md         # Character systems
│   ├── 8_gameplay_mechanics.md
│   └── ...                 # One file per major system
└── flow/
    ├── 0_technical.md      # HOW each feature is implemented
    ├── 1_auth_presence.md
    ├── 8_gameplay_mechanics.md
    └── ...                 # Implementation details with file references
```

**Key insight:** The GDD tells you *what* to build. Feature docs break it into *systems*. Flow docs tell you *exactly how* it's implemented.

### 2.2 The Game Design Document (GDD)

Our GDD is intentionally high-level:

```markdown
## Gameplay Mechanics
- **Player Movement**
  - Tile-based grid movement
  - Turn-based actions per player input

- **Combat System**
  - PvE: Encounters against monsters and NPCs
  - PvP: Player duels, group battles, arena tournaments

- **Character Progression**
  - Experience points and leveling
  - Stat points allocation per level
  - Reputation and faction alignment
```

This is the **north star**—it never mentions implementation details like controllers or database schemas. It's what you show stakeholders and use for high-level planning.

### 2.3 Feature Documentation: Breaking Down the GDD

Each major system gets its own feature doc (`doc/features/*.md`):

```markdown
# 8_gameplay_mechanics.md

## Player Movement
- Grid-based tile system with terrain modifiers
- Turn-per-action enforcement (server-side)
- Cooldown multipliers for different terrain types
- Spawn points and respawn timers

## Combat System
- Turn-based initiative order
- Body-part targeting (head, torso, stomach, legs)
- Action points and mana management
- Status effects and buff/debuff system
```

Feature docs are **implementation-ready specifications**—detailed enough that an engineer knows what to build, but not yet tied to specific files.

### 2.4 Flow Documentation: The Implementation Source of Truth

**This is where the magic happens.** Flow docs (`doc/flow/*.md`) describe *exactly* how each feature is implemented:

```markdown
# 8_gameplay_mechanics.md — Flow Documentation

## Combat Skill System

### Use Case: Player uses a skill during combat
1. Player clicks skill icon → `turn_combat_controller.js#useSkill()`
2. Stimulus sends action to `CombatController#action`
3. `TurnBasedCombatService` validates action points and mana
4. `Game::Combat::SkillExecutor` applies skill effects
5. `CombatLogEntry` records the action
6. Turbo Stream broadcasts update to all participants

### Key Behaviors
- Skills consume both action points AND mana slots
- Body-part targeting affects damage multipliers
- Critical hits based on agility vs target defense

### Responsible for Implementation Files
| Purpose | File |
|---------|------|
| Combat service | `app/services/game/combat/turn_based_combat_service.rb` |
| Skill executor | `app/services/game/combat/skill_executor.rb` |
| Stimulus controller | `app/javascript/controllers/turn_combat_controller.js` |
| Combat view | `app/views/combat/_battle.html.erb` |
| Action config | `config/gameplay/combat_actions.yml` |
```

**Why flow docs matter:**

1. **Context preservation** — When returning to a feature after weeks, you know exactly where everything is
2. **AI assistance** — Feed the flow doc to your AI assistant, and it understands the entire system
3. **Onboarding** — New engineers can trace any feature from UI to database
4. **Code review** — Reviewers can verify changes match the documented architecture

---

## 3. The "Inspired-By" Pattern: Borrowing Proven Mechanics

### 3.1 Why Reinvent the Wheel?

Classic games like Neverlands.ru have battle-tested UI/UX patterns. Instead of designing from scratch, we:

1. **Analyze** the original implementation (JavaScript, CSS, HTML)
2. **Document** the original patterns in `doc/features/neverlands_inspired.md`
3. **Adapt** to modern Rails/Hotwire patterns
4. **Track** implementation status

### 3.2 Example: Turn-Based Combat System

We received this Neverlands JavaScript:

```javascript
// Original Neverlands combat logic
function CountOD() {
  var totalOD = 0;
  for (var i = 0; i < 10; i++) {
    if (pos_atk[i] > 0) totalOD += pos_ochd[pos_atk[i]];
    if (pos_blk[i] > 0) totalOD += pos_ochd[pos_blk[i]];
  }
  // pos_ochd contains action point costs per body part
  return totalOD;
}

// Body part configuration
var pos_vars = ['', 'Head', 'Torso', 'Stomach', 'Groin', 'Left Leg', 'Right Leg'];
var pos_ochd = [0, 3, 2, 2, 2, 2, 2]; // Action point costs
```

### 3.3 Our Adaptation

We translated this to a Rails service with YAML configuration:

```yaml
# config/gameplay/combat_actions.yml
body_parts:
  head:
    action_cost: 3
    damage_multiplier: 1.5
    block_bonus: 0.8
  torso:
    action_cost: 2
    damage_multiplier: 1.0
    block_bonus: 1.0
  stomach:
    action_cost: 2
    damage_multiplier: 1.1
    block_bonus: 0.9
```

```ruby
# app/services/game/combat/turn_based_combat_service.rb
class Game::Combat::TurnBasedCombatService
  def initialize(battle)
    @battle = battle
    @config = YAML.load_file(Rails.root.join("config/gameplay/combat_actions.yml"))
  end

  def calculate_action_points_used(attacks, blocks)
    total = 0
    attacks.each { |part| total += @config.dig("body_parts", part, "action_cost") || 2 }
    blocks.each { |part| total += @config.dig("body_parts", part, "action_cost") || 2 }
    total
  end
end
```

And a Stimulus controller replacing the inline JavaScript:

```javascript
// app/javascript/controllers/turn_combat_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["attackSelect", "blockSelect", "actionPoints", "submitButton"]
  static values = { maxActions: Number, config: Object }

  connect() {
    this.updateActionPoints()
  }

  updateActionPoints() {
    const used = this.calculateUsedPoints()
    const remaining = this.maxActionsValue - used

    this.actionPointsTarget.textContent = `${remaining}/${this.maxActionsValue}`
    this.submitButtonTarget.disabled = remaining < 0
  }

  calculateUsedPoints() {
    let total = 0
    this.attackSelectTargets.forEach(select => {
      if (select.value) total += this.configValue.body_parts[select.value]?.action_cost || 2
    })
    this.blockSelectTargets.forEach(select => {
      if (select.value) total += this.configValue.body_parts[select.value]?.action_cost || 2
    })
    return total
  }
}
```

### 3.4 Documentation Structure for Inspired Features

We maintain a dedicated file tracking all borrowed patterns:

```markdown
# doc/features/neverlands_inspired.md

## Implementation Status Summary

| # | Feature | Status | Key Files |
|---|---------|--------|-----------|
| 1 | Chat System | ✅ Implemented | `chat_controller.js`, `moderation_service.rb` |
| 2 | Arena/PvP | ✅ Implemented | `arena_controller.rb`, `matchmaker.rb` |
| 3 | Turn-Based Combat | ✅ Implemented | `turn_based_combat_service.rb` |
| 4 | Combat Log | ✅ Implemented | `log_builder.rb`, `statistics_calculator.rb` |

## Chat System

### Original Neverlands Examples
[Original JavaScript code here]

### Elselands Implementation
- **Files:** `chat_controller.js`, `realtime_chat_channel.rb`
- **Key Adaptations:**
  - Replaced `onclick` with Stimulus `data-action`
  - WebSocket via ActionCable instead of polling
  - Server-side moderation before broadcast
```

**Benefits:**

1. **Reference material** — Original examples are preserved for future iterations
2. **Implementation tracking** — Clear status of what's done vs. planned
3. **Knowledge transfer** — Anyone can understand why we made certain choices

---

## 4. Testing Strategies for Game Systems

### 4.1 Test Categories

Game systems require different testing strategies than typical CRUD apps:

| Category | Purpose | Example |
|----------|---------|---------|
| **Unit Tests** | Individual service logic | `TurnBasedCombatService` action point calculation |
| **Request Tests** | API endpoints | `POST /combat/action` with attack data |
| **Channel Tests** | WebSocket functionality | `BattleChannel` broadcasts updates |
| **Helper Tests** | View helpers | `format_combat_log_message` output |
| **System Tests** | End-to-end flows | Full combat from start to victory |

### 4.2 Testing Real-Time Features

ActionCable channels need special setup:

```ruby
# spec/channels/battle_channel_spec.rb
require "rails_helper"

RSpec.describe BattleChannel, type: :channel do
  let(:user) { create(:user) }
  let(:battle) { create(:battle) }

  before do
    stub_connection current_user: user
  end

  it "subscribes to battle stream" do
    subscribe(battle_id: battle.id)
    expect(subscription).to be_confirmed
    expect(subscription).to have_stream_for(battle)
  end

  it "receives combat updates" do
    subscribe(battle_id: battle.id)

    expect {
      BattleChannel.broadcast_to(battle, { type: "turn_update", round: 1 })
    }.to have_broadcasted_to(battle)
  end
end
```

### 4.3 Testing Deterministic Combat

Combat must be reproducible for debugging and replays:

```ruby
# spec/services/game/combat/turn_based_combat_service_spec.rb
RSpec.describe Game::Combat::TurnBasedCombatService do
  let(:battle) { create(:battle, :with_participants) }
  let(:service) { described_class.new(battle) }

  describe "#submit_turn" do
    it "consumes action points correctly" do
      attacks = [{ body_part: "head" }, { body_part: "torso" }]
      blocks = [{ body_part: "stomach" }]

      # Head (3) + Torso (2) + Stomach (2) = 7 action points
      expect(service.calculate_action_points_used(attacks, blocks)).to eq(7)
    end

    context "with seeded RNG for reproducibility" do
      it "produces consistent damage rolls" do
        Game::Utils::Rng.seed(12345)

        result1 = service.resolve_attack(attacker, defender, "head")
        Game::Utils::Rng.seed(12345)
        result2 = service.resolve_attack(attacker, defender, "head")

        expect(result1[:damage]).to eq(result2[:damage])
      end
    end
  end
end
```

### 4.4 Coverage Goals

We maintain explicit coverage targets:

| Category | Target | Rationale |
|----------|--------|-----------|
| Models | 90% | Core game logic lives here |
| Services | 95% | Business logic must be bulletproof |
| Controllers | 85% | Request/response handling |
| Channels | 80% | Real-time features are critical |
| Helpers | 90% | UI consistency |
| Views | 60% | Basic rendering verification |
| System | 40% | Key user flows |

---

## 5. AI-Assisted Development: Making It Work for Senior Engineers

### 5.1 The Problem with Generic AI Assistance

Most AI coding assistants fail on complex projects because they lack:

- **Project context** — They don't know your architecture
- **Convention awareness** — They generate code that doesn't match your style
- **Domain knowledge** — They don't understand game mechanics

### 5.2 Our Solution: Structured Prompting with Documentation

We created a documentation hierarchy that the AI can reference:

```markdown
# README.md (excerpt)

## 📄 Documentation Map

| File | When to Reference / Purpose |
|------|----------------------------|
| **AGENT.md** | Always loaded, highest authority |
| **GUIDE.md** | Rails standards or general best practices |
| **MMO_ADDITIONAL_GUIDE.md** | Gameplay/MMORPG domain-specific conventions |
| **doc/gdd.md** | Game design vision, classes, mechanics |
| **doc/features/*.md** | Per-system breakdown (technical specs) |
| **doc/flow/*.md** | Implementation details with file references |
```

### 5.3 Effective Prompting Patterns

**Pattern 1: Feature Implementation**

```markdown
I want to start implementing the Player feature from `doc/features/3_player.md`.

Please follow:
- `AGENT.md` (always)
- `GUIDE.md` for general Rails patterns
- `MMO_ADDITIONAL_GUIDE.md` for gameplay logic architecture
- Use `MMO_ENGINE_SKELETON.md` for engine placement

**Task:**
1. Read `doc/features/3_player.md`
2. Identify required models, services, and UI components
3. Provide a detailed plan (files + responsibilities)
4. Wait for my confirmation before writing any code
```

**Pattern 2: Inspired-By Implementation**

```markdown
Here's the Neverlands JavaScript for their arena system:
[paste code]

Please:
1. Analyze the original implementation
2. Document it in `doc/features/neverlands_inspired.md`
3. Propose a Rails/Hotwire adaptation using our patterns
4. Update flow docs with implementation details
```

**Pattern 3: Bug Fix with Context**

```markdown
I'm seeing this error in the arena system:
[paste error]

Context:
- Check `doc/flow/11_arena_pvp.md` for the arena architecture
- The ArenaMatch model uses an enum that might conflict

Find the root cause and propose a fix that matches our conventions.
```

### 5.4 Why This Works for Senior Engineers

1. **You drive the architecture** — AI implements your decisions, doesn't make them
2. **Documentation is the contract** — Changes must match documented patterns
3. **Context is preserved** — Flow docs keep AI informed across sessions
4. **Code review is efficient** — You verify against documented expectations

### 5.5 Prompts That Accelerate Development

**For rapid prototyping:**
```markdown
Using AGENT.md rules, implement the next step from doc/features/3_player.md.
Use GUIDE.md for Rails logic, and MMO_ADDITIONAL_GUIDE.md for gameplay structure.
Touch only the necessary files.
```

**For code quality:**
```markdown
After implementation, run:
1. `bundle exec rspec` for tests
2. `bundle exec standardrb` for linting
3. `bundle exec brakeman` for security

Fix any issues before considering this complete.
```

**For documentation updates:**
```markdown
Update the corresponding flow doc (`doc/flow/X.md`) with:
- Use cases covered
- Key behaviors implemented
- Responsible files table
```

---

## 6. Practical Lessons from 100+ Systems

### 6.1 What Worked

**1. Flow docs as the source of truth**

Every PR must update the relevant flow doc. This creates a living architecture document that's always accurate.

**2. "Responsible Files" tables in flow docs**

```markdown
### Responsible for Implementation Files
| Purpose | File |
|---------|------|
| Combat service | `app/services/game/combat/turn_based_combat_service.rb` |
| Controller | `app/controllers/combat_controller.rb` |
| Stimulus | `app/javascript/controllers/turn_combat_controller.js` |
```

This makes it trivial to find code when debugging or extending features.

**3. YAML configuration for game data**

Instead of hardcoding values, we use `config/gameplay/*.yml`:

- `combat_actions.yml` — Body parts, action costs, multipliers
- `terrain_modifiers.yml` — Movement cooldowns by terrain
- `biomes.yml` — Encounter tables by region

Changes don't require code deployments, and game designers can read/modify the configs.

**4. Turbo Streams for real-time without complexity**

Instead of building a custom WebSocket protocol:

```ruby
# Broadcasting combat updates
Turbo::StreamsChannel.broadcast_update_to(
  @battle,
  target: "combat-log",
  partial: "combat_logs/entry",
  locals: { entry: log_entry }
)
```

The frontend gets updates automatically without custom JavaScript.

### 6.2 What We'd Do Differently

**1. Start with comprehensive factories earlier**

We had to backfill factories for models like `NpcTemplate`, `WebhookEndpoint`, etc. Building factories alongside models saves debugging time.

**2. Enum naming requires foresight**

ActiveRecord reserves certain method names (`group`, `order`, etc.). We had to rename `fight_type: :group` to `fight_type: :team_battle` to avoid conflicts.

**3. Migration idempotency from day one**

Adding `if column_exists?` checks to migrations would have prevented issues when re-running migrations:

```ruby
def change
  unless column_exists?(:battles, :share_token)
    add_column :battles, :share_token, :string
  end
end
```

### 6.3 Performance Considerations

**Real-time features need Redis pub/sub:**

```yaml
# config/cable.yml
production:
  adapter: redis
  url: <%= ENV.fetch("REDIS_CABLE_URL") %>
  channel_prefix: elselands_production
```

**Separate Redis instances for different concerns:**

| Purpose | Environment Variable |
|---------|---------------------|
| Rails cache | `REDIS_CACHE_URL` |
| Sidekiq queues | `REDIS_SIDEKIQ_URL` |
| Action Cable | `REDIS_CABLE_URL` |

This prevents a Sidekiq backup from affecting real-time chat.

---

## 7. The Complete Development Workflow

### 7.1 Adding a New Feature

```
1. GDD → Does this feature align with the game vision?
       ↓
2. Feature Doc → Create doc/features/X.md with:
   - System requirements
   - User-facing functionality
   - Integration points
       ↓
3. Flow Doc → Create doc/flow/X.md with:
   - Use cases (step-by-step flows)
   - Key behaviors
   - "Responsible Files" table (initially planned)
       ↓
4. Implementation → Using AI + documentation:
   - Generate models/migrations
   - Create services with tests
   - Build controllers and views
   - Add Stimulus controllers for interactivity
       ↓
5. Testing → Run full test suite:
   - bundle exec rspec
   - bundle exec standardrb
   - bundle exec brakeman
       ↓
6. Documentation Update → Update flow doc with:
   - Actual file paths
   - Implementation notes
   - Any deviations from plan
```

### 7.2 Debugging with Documentation

When something breaks:

1. **Find the flow doc** for that feature
2. **Trace the use case** — Which step is failing?
3. **Check the "Responsible Files"** — Go directly to the right code
4. **Verify against "Key Behaviors"** — Is the code doing what it should?

### 7.3 Onboarding New Engineers

1. Read `README.md` for project overview
2. Read `AGENT.md` and `GUIDE.md` for conventions
3. Pick a feature, read its flow doc
4. Trace from UI to database using "Responsible Files"
5. Make a small change, run tests, verify

---

## 8. Conclusion: Documentation as a Force Multiplier

Building a complex game is hard. Building it fast and maintaining quality is harder. Our documentation-driven approach made it possible:

| Challenge | Solution |
|-----------|----------|
| Keeping 100+ systems coherent | Feature docs define boundaries |
| Finding code in a large codebase | Flow docs with "Responsible Files" |
| Preserving context across sessions | Flow docs are always up-to-date |
| Effective AI assistance | Structured prompts with documentation |
| Onboarding new engineers | Self-documenting architecture |
| Borrowing proven patterns | "Inspired-by" documentation |

The upfront investment in documentation pays dividends throughout the project. Every hour spent documenting saves five hours of confusion later.

### Key Takeaways

1. **GDD → Features → Flows** creates a traceable path from vision to implementation
2. **Flow docs with "Responsible Files"** make code discoverable
3. **"Inspired-by" patterns** let you borrow proven mechanics responsibly
4. **AI works best with structured context** — feed it your documentation
5. **Tests are non-negotiable** for game systems with complex interactions
6. **YAML configuration** separates game data from code logic

Whether you're building an MMORPG, a complex SaaS, or any large Rails application, these patterns will help you ship faster while maintaining quality.

---

## Resources

- **Rails 8.1 + Hotwire**: [hotwired.dev](https://hotwired.dev)
- **ActionCable Guide**: [guides.rubyonrails.org/action_cable_overview.html](https://guides.rubyonrails.org/action_cable_overview.html)
- **Stimulus Handbook**: [stimulus.hotwired.dev/handbook](https://stimulus.hotwired.dev/handbook)
- **Flipper Feature Flags**: [github.com/flippercloud/flipper](https://github.com/flippercloud/flipper)

---

*This post was written while building Elselands—a browser-based MMORPG recreating the classic Neverlands.ru experience with modern Rails tooling. The documentation-driven approach described here enabled rapid development of 9 major Neverlands-inspired systems, 100+ models, and comprehensive test coverage in a fraction of the time traditional development would require.*

