---
layout: post
author: Max Lukin
title: Optimizing a Complex Rails Avatar Endpoint — my step‑by‑step notes
date: 2025-08-15 09:00:00
tags: [rails-8, rack, healthcheck, devops, reliability]
categories: rails performance api optimization blueprinter ransack caching
excerpt: Optimizing a Complex Rails Avatar Endpoint
---

I had an API endpoint that returned a **Avatar** and a lot of nested associations. It worked, but the shape of the data made it easy to trigger N+1s or force a single **monster JOIN** that Postgres struggled to optimize.

This write‑up is my engineering log: what I started with, why it was slow, and the exact changes I shipped. It includes **every example from the session**, starting at **1)**, along with the full SQL log and the original preload code. All snippets are explicitly file‑scoped so they’re copy‑pasteable into a Rails 7/8 codebase.

---

## 1) Baseline & symptoms

**Endpoint:**

- `GET /api/v1/avatars/:id` (show)
- `GET /api/v1/avatars` (index with Ransack filters + pagination)

**Real SQL log I started from (show):**

```text
Started GET "/api/v1/avatars/1" for ::1 at 2025-08-11 14:59:59 +0000
Processing by Api::V1::GameController#show as */*
  Parameters: {"id" => "1"}
  Player Load (15.4ms)  SELECT `players`.* FROM `game_table` WHERE `players`.`id` = 1 LIMIT 1 /*action='show',application='TestApp',controller='game'*/
  Avatar Load (0.2ms)  SELECT `avatars`.* FROM `game_table` WHERE `avatars`.`id` = 1 LIMIT 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:143:in 'Api::V1::GameController#set_avatar'
  Armory Load (0.3ms)  SELECT `armory`.* FROM `game_table` WHERE `armory`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Rune Load (0.3ms)  SELECT `runes`.* FROM `game_table` WHERE `runes`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Beacon Load (0.2ms)  SELECT `beacons`.* FROM `game_table` WHERE `beacons`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  LoreNode Load (0.2ms)  SELECT `lore_nodes`.* FROM `game_table` WHERE `lore_nodes`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  TrainingLog Load (0.2ms)  SELECT `training_logs`.* FROM `game_table` WHERE `training_logs`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  LoadoutDoc Load (0.8ms)  SELECT `asset_cache`.* FROM `game_table` WHERE `asset_cache`.`asset_kind` = 'LoadoutDoc' AND `asset_cache`.`owner_id` = 1 AND `asset_cache`.`owner_kind` = 'Avatar' /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  QuestHook Load (0.3ms)  SELECT `quest_hooks`.* FROM `game_table` WHERE `quest_hooks`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  TrophyBanner Load (0.2ms)  SELECT `asset_cache`.* FROM `game_table` WHERE `asset_cache`.`asset_kind` = 'TrophyBanner' AND `asset_cache`.`owner_id` = 1 AND `asset_cache`.`owner_kind` = 'Avatar' /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Dialect Load (0.2ms)  SELECT `dialects`.* FROM `game_table` WHERE `dialects`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Permit Load (0.2ms)  SELECT `permits`.* FROM `game_table` WHERE `permits`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  MapRule Load (0.2ms)  SELECT `map_rules`.* FROM `game_table` WHERE `map_rules`.`avatar_id` = 1 LIMIT 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  GuildLink Load (0.3ms)  SELECT `guild_links`.* FROM `game_table` WHERE `guild_links`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Mission Load (0.2ms)  SELECT `missions`.* FROM `game_table` WHERE `missions`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  LoadoutDoc Load (0.2ms)  SELECT `asset_cache`.* FROM `game_table` WHERE `asset_cache`.`asset_kind` = 'LoadoutDoc' AND `asset_cache`.`owner_id` = 1 AND `asset_cache`.`owner_kind` = 'Mission' /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  TrophyBanner Load (0.2ms)  SELECT `asset_cache`.* FROM `game_table` WHERE `asset_cache`.`asset_kind` = 'TrophyBanner' AND `asset_cache`.`owner_id` = 1 AND `asset_cache`.`owner_kind` = 'Mission' /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Chronicle Load (0.2ms)  SELECT `chronicles`.* FROM `game_table` WHERE `chronicles`.`avatar_id` = 1 LIMIT 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  LoadoutDoc Load (0.2ms)  SELECT `asset_cache`.* FROM `game_table` WHERE `asset_cache`.`asset_kind` = 'LoadoutDoc' AND `asset_cache`.`owner_id` = 1 AND `asset_cache`.`owner_kind` = 'Chronicle' /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  BountyRule Load (0.3ms)  SELECT `bounty_rules`.* FROM `game_table` WHERE `bounty_rules`.`avatar_id` = 1 LIMIT 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  ClearanceRune Load (0.2ms)  SELECT `clearance_runes`.* FROM `game_table` WHERE `clearance_runes`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  AbilityReview Load (0.2ms)  SELECT `ability_reviews`.* FROM `game_table` WHERE `ability_reviews`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  Ability Load (0.2ms)  SELECT `abilities`.* FROM `game_table` WHERE `abilities`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  SideQuest Load (0.2ms)  SELECT `side_quests`.* FROM `game_table` WHERE `side_quests`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  RaidLog Load (0.2ms)  SELECT `raid_logs`.* FROM `game_table` WHERE `raid_logs`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  WitnessNote Load (0.2ms)  SELECT `witness_notes`.* FROM `game_table` WHERE `witness_notes`.`raid_log_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
  FieldNote Load (0.2ms)  SELECT `field_notes`.* FROM `game_table` WHERE `field_notes`.`avatar_id` = 1 /*action='show',application='TestApp',controller='game'*/
  ↳ app/controllers/api/v1/game_controller.rb:109:in 'Api::V1::GameController#show'
