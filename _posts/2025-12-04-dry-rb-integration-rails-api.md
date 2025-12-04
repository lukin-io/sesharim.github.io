---
layout: post
title: "From Rails Spaghetti to Structured Code: Integrating dry-rb into Your API"
date: 2025-12-04
author: Max Lukin
tags: [rails, dry-rb, functional-programming, refactoring, types, validation, architecture, events]
categories: [engineering, rails, best-practices, refactoring]
description: "A comprehensive guide to integrating 11 dry-rb gems into your Ruby on Rails API—showing real before/after examples of how dry-types, dry-struct, dry-monads, dry-validation, dry-container, dry-matcher, dry-configurable, dry-initializer, and dry-events improve maintainability, testability, and code clarity."
---

> _"The best code isn't clever—it's obvious. dry-rb makes Rails code obvious."_

Every Rails developer has written code that works but feels wrong. Manual type coercion scattered across controllers. Validation logic duplicated between models and services. Deeply nested conditionals handling success and failure cases. Configuration constants scattered across files. Side effects mixed with business logic. These patterns work, but they accumulate into technical debt.

After shipping dozens of API endpoints, we integrated **dry-rb** into our Rails API. This post documents the transformation—with real before/after examples showing how each gem improves specific code patterns.

---

## Table of Contents

