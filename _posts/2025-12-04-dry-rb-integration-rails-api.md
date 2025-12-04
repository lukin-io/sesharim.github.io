---
layout: post
title: "From Rails Spaghetti to Structured Code: Integrating dry-rb into Your API"
date: 2025-12-04
author: Max Lukin
tags: [rails, dry-rb, functional-programming, refactoring, types, validation, architecture]
categories: [engineering, rails, best-practices, refactoring]
description: "A practical guide to integrating dry-rb gems into your Ruby on Rails API—showing real before/after examples of how dry-types, dry-struct, dry-monads, dry-validation, and dry-container improve maintainability, testability, and code clarity."
---

> _"The best code isn't clever—it's obvious. dry-rb makes Rails code obvious."_

Every Rails developer has written code that works but feels wrong. Manual type coercion scattered across controllers. Validation logic duplicated between models and services. Deeply nested conditionals handling success and failure cases. These patterns work, but they accumulate into technical debt.

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
8. [Other dry-rb Gems Worth Exploring](#8-other-dry-rb-gems-worth-exploring)
9. [Benefits and Tradeoffs](#9-benefits-and-tradeoffs)
10. [Conclusion](#10-conclusion)

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
  def self.[](*keys)
    Module.new do
      keys.each do |key|
        define_method(key) do
          ivar = "@_dep_#{key}"
          return instance_variable_get(ivar) if instance_variable_defined?(ivar)
          instance_variable_set(ivar, AppContainer.resolve(key))
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
  include Deps[:actions_builder, :visibility_flags]  # Inject dependencies

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

## 8. Other dry-rb Gems Worth Exploring

### 8.1 dry-transaction: Multi-Step Business Operations

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

### 8.2 dry-matcher: Pattern Matching for Results

Elegant handling of different result types:

```ruby
# Define matcher
require "dry/matcher/result_matcher"

# Use in controller
Dry::Matcher::ResultMatcher.call(result) do |m|
  m.success do |value|
    render json: { data: value }, status: :ok
  end

  m.failure :validation do |errors|
    render json: { errors: errors }, status: :unprocessable_entity
  end

  m.failure :not_found do
    head :not_found
  end

  m.failure do |error|
    render json: { error: error }, status: :internal_server_error
  end
end
```

### 8.3 dry-configurable: Thread-Safe Configuration

Replace scattered constants with structured config:

```ruby
# app/config/profile_config.rb
class ProfileConfig
  extend Dry::Configurable

  setting :max_skills, default: 50
  setting :cache_ttl, default: 1.hour
  setting :visibility_modes, default: %w[public private friends]

  setting :api do
    setting :rate_limit, default: 100
    setting :timeout, default: 30
  end
end

# Usage
ProfileConfig.config.max_skills           # => 50
ProfileConfig.config.api.rate_limit       # => 100

# Override in tests
ProfileConfig.configure { |c| c.max_skills = 10 }
```

### 8.4 dry-effects: Algebraic Effects

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

### 8.5 Gem Selection Guide

| Gem | When to Use | Complexity |
|-----|-------------|------------|
| **dry-types** | Any project (foundational) | Low |
| **dry-struct** | Data transfer objects, value objects | Low |
| **dry-monads** | Service objects with failures | Medium |
| **dry-validation** | API input validation | Medium |
| **dry-container** | Large apps, testing focus | Medium |
| **dry-transaction** | Multi-step workflows | Medium |
| **dry-configurable** | Complex configuration | Low |
| **dry-effects** | Advanced FP patterns | High |

---

## 9. Benefits and Tradeoffs

### 9.1 Benefits

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

### 9.2 Tradeoffs

**1. Learning Curve**
- Team needs to learn dry-rb idioms
- Functional programming concepts (monads, composition)
- More files/classes than "Rails way"

**2. Indirection**
- Types defined in one place, used in another
- Following data flow requires understanding container
- Debugging may span multiple abstractions

**3. Overhead for Simple Cases**
```ruby
# For a simple boolean flag, this is overkill:
attribute :is_active, Types::Bool.default(false)

# This is fine:
attr_accessor :is_active
```

**4. Gems Add Dependencies**
- 7 gems for full suite
- Version compatibility to manage
- Bundle size increases

### 9.3 When to Use dry-rb

**✅ Good Fit:**
- APIs with complex data contracts
- Services with multiple failure modes
- Apps where testability is priority
- Teams comfortable with FP concepts
- Large apps with many developers

**❌ Poor Fit:**
- Simple CRUD apps
- Prototypes/MVPs
- Teams unfamiliar with FP
- Performance-critical hot paths (slight overhead)

---

## 10. Conclusion

Integrating dry-rb into our Rails API transformed code that "worked" into code that's **obvious, testable, and maintainable**:

| Metric | Before | After |
|--------|--------|-------|
| Actions payload code | 70+ lines | 15 lines |
| Type validation | Manual per-field | Declarative |
| Error handling | try/rescue + nil | Result monad |
| Dependencies | Hard-coded classes | Injected |
| Test isolation | Integration only | Unit + integration |

### Key Takeaways

1. **Start with dry-types** — It's foundational and low-risk
2. **Add dry-struct for data transfer** — Especially for API responses
3. **Use dry-monads in services** — Replace boolean/nil returns
4. **Add dry-validation for API inputs** — Before data hits your models
5. **Introduce dry-container gradually** — When testing pain increases
6. **Don't over-engineer** — A simple hash is fine for simple data

### The Return on Investment

The initial investment—learning curves, refactoring, new patterns—pays dividends in:

- **Fewer bugs** — Type mismatches caught at construction, not runtime
- **Faster debugging** — Follow explicit contracts, not implicit conventions
- **Easier onboarding** — Types document themselves
- **Confident refactoring** — Change implementation, types verify compatibility

dry-rb doesn't replace Rails conventions—it **complements them** where they fall short. Use the right tool for each job.

---

## Resources

- **dry-rb Official Site**: [dry-rb.org](https://dry-rb.org/)
- **dry-rb GitHub**: [github.com/dry-rb](https://github.com/dry-rb)
- **dry-types Documentation**: [dry-rb.org/gems/dry-types](https://dry-rb.org/gems/dry-types)
- **dry-monads Documentation**: [dry-rb.org/gems/dry-monads](https://dry-rb.org/gems/dry-monads)
- **dry-validation Documentation**: [dry-rb.org/gems/dry-validation](https://dry-rb.org/gems/dry-validation)
- **Trailblazer (alternative)**: [trailblazer.to](https://trailblazer.to/) (uses dry-rb under the hood)

---

*This post documents our integration of dry-rb gems into the Wigiwork API. The patterns described here reduced our Profile Actions payload logic from 70+ lines to 15, improved test coverage, and established patterns that scale across 100+ endpoints.*