Completed 200 OK in 46ms (Views: 0.3ms | ActiveRecord: 22.0ms (27 queries, 0 cached) | GC: 1.4ms)
```

**Original preload block (index) I wanted to replace:**

```ruby
# app/controllers/api/v1/game_controller.rb (index; BEFORE)
@avatars = Avatar.preload(
  :player,
  :beacons,
  :abilities,
  :raid_logs,
  :guild_links,
  :dialects,
  :lore_nodes,
  :ability_reviews,
  :training_logs,
  :field_notes,
  :runes,
  :armory,
  :missions,
  :quest_hooks,
  :clearance_runes,
  :permits,
  :trophy_banners,
  :loadout_docs,
  :map_rule,
  :bounty_rule,
  # Nested associations for models that have their own associations
  { runes: [:loadout_docs] },
  { chronicle: [:loadout_docs] },
  { raid_logs: :witness_notes },
  { training_logs: [:trophy_banners, :loadout_docs] },
  { permits: [:trophy_banners, :loadout_docs, :permit_links] },
  { missions: [:trophy_banners, :loadout_docs] },
  { side_quests: [:trophy_banners, :loadout_docs] },
  { armory: [:loadout_docs] },
  # { clearance_runes: [:trophy_banners, :loadout_docs] },
  # { runes: [:trophy_banners, :loadout_docs] },
  # { field_notes: [:trophy_banners, :loadout_docs] }
)
.ransack(ransack_params)
.result(distinct: true)
.page(params[:page])
.per(params[:limit])
```

This fetches **everything** by default. Even when the UI only needed a subset, the DB and the JSON renderer were doing unnecessary work.

---

## 2) I made the payload **opt‑in** via `include=` and `fields=`

I added a small concern to parse and **whitelist** expansions and sparse fieldsets.

**File:** `app/controllers/concerns/include_params.rb`

```ruby
module IncludeParams
  # Whitelist to avoid arbitrary preload trees
  ALLOWED_INCLUDES = %w[
    player beacons abilities raid_logs.witness_notes guild_links
    dialects lore_nodes ability_reviews training_logs.trophy_banners training_logs.loadout_docs
    field_notes runes.loadout_docs armory.loadout_docs
    missions.trophy_banners missions.loadout_docs quest_hooks clearance_runes
    permits.trophy_banners permits.loadout_docs permits.permit_links
    trophy_banners loadout_docs chronicle.loadout_docs map_rule bounty_rule side_quests.trophy_banners
    side_quests.loadout_docs
  ].freeze

  def parsed_includes
    raw = params[:include].to_s.split(',').map(&:strip)
    raw & ALLOWED_INCLUDES
  end

  # JSON:API-style sparse fieldsets, e.g. fields[avatars]=id,username,role
  def parsed_fields
    fields = params.fetch(:fields, {}).to_h.transform_values { |v| v.split(',').map(&:strip) }
    fields.transform_keys!(&:to_s)
  end