1. [The Problem: Rails Patterns That Don't Scale](#1-the-problem-rails-patterns-that-dont-scale)
2. [The Solution: dry-rb Gem Suite](#2-the-solution-dry-rb-gem-suite)
3. [dry-types: Type-Safe Enums and Coercion](#3-dry-types-type-safe-enums-and-coercion)
4. [dry-struct: Immutable Data Structures](#4-dry-struct-immutable-data-structures)
5. [dry-monads: Functional Error Handling](#5-dry-monads-functional-error-handling)
6. [dry-validation: Contract-Based Validation](#6-dry-validation-contract-based-validation)
7. [dry-container + dry-auto_inject: Dependency Injection](#7-dry-container--dry-auto_inject-dependency-injection)
8. [dry-matcher: Pattern Matching for Results](#8-dry-matcher-pattern-matching-for-results)
9. [dry-configurable: Thread-Safe Configuration](#9-dry-configurable-thread-safe-configuration)
10. [dry-initializer: Declarative Parameter DSL](#10-dry-initializer-declarative-parameter-dsl)
11. [dry-events: Pub/Sub Event System](#11-dry-events-pubsub-event-system)
12. [Other dry-rb Gems Worth Exploring](#12-other-dry-rb-gems-worth-exploring)
13. [Benefits and Tradeoffs](#13-benefits-and-tradeoffs)
14. [Conclusion](#14-conclusion)

---

## 1. The Problem: Rails Patterns That Don't Scale

### 1.1 The "Rails Way" Has Limits

Rails conventions are excellent for getting started quickly. But as applications grow, certain patterns become problematic:

| Pattern | Works For | Breaks When |
|---------|-----------|-------------|
| Hash params everywhere | Simple CRUD | Complex nested data structures |
| ActiveRecord validations | Model-level rules | Cross-field business logic |
| Controller conditionals | Simple flows | Multiple success/failure paths |
| Manual type coercion | Occasional use | Dozens of fields need processing |
| Class method calls | Small apps | Testing requires stubbing globals |
| Scattered constants | One-off values | Configuration needs structure |
| Inline side effects | Simple actions | Need audit trail or event-driven architecture |

### 1.2 Real Example: Profile Actions Payload

We needed to serialize client-specific profile data. Here's what the original code looked like:

```ruby
# Original: 70+ lines of manual validation and coercion
def build_actions_payload(options)
  actions = extract_actions_data(options)
  result = {}

  # Manual enum validation
  status = actions[:access_status].to_s
  result[:access_status] = ACCESS_STATUS_VALUES.include?(status) ? status : "none"

  # Manual boolean coercion
  result[:profile_viewed] = actions[:profile_viewed] == true
  result[:is_saved] = actions[:is_saved] == true

  # Manual conditional inclusion
  if actions[:thumb_status].present?
    thumb = actions[:thumb_status].to_s
    result[:thumb_status] = thumb if THUMB_STATUS_VALUES.include?(thumb)
  end

  if actions[:applied_at].present?
    value = actions[:applied_at]
    result[:applied_at] = value.respond_to?(:iso8601) ? value.iso8601 : value.to_s
  end

  if actions.key?(:access_expired)
    result[:access_expired] = actions[:access_expired] == true
  end

  if actions[:access_end_reason].present?
    reason = actions[:access_end_reason].to_s
    result[:access_end_reason] = reason if ACCESS_END_REASON_VALUES.include?(reason)
  end

  # ... 30 more lines
  result
end
```

**Problems:**
- ❌ Manual type coercion (`to_s`, `== true`) repeated everywhere
- ❌ Validation scattered (constants + inline checks)
- ❌ Hard to test—tightly coupled to Blueprint
- ❌ No type safety—wrong data silently coerced
- ❌ Verbose—business logic drowns in boilerplate

---

## 2. The Solution: dry-rb Gem Suite

The [dry-rb](https://dry-rb.org/gems/) ecosystem provides focused, composable gems for common problems:

| Gem | Purpose | Replaces |
|-----|---------|----------|
| **dry-types** | Type definitions with constraints | Manual enum validation |
| **dry-struct** | Immutable typed objects | Hash manipulation |
| **dry-monads** | Functional result handling | try/rescue + conditionals |
| **dry-validation** | Contract-based validation | Scattered validation logic |
| **dry-schema** | Schema coercion | Strong parameters edge cases |
| **dry-container** | Dependency registry | Global class references |
| **dry-auto_inject** | Constructor injection | Manual dependency passing |
| **dry-matcher** | Result pattern matching | Case statements on results |
| **dry-configurable** | Thread-safe configuration | Scattered constants |
| **dry-initializer** | Param/option DSL | Boilerplate initialize methods |
| **dry-events** | Pub/sub event system | Inline side effects |

### Our Gemfile Addition

```ruby
# Gemfile
# Dry-rb gems for structured types, validation, and functional patterns
gem "dry-types", "~> 1.7"
gem "dry-struct", "~> 1.6"
gem "dry-monads", "~> 1.6"
gem "dry-validation", "~> 1.11"
gem "dry-schema", "~> 1.14"
gem "dry-container", "~> 0.11"
gem "dry-auto_inject", "~> 0.9"
gem "dry-matcher", "~> 1.0"
gem "dry-configurable", "~> 1.2"
gem "dry-initializer", "~> 3.1"
gem "dry-events", "~> 1.0"
```

---

## 3. dry-types: Type-Safe Enums and Coercion

### 3.1 The Problem: Scattered Constants and Manual Checks

```ruby
# Before: Constants scattered, validation repeated
class ProfileBlueprint < ApplicationBlueprint
  ACCESS_STATUS_VALUES = %w[none requested approved denied removed shared].freeze
  THUMB_STATUS_VALUES = %w[liked disliked].freeze
  ACCESS_END_REASON_VALUES = %w[expired declined blocked removed].freeze

  def build_actions_payload(options)
    status = actions[:access_status].to_s
    result[:access_status] = ACCESS_STATUS_VALUES.include?(status) ? status : "none"
    # Repeated for every enum field...
  end
end
```

**Issues:**
- Constants defined in one class, used elsewhere
- Validation logic duplicated wherever enums are checked
- No automatic coercion or defaults

### 3.2 The Solution: Centralized Type Registry

```ruby
# app/types.rb
require "dry/types"

module Types
  include Dry.Types()

  # Common types with safe defaults
  SafeBool = Types::Bool.fallback(false)
  OptionalString = Types::String.optional
  OptionalInteger = Types::Integer.optional

  # ISO8601 timestamp coercion
  ISO8601String = Types::String.optional.constructor do |value|
    next nil if value.nil?
    case value
    when Time, DateTime, ActiveSupport::TimeWithZone
      value.iso8601
    else
      value.to_s
    end
  end

  # Profile Actions enums - SINGLE SOURCE OF TRUTH
  module Profiles
    ACCESS_STATUS_VALUES = %w[none requested approved denied removed shared].freeze
    AccessStatus = Types::String.enum(*ACCESS_STATUS_VALUES).fallback("none")

    THUMB_STATUS_VALUES = %w[liked disliked].freeze
    ThumbStatus = Types::String.enum(*THUMB_STATUS_VALUES).optional

    ACCESS_END_REASON_VALUES = %w[expired declined blocked removed].freeze
    AccessEndReason = Types::String.enum(*ACCESS_END_REASON_VALUES).optional
  end
end
```

**Benefits:**
- ✅ Enums defined once, reusable everywhere
- ✅ Built-in validation (invalid values → constraint error or fallback)
- ✅ Automatic coercion with `.constructor`
- ✅ Safe defaults with `.fallback()`
- ✅ Self-documenting—type definitions are specifications

### 3.3 Usage Examples

```ruby
# Enum validation is automatic
Types::Profiles::AccessStatus["approved"]  # => "approved"
Types::Profiles::AccessStatus["invalid"]   # => "none" (fallback)
Types::Profiles::AccessStatus[nil]         # => "none" (fallback)

# Boolean coercion with fallback
Types::SafeBool[true]   # => true
Types::SafeBool[nil]    # => false (fallback, not nil!)

# Timestamp coercion
Types::ISO8601String[Time.current]           # => "2025-12-04T09:30:00Z"
Types::ISO8601String["2025-12-04T09:30:00Z"] # => "2025-12-04T09:30:00Z"
Types::ISO8601String[nil]                    # => nil
```

---

## 4. dry-struct: Immutable Data Structures

### 4.1 The Problem: Hash Manipulation Everywhere

```ruby
# Before: Raw hash with manual processing
def build_actions
  actions = {}
  actions[:access_status] = compute_access_status
  actions[:profile_viewed] = compute_profile_viewed
  actions[:is_saved] = compute_is_saved
  # No guarantee of structure
  # Caller must know what keys exist
  # Mutable—anyone can modify
  actions
end
```

**Issues:**
- No schema—structure discovered at runtime
- Mutable—data can change unexpectedly
- Manual coercion needed when consuming
- No IDE autocompletion

### 4.2 The Solution: Typed Immutable Struct

```ruby
# app/structs/profiles/actions.rb
require "dry/struct"

module Profiles
  class Actions < Dry::Struct
    # Allow string keys from input hash
    transform_keys(&:to_sym)

    # Required fields with defaults (always present in payload)
    attribute? :access_status, Types::Profiles::AccessStatus.default("none".freeze)
    attribute? :profile_viewed, Types::SafeBool.default(false)
    attribute? :is_saved, Types::SafeBool.default(false)

    # Optional fields (only in payload when present)
    attribute? :note, Types::OptionalString
    attribute? :thumb_status, Types::Profiles::ThumbStatus
    attribute? :applied_at, Types::ISO8601String
    attribute? :access_expired, Types::Bool.optional
    attribute? :access_end_reason, Types::Profiles::AccessEndReason
    attribute? :chat_id, Types::OptionalInteger
    attribute? :is_shared, Types::Bool.optional

    # Clean serialization for API response
    def to_payload
      payload = {
        access_status: access_status,
        profile_viewed: profile_viewed,
        is_saved: is_saved
      }

      # Add optional fields only when present
      payload[:note] = note if note.present?
      payload[:thumb_status] = thumb_status if thumb_status.present?
      payload[:applied_at] = applied_at if applied_at.present?
      payload[:access_expired] = access_expired unless access_expired.nil?
      payload[:access_end_reason] = access_end_reason if access_end_reason.present?
      payload[:chat_id] = chat_id if chat_id.present?
      payload[:is_shared] = true if is_shared == true

      payload
    end
  end
end
```

### 4.3 Before vs After Comparison

**Before (manual hash building):**
```ruby
# 70+ lines scattered across service and blueprint
def build_actions_payload(options)
  actions = extract_actions_data(options)
  result = {}
  status = actions[:access_status].to_s
  result[:access_status] = ACCESS_STATUS_VALUES.include?(status) ? status : "none"
  result[:profile_viewed] = actions[:profile_viewed] == true
  # ... 60 more lines of manual processing
end
```

**After (struct instantiation):**
```ruby
# Service creates struct
actions = Profiles::Actions.new(
  access_status: compute_access_status,
  profile_viewed: compute_profile_viewed,
  is_saved: compute_is_saved,
  chat_id: find_chat_room&.id
)

# Blueprint just calls to_payload
field :actions do |_profile, options|
  options.dig(:context, :actions).to_payload
end
```

**Reduction: 70+ lines → ~15 lines**

### 4.4 Benefits of dry-struct

| Aspect | Raw Hash | Dry::Struct |
|--------|----------|-------------|
| **Schema** | Implicit | Explicit, documented |
| **Type safety** | None | Enforced at construction |
| **Defaults** | Manual | Declarative |
| **Mutability** | Mutable | Immutable |
| **IDE support** | None | Autocomplete attributes |
| **Testability** | Test whole flow | Test struct in isolation |

---

## 5. dry-monads: Functional Error Handling

### 5.1 The Problem: Nested Conditionals

```ruby
# Before: Conditional soup
def call
  return nil unless profile.present?
  return nil unless client_user.present?
  return nil unless client_user.client?
  return nil unless profile_user.present?

  # Happy path finally...
  build_actions
rescue StandardError => e
  Rails.logger.error(e)
  nil
end
```

**Issues:**
- Early returns obscure happy path
- Error information lost (just returns nil)
- Caller can't distinguish "no data" from "error"
- No composability

### 5.2 The Solution: Result Monad

```ruby
# app/services/profiles/actions_builder.rb
require "dry/monads"

module Profiles
  class ActionsBuilder
    include Dry::Monads[:result]

    def call
      return Success(default_actions_struct) unless valid_context?

      Success(build_actions_struct)
    end

    private

    def valid_context?
      profile.present? &&
        client_user.present? &&
        client_user.client? &&
        profile_user.present?
    end

    def default_actions_struct
      Profiles::Actions.new(
        access_status: "none",
        profile_viewed: false,
        is_saved: false
      )
    end

    def build_actions_struct
      Profiles::Actions.new(
        access_status: compute_access_status,
        profile_viewed: compute_profile_viewed,
        # ... other fields
      )
    end
  end
end
```

### 5.3 Controller Integration

```ruby
# app/controllers/api/v1/profiles_controller.rb
def show
  flags = visibility_flags.get(@profile)
  context = { visibility_flags: flags, host: request.base_url }

  if current_user&.client?
    result = actions_builder.call(profile: @profile, client_user: current_user)
    context[:actions] = result.value! if result.success?
  end

  render json: { data: ProfileBlueprint.render_as_hash(@profile, context: context) }
end
```

### 5.4 Pattern Matching with Results

```ruby
# For more complex flows, pattern match on Result
result = ActionsBuilder.call(profile: @profile, client_user: current_user)

case result
in Success(actions)
  render_success(actions.to_payload)
in Failure[:invalid_context, reason]
  Rails.logger.warn("Invalid context: #{reason}")
  render_default_actions
in Failure[:database_error, exception]
  Sentry.capture_exception(exception)
  head :internal_server_error
end
```

### 5.5 Composing Multiple Operations

```ruby
# Chain operations that might fail
class ProcessOrder
  include Dry::Monads[:result, :do]

  def call(order_params)
    order = yield validate_order(order_params)
    user = yield find_user(order.user_id)
    payment = yield charge_payment(user, order.total)
    yield send_confirmation(user, order, payment)

    Success(order)
  end

  private

  def validate_order(params)
    # Returns Success(order) or Failure([:validation, errors])
  end

  def charge_payment(user, amount)
    # Returns Success(payment) or Failure([:payment_failed, reason])
  end
end
```

The `yield` keyword automatically unwraps `Success` values and short-circuits on `Failure`.

---

## 6. dry-validation: Contract-Based Validation

### 6.1 The Problem: Validation Logic Everywhere

```ruby
# Before: Validation scattered across controller, model, and service
class ItemsController < ApplicationController
  def create
    # Controller validation
    return render_error("Title required") if params[:title].blank?
    return render_error("Invalid status") unless VALID_STATUSES.include?(params[:status])

    @item = Item.new(item_params)
    # Model validation runs here too...
  end
end

class Item < ApplicationRecord
  # Model validation
  validates :title, presence: true
  validates :status, inclusion: { in: VALID_STATUSES }
  validate :price_must_be_positive_for_published
end
```

**Issues:**
- Validation logic duplicated (controller + model)
- Cross-field rules awkward in ActiveRecord
- Hard to test validation in isolation
- Error messages inconsistent

### 6.2 The Solution: Validation Contracts

```ruby
# app/contracts/profiles/actions_contract.rb
require "dry/validation"

module Profiles
  class ActionsContract < Dry::Validation::Contract
    # Schema definition - coerces and validates structure
    params do
      optional(:access_status).filled(:string)
      optional(:profile_viewed).filled(:bool)
      optional(:is_saved).filled(:bool)
      optional(:note).maybe(:string)
      optional(:thumb_status).maybe(:string)
      optional(:access_expired).maybe(:bool)
      optional(:access_end_reason).maybe(:string)
      optional(:chat_id).maybe(:integer)
    end

    # Enum validation rules
    rule(:access_status) do
      next if value.nil?
      unless Types::Profiles::ACCESS_STATUS_VALUES.include?(value)
        key.failure("must be one of: #{Types::Profiles::ACCESS_STATUS_VALUES.join(', ')}")
      end
    end

    rule(:thumb_status) do
      next if value.nil?
      unless Types::Profiles::THUMB_STATUS_VALUES.include?(value)
        key.failure("must be one of: #{Types::Profiles::THUMB_STATUS_VALUES.join(', ')}")
      end
    end

    # Cross-field validation
    rule(:access_end_reason, :access_expired) do
      if values[:access_end_reason].present? && values[:access_expired] != true
        key(:access_end_reason).failure("requires access_expired to be true")
      end
    end
  end
end
```

### 6.3 Using Contracts

```ruby
contract = Profiles::ActionsContract.new
result = contract.call(params.to_unsafe_h)

if result.success?
  # Validated and coerced data
  actions = Profiles::Actions.new(result.to_h)
else
  # Structured errors
  render json: { errors: result.errors.to_h }, status: :unprocessable_entity
end
```

### 6.4 Contract vs Model Validation

| Aspect | ActiveRecord Validation | Dry::Validation Contract |
|--------|------------------------|-------------------------|
| **When runs** | Before save | Before touching model |
| **Cross-field rules** | Custom validators | Declarative `rule` blocks |
| **Testability** | Requires model instance | Pure Ruby, no DB |
| **Reusability** | Tied to model | Standalone class |
| **Error format** | Rails format | Customizable |
| **Coercion** | Limited | Built-in via schema |

**Use both:** Contracts for input validation (API layer), ActiveRecord for data integrity (persistence layer).

---

## 7. dry-container + dry-auto_inject: Dependency Injection

### 7.1 The Problem: Hard-Coded Dependencies

```ruby
# Before: Tight coupling to class names
class ProfilesController < ApplicationController
  def show
    flags = Visibility::ProfileVisibilityFlags.get(@profile)
    result = Profiles::ActionsBuilder.call(profile: @profile, client_user: current_user)
    # ...
  end
end

# Testing requires stubbing constants
RSpec.describe ProfilesController do
  before do
    allow(Visibility::ProfileVisibilityFlags).to receive(:get).and_return({})
    allow(Profiles::ActionsBuilder).to receive(:call).and_return(Success({}))
  end
end
```

**Issues:**
- Can't easily swap implementations
- Testing requires monkey-patching
- Dependencies hidden in method bodies
- No central registry of services

### 7.2 The Solution: Container + Injection

```ruby
# app/container.rb
require "dry/container"
require "dry/auto_inject"

class AppContainer
  extend Dry::Container::Mixin

  # Register services
  register(:actions_builder) { Profiles::ActionsBuilder }
  register(:visibility_flags) { Visibility::ProfileVisibilityFlags }

  # Future additions
  # register(:email_service) { EmailService.new }
  # register(:payment_gateway) { Stripe::Client.new(ENV['STRIPE_KEY']) }
end

# For POROs (constructor injection)
Import = Dry::AutoInject(AppContainer)

# For Rails controllers (memoized accessors)
module Deps
  def self.included(base)
    base.class_eval do
      AppContainer.keys.each do |key|
        define_method(key) do
          @_deps_cache ||= {}
          @_deps_cache[key] ||= AppContainer[key]
        end
      end
    end
  end
end
```

### 7.3 Controller with Injection

```ruby
# app/controllers/api/v1/profiles_controller.rb
class ProfilesController < ApplicationController
  include Deps  # Inject all registered dependencies

  def show
    flags = visibility_flags.get(@profile)           # Use injected service
    result = actions_builder.call(...)               # Use injected builder
    # ...
  end
end
```

### 7.4 Testing with Injection

```ruby
# Spec: Easy stubbing via dependency override
RSpec.describe ProfilesController do
  let(:mock_builder) { double("ActionsBuilder") }
  let(:mock_flags) { double("VisibilityFlags") }

  before do
    # Override container registrations for test
    AppContainer.stub(:actions_builder, mock_builder)
    AppContainer.stub(:visibility_flags, mock_flags)
  end

  it "uses injected dependencies" do
    expect(mock_flags).to receive(:get).and_return({})
    expect(mock_builder).to receive(:call).and_return(Success(default_actions))

    get :show, params: { id: profile.id }
  end
end
```

### 7.5 Benefits of Dependency Injection

| Without DI | With DI |
|------------|---------|
| `ClassName.call(...)` scattered | Centralized registry |
| Test with `allow(ClassName)` | Test with mock injection |
| Change implementation = change every caller | Change registration only |
| Dependencies implicit | Dependencies explicit |

---

## 8. dry-matcher: Pattern Matching for Results

### 8.1 The Problem: Verbose Result Handling

```ruby
# Before: Manual success/failure checks
def show
  result = actions_builder.call(profile: @profile, client_user: current_user)

  if result.success?
    context[:actions] = result.value!
  else
    case result.failure
    when :not_found
      head :not_found
    when :unauthorized
      head :unauthorized
    else
      render json: { error: result.failure }, status: :unprocessable_entity
    end
  end
end
```

**Issues:**
- Verbose conditional logic
- Easy to forget failure cases
- Not composable
- Repeated patterns across controllers

### 8.2 The Solution: Pattern Matching Concern

```ruby
# app/controllers/concerns/result_matchable.rb
require "dry/matcher/result_matcher"

module ResultMatchable
  extend ActiveSupport::Concern

  included do
    class_attribute :result_matcher, default: Dry::Matcher::ResultMatcher
  end

  # Match on a Dry::Monads::Result with pattern matching
  def match_result(result, &block)
    result_matcher.call(result, &block)
  end

  # Extract value from Success or return nil for Failure
  def unwrap_result(result)
    result.success? ? result.value! : nil
  end

  # Returns [success?, value_or_error]
  def result_tuple(result)
    if result.success?
      [true, result.value!]
    else
      [false, result.failure]
    end
  end
end
```

### 8.3 Controller with Pattern Matching

```ruby
# app/controllers/api/v1/profiles_controller.rb
class ProfilesController < ApplicationController
  include ResultMatchable  # Add pattern matching

  def show
    result = actions_builder.call(profile: @profile, client_user: current_user)

    # Simple extraction
    context[:actions] = unwrap_result(result)

    # Or full pattern matching for complex flows
    match_result(result) do |m|
      m.success { |actions| context[:actions] = actions }
      m.failure(:not_found) { head :not_found; return }
      m.failure(:unauthorized) { head :unauthorized; return }
      m.failure { |error| Rails.logger.warn("Actions failed: #{error}") }
    end

    render json: { data: ProfileBlueprint.render_as_hash(@profile, context: context) }
  end
end
```

### 8.4 Before vs After

**Before:**
```ruby
# 15 lines of conditional logic
if result.success?
  context[:actions] = result.value!
else
  case result.failure
  when :not_found then head :not_found
  when :unauthorized then head :unauthorized
  else render_error(result.failure)
  end
end
```

**After:**
```ruby
# 1 line for simple cases
context[:actions] = unwrap_result(result)

# Or declarative matching for complex cases
match_result(result) do |m|
  m.success { |v| context[:actions] = v }
  m.failure(:not_found) { head :not_found }
  m.failure { |e| render_error(e) }
end
```

### 8.5 Benefits

| Without dry-matcher | With dry-matcher |
|---------------------|------------------|
| `if/case` statements | Declarative blocks |
| Easy to miss cases | Exhaustive matching |
| Scattered handling | Centralized concern |
| Hard to test branches | Each handler testable |

---

## 9. dry-configurable: Thread-Safe Configuration

### 9.1 The Problem: Scattered Constants

```ruby
# Before: Constants scattered across files
class ProfileBlueprint < ApplicationBlueprint
  ACCESS_STATUS_VALUES = %w[none requested approved denied removed shared].freeze
  CACHE_TTL = 5.minutes
end

class AccessRequest < ApplicationRecord
  EXPIRY_DAYS = 30
end

class ProfilesController < ApplicationController
  MAX_PER_PAGE = 100
end
```

**Issues:**
- Configuration scattered across classes
- Hard to find all config values
- No nesting or organization
- Testing requires constant stubbing
- Not thread-safe for dynamic changes

### 9.2 The Solution: Centralized Configuration

```ruby
# app/config/profile_config.rb
require "dry/configurable"

class ProfileConfig
  extend Dry::Configurable

  # Actions settings
  setting :actions do
    setting :cache_ttl, default: 5.minutes
    setting :default_access_status, default: "none"
    setting :default_profile_viewed, default: false
    setting :default_is_saved, default: false

    setting :access_status_values, default: %w[none requested approved denied removed shared].freeze
    setting :thumb_status_values, default: %w[liked disliked].freeze
    setting :access_end_reason_values, default: %w[expired declined blocked removed].freeze

    setting :status_mapping, default: {
      "pending" => "requested",
      "approved" => "approved",
      "declined" => "denied",
      "blocked" => "denied",
      "expired" => "removed"
    }.freeze
  end

  # Visibility settings
  setting :visibility do
    setting :default_mode, default: "visible"
    setting :modes, default: %w[visible semi_anonymous fully_anonymous].freeze
  end

  # Access request settings
  setting :access do
    setting :request_expiry_days, default: 30
    setting :auto_approve_verified_companies, default: false
    setting :max_pending_per_company, default: 100
  end

  # Event publishing settings
  setting :events do
    setting :publish_profile_views, default: true
    setting :publish_access_events, default: true
  end
end
```

### 9.3 Usage in Code

```ruby
# Access nested settings with dot notation
ProfileConfig.config.actions.cache_ttl           # => 5.minutes
ProfileConfig.config.actions.status_mapping      # => {"pending" => "requested", ...}
ProfileConfig.config.visibility.default_mode     # => "visible"
ProfileConfig.config.access.request_expiry_days  # => 30

# Use in service objects
class ActionsBuilder
  def default_actions_struct
    Profiles::Actions.new(
      access_status: config.default_access_status,
      profile_viewed: config.default_profile_viewed,
      is_saved: config.default_is_saved
    )
  end

  private

  def config
    ProfileConfig.config.actions
  end
end
```

### 9.4 Testing with Configuration

```ruby
RSpec.describe ActionsBuilder do
  # Override config for test
  before do
    allow(ProfileConfig.config.actions).to receive(:cache_ttl).and_return(0)
  end

  # Or use configure block
  around do |example|
    original = ProfileConfig.config.actions.cache_ttl
    ProfileConfig.configure { |c| c.actions.cache_ttl = 0 }
    example.run
    ProfileConfig.configure { |c| c.actions.cache_ttl = original }
  end
end
```

### 9.5 Before vs After

**Before:**
```ruby
# Hunt through 10 files to find all profile-related constants
grep -r "CACHE_TTL\|EXPIRY_DAYS\|MAX_" app/
```

**After:**
```ruby
# One file, organized by domain
ProfileConfig.config  # => nested configuration tree
```

### 9.6 Benefits

| Scattered Constants | dry-configurable |
|--------------------|------------------|
| Find: grep across codebase | Find: one file |
| Organize: N/A | Organize: nested settings |
| Test: stub constants | Test: configure block |
| Thread-safe: No | Thread-safe: Yes |
| Document: comments | Document: structure IS docs |

---

## 10. dry-initializer: Declarative Parameter DSL

### 10.1 The Problem: Boilerplate Initialize Methods

```ruby
# Before: Manual parameter handling
class ActionsBuilder
  def initialize(profile:, client_user:)
    @profile = profile
    @client_user = client_user
    @profile_user = profile&.user
  end

  def self.call(profile:, client_user:)
    new(profile: profile, client_user: client_user).call
  end

  private

  attr_reader :profile, :client_user, :profile_user
end
```

**Issues:**
- Boilerplate `@x = x` assignments
- Manual `attr_reader` for each param
- No type coercion
- No default values
- `self.call` pattern repeated everywhere

### 10.2 The Solution: Declarative Parameters

```ruby
# app/services/profiles/actions_builder.rb
require "dry/initializer"

module Profiles
  class ActionsBuilder
    extend Dry::Initializer

    # Required parameters
    param :profile
    param :client_user

    # Derived option with default
    option :profile_user, default: proc { profile&.user }

    def self.call(profile:, client_user:)
      new(profile, client_user).call
    end

    def call
      return Success(default_actions_struct) unless valid_context?
      Success(build_actions_struct)
    end

    # params are accessible directly - no attr_reader needed
    private

    def valid_context?
      profile.present? && client_user.present? && client_user.client?
    end
  end
end
```

### 10.3 Advanced Features

```ruby
class OrderProcessor
  extend Dry::Initializer

  # Required param with type coercion
  param :order_id, Types::Integer

  # Optional param with default
  param :notify, default: proc { true }

  # Named options (keyword args)
  option :logger, default: proc { Rails.logger }
  option :mailer, default: proc { OrderMailer }

  # Type-checked option
  option :priority, Types::String.enum("low", "normal", "high"), default: proc { "normal" }

  # Reader visibility
  option :api_key, reader: :private

  def call
    logger.info("Processing order #{order_id} with priority #{priority}")
    # ...
  end
end

# Usage
processor = OrderProcessor.new(123, true, priority: "high")
processor.order_id  # => 123
processor.priority  # => "high"
```

### 10.4 Before vs After

**Before (19 lines):**
```ruby
class ActionsBuilder
  def initialize(profile:, client_user:)
    @profile = profile
    @client_user = client_user
    @profile_user = profile&.user
  end

  def self.call(profile:, client_user:)
    new(profile: profile, client_user: client_user).call
  end

  private

  attr_reader :profile, :client_user, :profile_user

  def call
    # ...
  end
end
```

**After (10 lines):**
```ruby
class ActionsBuilder
  extend Dry::Initializer

  param :profile
  param :client_user
  option :profile_user, default: proc { profile&.user }

  def self.call(profile:, client_user:)
    new(profile, client_user).call
  end

  def call
    # ...
  end
end
```

### 10.5 Benefits

| Manual Initialize | dry-initializer |
|-------------------|-----------------|
| `@x = x` boilerplate | Declarative `param`/`option` |
| Manual `attr_reader` | Auto-generated readers |
| No type coercion | Built-in type support |
| No defaults DSL | `default: proc { }` |
| All public readers | `reader: :private` option |

---

## 11. dry-events: Pub/Sub Event System

### 11.1 The Problem: Inline Side Effects

```ruby
# Before: Side effects mixed with business logic
class ProfilesController < ApplicationController
  def show
    @profile = Profile.find(params[:id])

    # Business logic
    context = build_context(@profile)

    # Side effect #1: Analytics
    Analytics.track("profile_viewed", {
      profile_id: @profile.id,
      viewer_id: current_user&.id
    })

    # Side effect #2: Logging
    AuditLog.create!(
      action: "profile_view",
      resource: @profile,
      user: current_user
    )

    # Side effect #3: Cache warming
    ProfileCacheWarmer.perform_async(@profile.id) if should_warm_cache?

    render json: { data: ProfileBlueprint.render_as_hash(@profile, context: context) }
  end
end
```

**Issues:**
- Controller bloated with side effects
- Hard to test business logic in isolation
- Adding new side effects = modifying controller
- Side effects tightly coupled to triggering code
- No audit trail of "what events exist"

### 11.2 The Solution: Event Publisher

```ruby
# app/events/publisher.rb
require "dry/events"

class EventPublisher
  include Dry::Events::Publisher[:app]

  # Profile events
  register_event("profile.viewed")
  register_event("profile.actions_computed")

  # Access request events
  register_event("access.requested")
  register_event("access.approved")
  register_event("access.declined")

  # Chat events
  register_event("chat.room_accessed")

  class << self
    def instance
      @instance ||= new
    end

    def publish(event_name, payload = {})
      return unless should_publish?(event_name)

      instance.publish(event_name, payload.merge(published_at: Time.current))
    end

    def subscribe(listener_or_event, &block)
      if block_given?
        instance.subscribe(listener_or_event, &block)
      else
        instance.subscribe(listener_or_event)
      end
    end

    private

    def should_publish?(event_name)
      return false unless ProfileConfig.config.events.publish_profile_views if event_name.start_with?("profile.")
      return false unless ProfileConfig.config.events.publish_access_events if event_name.start_with?("access.")
      true
    end
  end
end
```

### 11.3 Publishing Events

```ruby
# app/controllers/api/v1/profiles_controller.rb
class ProfilesController < ApplicationController
  def show
    @profile = Profile.find(params[:id])
    context = build_context(@profile)

    # Publish event - side effects handled by subscribers
    EventPublisher.publish("profile.viewed", {
      profile_id: @profile.id,
      viewer_id: current_user&.id,
      viewer_role: current_user&.role
    })

    render json: { data: ProfileBlueprint.render_as_hash(@profile, context: context) }
  end
end

# app/services/profiles/actions_builder.rb
class ActionsBuilder
  def call
    actions = build_actions_struct

    # Publish event with computed data
    EventPublisher.publish("profile.actions_computed", {
      profile_id: profile.id,
      client_user_id: client_user.id,
      access_status: actions.access_status,
      has_chat: actions.chat_id.present?
    })

    Success(actions)
  end
end
```

### 11.4 Subscribing to Events

```ruby
# config/initializers/event_subscribers.rb

# Block-based subscriber
EventPublisher.subscribe("profile.viewed") do |event|
  Analytics.track("profile_view", event.payload)
end

# Object-based subscriber
class AuditListener
  def on_profile_viewed(event)
    AuditLog.create!(
      action: "profile_view",
      resource_type: "Profile",
      resource_id: event.payload[:profile_id],
      user_id: event.payload[:viewer_id],
      occurred_at: event.payload[:published_at]
    )
  end

  def on_access_requested(event)
    AuditLog.create!(action: "access_request", **event.payload)
  end

  def on_access_approved(event)
    AuditLog.create!(action: "access_approval", **event.payload)
  end
end

EventPublisher.subscribe(AuditListener.new)

# Conditional subscriber
class CacheWarmerListener
  def on_profile_viewed(event)
    return unless should_warm_cache?(event.payload[:profile_id])

    ProfileCacheWarmer.perform_async(event.payload[:profile_id])
  end

  private

  def should_warm_cache?(profile_id)
    # Logic to determine if cache should be warmed
  end
end

EventPublisher.subscribe(CacheWarmerListener.new)
```

### 11.5 Before vs After

**Before (controller with inline side effects):**
```ruby
def show
  @profile = Profile.find(params[:id])

  # Side effect #1
  Analytics.track("profile_viewed", { profile_id: @profile.id })

  # Side effect #2
  AuditLog.create!(action: "profile_view", resource: @profile)

  # Side effect #3
  ProfileCacheWarmer.perform_async(@profile.id)

  render json: { data: ProfileBlueprint.render_as_hash(@profile) }
end
```

**After (clean controller, events handle side effects):**
```ruby
def show
  @profile = Profile.find(params[:id])

  EventPublisher.publish("profile.viewed", {
    profile_id: @profile.id,
    viewer_id: current_user&.id
  })

  render json: { data: ProfileBlueprint.render_as_hash(@profile) }
end
```

### 11.6 Testing Events

```ruby
RSpec.describe ProfilesController do
  describe "GET #show" do
    it "publishes profile.viewed event" do
      expect(EventPublisher).to receive(:publish).with(
        "profile.viewed",
        hash_including(profile_id: profile.id, viewer_id: user.id)
      )

      get :show, params: { id: profile.id }
    end
  end
end

RSpec.describe AuditListener do
  describe "#on_profile_viewed" do
    let(:event) { double(payload: { profile_id: 1, viewer_id: 2, published_at: Time.current }) }

    it "creates audit log entry" do
      expect { subject.on_profile_viewed(event) }.to change(AuditLog, :count).by(1)
    end
  end
end
```

### 11.7 Benefits

| Inline Side Effects | dry-events |
|--------------------|------------|
| Mixed with business logic | Separated via pub/sub |
| Hard to test in isolation | Each listener testable |
| Adding effects = modify caller | Adding effects = new subscriber |
| No event catalog | `register_event` documents all |
| Tight coupling | Loose coupling |
| Synchronous only | Async-ready (queue subscribers) |

---

## 12. Other dry-rb Gems Worth Exploring

### 12.1 dry-transaction: Multi-Step Business Operations

Perfect for complex workflows like order processing or user registration:

```ruby
# app/transactions/create_order.rb
class CreateOrder
  include Dry::Transaction

  step :validate
  step :create_order
  step :charge_payment
  step :send_confirmation

  private

  def validate(input)
    contract = OrderContract.new
    result = contract.call(input)
    result.success? ? Success(result.to_h) : Failure(result.errors)
  end

  def create_order(input)
    order = Order.create!(input)
    Success(order)
  rescue ActiveRecord::RecordInvalid => e
    Failure(e.message)
  end

  def charge_payment(order)
    # Payment logic...
    Success(order)
  end

  def send_confirmation(order)
    OrderMailer.confirmation(order).deliver_later
    Success(order)
  end
end

# Usage
result = CreateOrder.new.call(order_params)
result.success? # => true/false
```

### 12.2 dry-effects: Algebraic Effects

Advanced: dependency injection via effects (alternative to dry-container):

```ruby
class ProcessPayment
  include Dry::Effects.Reader(:current_user)
  include Dry::Effects.Resolve(:payment_gateway)

  def call(amount)
    gateway = resolve(:payment_gateway)
    gateway.charge(current_user, amount)
  end
end

# Provide effects at call site
result = Dry::Effects.handler.with(
  current_user: user,
  resolve: { payment_gateway: StripeGateway.new }
) { ProcessPayment.new.call(100) }
```

### 12.3 Gem Selection Guide

| Gem | When to Use | Complexity |
|-----|-------------|------------|
| **dry-types** | Any project (foundational) | Low |
| **dry-struct** | Data transfer objects, value objects | Low |
| **dry-configurable** | Configuration management | Low |
| **dry-initializer** | Service object parameters | Low |
| **dry-monads** | Service objects with failures | Medium |
| **dry-validation** | API input validation | Medium |
| **dry-container** | Large apps, testing focus | Medium |
| **dry-matcher** | Result pattern matching | Medium |
| **dry-events** | Event-driven architecture | Medium |
| **dry-transaction** | Multi-step workflows | Medium |
| **dry-effects** | Advanced FP patterns | High |

---

## 13. Benefits and Tradeoffs

### 13.1 Benefits

**1. Explicit Over Implicit**
```ruby
# Before: What can access_status be? Check the code...
result[:access_status] = ACCESS_STATUS_VALUES.include?(status) ? status : "none"

# After: The type IS the documentation
attribute :access_status, Types::Profiles::AccessStatus  # Enum is explicit
```

**2. Testability**
```ruby
# Before: Test through controller/blueprint
it "returns correct access_status" do
  get "/profiles/1", headers: auth_headers
  expect(response.body).to include('"access_status":"approved"')
end

# After: Unit test the struct directly
it "coerces invalid status to none" do
  actions = Profiles::Actions.new(access_status: "invalid")
  expect(actions.access_status).to eq("none")
end
```

**3. Composability**
```ruby
# Combine types to build complex structures
CompanyProfile = Types::Hash.schema(
  name: Types::String,
  employees: Types::Array.of(EmployeeStruct),
  settings: Types::Hash.schema(
    visibility: Types::Profiles::VisibilityMode,
    features: Types::Array.of(Types::String)
  )
)
```

**4. Error Messages**
```ruby
# dry-validation provides structured errors
contract.call(thumb_status: "invalid").errors.to_h
# => { thumb_status: ["must be one of: liked, disliked"] }
```

**5. Event-Driven Architecture**
```ruby
# Before: Side effects scattered in controllers
Analytics.track(...)
AuditLog.create!(...)
CacheWarmer.perform_async(...)

# After: Single event, multiple handlers
EventPublisher.publish("profile.viewed", { ... })
```

**6. Centralized Configuration**
```ruby
# Before: grep -r "CACHE_TTL" app/
# After: ProfileConfig.config.actions.cache_ttl
```

### 13.2 Tradeoffs

**1. Learning Curve**
- Team needs to learn dry-rb idioms
- Functional programming concepts (monads, composition)
- More files/classes than "Rails way"

**2. Indirection**
- Types defined in one place, used in another
- Following data flow requires understanding container
- Events may be handled far from where they're published

**3. Overhead for Simple Cases**
```ruby
# For a simple boolean flag, this is overkill:
attribute :is_active, Types::Bool.default(false)

# This is fine:
attr_accessor :is_active
```

**4. Gems Add Dependencies**
- 11 gems for full suite
- Version compatibility to manage
- Bundle size increases

### 13.3 When to Use dry-rb

**✅ Good Fit:**
- APIs with complex data contracts
- Services with multiple failure modes
- Apps where testability is priority
- Teams comfortable with FP concepts
- Large apps with many developers
- Event-driven or audit-heavy systems

**❌ Poor Fit:**
- Simple CRUD apps
- Prototypes/MVPs
- Teams unfamiliar with FP
- Performance-critical hot paths (slight overhead)

---

## 14. Conclusion

Integrating dry-rb into our Rails API transformed code that "worked" into code that's **obvious, testable, and maintainable**:

| Metric | Before | After |
|--------|--------|-------|
| Actions payload code | 70+ lines | 15 lines |
| Type validation | Manual per-field | Declarative |
| Error handling | try/rescue + nil | Result monad |
| Dependencies | Hard-coded classes | Injected |
| Configuration | Scattered constants | Centralized |
| Side effects | Inline in controllers | Event-driven |
| Service parameters | Manual initialize | Declarative DSL |
| Result handling | if/case statements | Pattern matching |
| Test isolation | Integration only | Unit + integration |
| Gems used | 0 | 11 |

### Key Takeaways

1. **Start with dry-types** — It's foundational and low-risk
2. **Add dry-struct for data transfer** — Especially for API responses
3. **Use dry-monads in services** — Replace boolean/nil returns
4. **Add dry-validation for API inputs** — Before data hits your models
5. **Use dry-configurable early** — Centralize config before it scatters
6. **Add dry-initializer to services** — Reduce boilerplate immediately
7. **Introduce dry-container gradually** — When testing pain increases
8. **Add dry-matcher for cleaner controllers** — Pattern matching is elegant
9. **Use dry-events for side effects** — Decouple analytics, logging, notifications
10. **Don't over-engineer** — A simple hash is fine for simple data

### The Return on Investment

The initial investment—learning curves, refactoring, new patterns—pays dividends in:

- **Fewer bugs** — Type mismatches caught at construction, not runtime
- **Faster debugging** — Follow explicit contracts, not implicit conventions
- **Easier onboarding** — Types and events document themselves
- **Confident refactoring** — Change implementation, types verify compatibility
- **Testable architecture** — Unit test components in isolation
- **Scalable patterns** — Event-driven architecture grows with your app

dry-rb doesn't replace Rails conventions—it **complements them** where they fall short. Use the right tool for each job.

---

## Resources

- **dry-rb Official Site**: [dry-rb.org](https://dry-rb.org/)
- **dry-rb GitHub**: [github.com/dry-rb](https://github.com/dry-rb)
- **dry-types Documentation**: [dry-rb.org/gems/dry-types](https://dry-rb.org/gems/dry-types)
- **dry-monads Documentation**: [dry-rb.org/gems/dry-monads](https://dry-rb.org/gems/dry-monads)
- **dry-validation Documentation**: [dry-rb.org/gems/dry-validation](https://dry-rb.org/gems/dry-validation)
- **dry-events Documentation**: [dry-rb.org/gems/dry-events](https://dry-rb.org/gems/dry-events)
- **dry-configurable Documentation**: [dry-rb.org/gems/dry-configurable](https://dry-rb.org/gems/dry-configurable)
- **dry-initializer Documentation**: [dry-rb.org/gems/dry-initializer](https://dry-rb.org/gems/dry-initializer)
- **dry-matcher Documentation**: [dry-rb.org/gems/dry-matcher](https://dry-rb.org/gems/dry-matcher)
- **Trailblazer (alternative)**: [trailblazer.to](https://trailblazer.to/) (uses dry-rb under the hood)

---

*This post documents our integration of 11 dry-rb gems into the Wigiwork API. The patterns described here reduced our Profile Actions payload logic from 70+ lines to 15, improved test coverage, established event-driven architecture, and created patterns that scale across 100+ endpoints.*