end
```

**How I call it:**

- `GET /api/v1/avatars/1` → **compact** default payload.
- `GET /api/v1/avatars/1?include=missions.trophy_banners,training_logs.loadout_docs` → only those heavy bits are expanded.

---

## 3) Controller changes: **preload for rendering, JOIN for filters**

I mapped `include` tokens to a preload tree, and I only `JOIN` on associations that Ransack actually filters or sorts on.

**File:** `app/controllers/api/v1/game_controller.rb`

```ruby
class Api::V1::GameController < ApplicationController
  include IncludeParams

  # Map requested include tokens to a preload tree
  PRELOAD_MAP = {
    'player' => :player,
    'beacons' => :beacons,
    'abilities' => :abilities,
    'raid_logs' => { raid_logs: :witness_notes },
    'guild_links' => :guild_links,
    'dialects' => :dialects,
    'lore_nodes' => :lore_nodes,
    'ability_reviews' => :ability_reviews,
    'training_logs.trophy_banners' => { training_logs: :trophy_banners },
    'training_logs.loadout_docs'  => { training_logs: :loadout_docs },
    'field_notes' => :field_notes,
    'runes.loadout_docs' => { runes: :loadout_docs },
    'armory.loadout_docs' => { armory: :loadout_docs },
    'missions.trophy_banners' => { missions: :trophy_banners },
    'missions.loadout_docs'  => { missions: :loadout_docs },
    'quest_hooks' => :quest_hooks,
    'clearance_runes' => :clearance_runes,
    'permits.trophy_banners' => { permits: :trophy_banners },
    'permits.loadout_docs'  => { permits: :loadout_docs },
    'permits.permit_links' => { permits: :permit_links },
    'trophy_banners' => :trophy_banners,
    'loadout_docs'  => :loadout_docs,
    'chronicle.loadout_docs' => { chronicle: :loadout_docs },
    'map_rule' => :map_rule,
    'bounty_rule' => :bounty_rule,
    'side_quests.trophy_banners' => { side_quests: :trophy_banners },
    'side_quests.loadout_docs'  => { side_quests: :loadout_docs }
  }.freeze

  # GET /api/v1/avatars
  def index
    includes = parsed_includes
    fields   = parsed_fields
    scope    = Avatar.all

    # JOINs strictly for Ransack filters/sorts.
    if params.dig(:q)&.keys&.any? { |k| k.start_with?('player_') }
      scope = scope.joins(:player)
    end
    if params.dig(:q)&.keys&.any? { |k| k.start_with?('map_rule_') }
      scope = scope.joins(:map_rule)
    end

    scope = scope.preload(preload_tree(includes)) if includes.any?

    records = scope.ransack(ransack_params).result(distinct: true)
                   .page(params[:page]).per(params[:limit])

    render json: AvatarBlueprint.render(records,
      view: view_for(includes),
      fields: fields['avatars'])
  end

  # GET /api/v1/avatars/:id
  def show
    includes = parsed_includes
    fields   = parsed_fields

    scope = Avatar.preload(preload_tree(includes))
    @avatar = scope.find(params[:id])

    # Strong HTTP caching: ETag + Last-Modified across key associations
    last_mod = [
      @avatar.updated_at,
      @avatar.abilities.maximum(:updated_at),
      @avatar.raid_logs.maximum(:updated_at)
    ].compact.max

    fresh_when etag: [@avatar.cache_key_with_version, includes.sort],
               last_modified: last_mod,
               public: true

    render json: AvatarBlueprint.render(@avatar,
      view: view_for(includes),
      fields: fields['avatars'])
  end

  private

  def preload_tree(includes)
    includes.map { |key| PRELOAD_MAP.fetch(key) }
  end

  def view_for(includes)
    if includes.any? { |i| i.start_with?('missions') || i.start_with?('training_logs') }
      :extended
    elsif includes.any?
      :standard
    else
      :compact
    end
  end

  def ransack_params
    params.fetch(:q, {})
  end
end
```

---

## 4) Serializer views + per‑record caches (Blueprinter)

The default is **compact**; heavier trees are behind `:standard` and `:extended`. Heavy leaf nodes cache by `cache_key_with_version`.

**File:** `app/blueprints/avatar_blueprint.rb`

```ruby
class AvatarBlueprint < Blueprinter::Base
  identifier :id

  view :compact do
    fields :username, :role, :location, :experience_years
    association :player, blueprint: PlayerBlueprint, view: :tiny
  end

  view :standard do
    include_view :compact
    association :abilities, blueprint: AbilityBlueprint
    association :dialects, blueprint: DialectBlueprint
  end

  view :extended do
    include_view :standard
    association :raid_logs, blueprint: RaidLogBlueprint, view: :with_refs
    association :training_logs, blueprint: TrainingLogBlueprint, view: :with_assets
    association :missions, blueprint: MissionBlueprint, view: :with_assets do |avatar, options|
      max = options[:locals]&.fetch(:max_children, 25)
      avatar.missions.limit(max)
    end
    association :permits, blueprint: PermitBlueprint, view: :with_assets
    association :chronicle, blueprint: ChronicleBlueprint, view: :with_loadout_docs
  end
end
```

**File:** `app/blueprints/mission_blueprint.rb`

```ruby
class MissionBlueprint < Blueprinter::Base
  identifier :id
  fields :title, :summary, :started_on, :finished_on

  association :trophy_banners, blueprint: AttachmentBlueprint
  association :loadout_docs,  blueprint: AttachmentBlueprint

  # Per-record cache
  cache ->(obj, _opts) { "bp:mission:#{obj.cache_key_with_version}" }
end
```

---

## 5) Avoid “monster SQL”: split JOINs for filters from PRELOADs for rendering

This is the pattern I keep handy when the index endpoint starts accreting conditions:

```ruby
scope = Avatar.all

joins_needed = []
joins_needed << :player if params.dig(:q)&.keys&.any? { |k| k.start_with?('player_') }
joins_needed << :map_rule if params.dig(:q)&.keys&.any? { |k| k.start_with?('map_rule_') }
scope = scope.joins(*joins_needed) if joins_needed.any?

scope = scope.preload(preload_tree(parsed_includes))
records = scope.ransack(ransack_params).result(distinct: true)
```

---

## 6) Async preloading (optional)

Rails 7/8 lets me parallelize independent SELECTs:

**File:** `config/application.rb`

```ruby
config.active_record.async_query_executor = :global_thread_pool
config.active_record.global_executor_concurrency = 4 # tune per env
```

**Usage (example):**

```ruby
@avatar = Avatar.preload(preload_tree(parsed_includes)).load_async.find(params[:id])
```

---

## 7) Cap / paginate heavy nested collections

I pass a `locals` cap to Blueprinter and enforce it in the association (see `AvatarBlueprint` above).

```ruby
# app/controllers/api/v1/game_controller.rb (show)
render json: AvatarBlueprint.render(@avatar, view: :extended, locals: { max_children: 25 })
```

---

## 8) Side‑loading for fastest TTFB

Sometimes I just want IDs first, details later.

**Main payload sideload IDs:**

```json
{
  "id": 1,
  "mission_ids": [3,5,8,13]
}
```

**Then fetch details in bulk:**

```
GET /api/v1/missions?ids=3,5,8,13
```

**Or expose a focused associations endpoint:**

**File:** `app/controllers/api/v1/game_associations_controller.rb`

```ruby
class Api::V1::GameAssociationsController < ApplicationController
  include IncludeParams

  def show
    avatar = Avatar.find(params[:id])
    includes = parsed_includes
    raise ActionController::BadRequest, "include= required" if includes.blank?

    # Preload requested bits only
    Avatar.where(id: avatar.id).preload(preload_tree(includes)).load

    render json: {
      id: avatar.id,
      include: includes,
      data: AvatarBlueprint.render(avatar, view: :extended, fields: params.dig(:fields, 'avatars'))
    }
  end

  private

  def preload_tree(includes)
    includes.map { |key| Api::V1::GameController::PRELOAD_MAP.fetch(key) }
  end
end
```

Usage:

```
GET /api/v1/avatars/1/associations?include=missions,training_logs
```

---

## 9) Model‑level tweaks that prevent surprise queries

**File:** `app/models/avatar.rb`

```ruby
class Avatar < ApplicationRecord
  has_many :abilities, inverse_of: :avatar, dependent: :destroy
  has_many :missions, inverse_of: :avatar, dependent: :destroy
  # If you use counters a lot:
  # has_many :raid_logs, inverse_of: :avatar, dependent: :destroy, counter_cache: true
end
```

I also use `touch: false` on high‑churn relations so I don’t constantly invalidate parent caches.

To keep Ransack from auto‑joining unexpected stuff, I whitelist:

```ruby
# app/models/avatar.rb
def self.ransackable_associations(_ = nil)
  %w[player map_rule]
end

def self.ransackable_attributes(_ = nil)
  %w[username role location experience_years]
end
```

---

## 10) Guardrails: I enforce a “query budget” in tests

**File:** `spec/requests/api/v1/avatars_spec.rb`

```ruby
it 'stays under 12 queries for compact show' do
  expect {
    get "/api/v1/avatars/#{avatar.id}"
  }.to make_database_queries(count: <= 12) # adapt matcher/threshold
end
```

I also log `payload_size` (bytes) and render time so regressions show up in metrics, not in player reports.

---

## 11) Requests I actually run during development

**Index (lean default):**

```
GET /api/v1/avatars?page=1&limit=20
```

**Index + filter on player + expand a bit:**

```
GET /api/v1/avatars?include=abilities,dialects&q[player_email_cont]=max@
```

**Show minimal (fastest):**

```
GET /api/v1/avatars/1
```

**Show with heavy expansions:**

```
GET /api/v1/avatars/1?include=missions.trophy_banners,training_logs.loadout_docs,permits.loadout_docs
```

**Fetch only associations later:**

```
GET /api/v1/avatars/1/associations?include=missions,training_logs
```

---

## 12) Appendix — the full “before” preload list (for posterity)

```ruby
Avatar.preload(
  :player,
  :beacons,
  :abilities,
  :raid_logs,
  :guild_links,
  :dialects,
  :lore_nodes,
  :ability_reviews,
  :training_logs,
  :field_notes,
  :runes,
  :armory,
  :missions,
  :quest_hooks,
  :clearance_runes,
  :permits,
  :trophy_banners,
  :loadout_docs,
  :map_rule,
  :bounty_rule,
  { runes: [:loadout_docs] },
  { chronicle: [:loadout_docs] },
  { raid_logs: :witness_notes },
  { training_logs: [:trophy_banners, :loadout_docs] },
  { permits: [:trophy_banners, :loadout_docs, :permit_links] },
  { missions: [:trophy_banners, :loadout_docs] },
  { side_quests: [:trophy_banners, :loadout_docs] },
  { armory: [:loadout_docs] }
)
```

---

### What changed (in one screen)

- Default response is **compact**; clients expand with `include=`/`fields=`.
- I **JOIN** only for filters/sorts; I **preload** what I render.
- Heavier serializer views are cached per record.
- Strong **ETag/Last‑Modified** avoids re‑rendering unchanged resources.
- Optional **async preloading** helps when many independent associations exist.
- I cap/paginate heavy children or fetch them via dedicated endpoints.
- Guardrails (query budget, Ransack whitelists, payload logging) keep it fast.

If you drop this post into a Jekyll site, name it `_posts/2025-08-15-rails-avatar-endpoint-optimization.md`.
