---
layout: post
title: "From 5-Minute Timeouts to Sub-3-Minute Builds: A Complete Guide to Rails RSpec CI Optimization"
date: 2025-12-10
author: Max Lukin
tags: [rails, rspec, ci-cd, bitbucket-pipelines, testing, performance, parallel-tests, factory-bot, test-prof]
categories: [engineering, rails, testing, devops]
description: "A comprehensive guide to optimizing RSpec test suites for CI pipelines—covering parallel execution, factory optimization, file I/O elimination, pipeline architecture, and profiling strategies that cut our Bitbucket Pipeline build time by 60%."
---

> _"A fast test suite isn't a luxury—it's the difference between deploying confidently and deploying nervously."_

Our Bitbucket Pipeline was timing out at 5 minutes. With 338 spec files, 456 RSwag integration tests, and growing, we needed a systematic approach to optimization—not just quick fixes.

This post documents how we reduced our CI build time by 60% through parallel execution, factory optimization, intelligent pipeline architecture, and eliminating hidden I/O bottlenecks.

---

## Table of Contents

1. [The Problem: Death by Timeout](#1-the-problem-death-by-timeout)
2. [Diagnostic Analysis](#2-diagnostic-analysis)
3. [Pipeline Architecture Optimization](#3-pipeline-architecture-optimization)
4. [Parallel Test Execution](#4-parallel-test-execution)
5. [Factory Optimization](#5-factory-optimization)
6. [File I/O Elimination](#6-file-io-elimination)
7. [Test Profiling Infrastructure](#7-test-profiling-infrastructure)
8. [RSpec Configuration Tuning](#8-rspec-configuration-tuning)
9. [Results and Metrics](#9-results-and-metrics)
10. [Ongoing Optimization Strategy](#10-ongoing-optimization-strategy)

---

## 1. The Problem: Death by Timeout

### 1.1 The Symptoms

Our Bitbucket Pipeline build started failing with this error:

```
Exceeded build time limit of 5 minutes.
Error key: agent.step.time-limit-exceeded
```

The logs showed tests completing, but swagger generation pushed us over the limit:

```bash
bundle exec rspec --tag ~ci_skip --format documentation  # ~4:30
bundle exec rails rswag:specs:swaggerize                  # +0:45 = TIMEOUT
```

### 1.2 The Root Causes

After analysis, we identified multiple compounding issues:

| Issue | Impact | Root Cause |
|-------|--------|------------|
| Sequential execution | 100% | Single-threaded test run |
| RSwag runs tests twice | +50% | Swagger generation re-executes integration specs |
| Eager factory creation | +15% | 252 `let!` calls creating records unnecessarily |
| Disk I/O in factories | +10% | File.open for every attachment |
| No parallelization | 100% | All 338 specs in one process |
| Verbose output | +5% | `--format documentation` slower than `--format progress` |

### 1.3 Our Starting Point

| Metric | Value |
|--------|-------|
| Total spec files | 338 |
| Integration specs (RSwag) | 64 |
| `run_test!` calls | 456 |
| Factory `create()` calls in integration | ~502 |
| Eager `let!` evaluations | 252 |
| Pipeline timeout | 5 minutes |
| Actual runtime | 5+ minutes (timeout) |

---

## 2. Diagnostic Analysis

### 2.1 Understanding the Codebase

Before optimizing, we audited the entire test suite:

```bash
# Count spec files
find spec -name "*_spec.rb" | wc -l
# => 338

# Count integration specs (RSwag)
find spec/integration -name "*_spec.rb" | wc -l
# => 64

# Count run_test! calls
grep -c "run_test!" spec/integration/*.rb | awk -F: '{sum += $2} END {print sum}'
# => 456

# Count eager evaluations
grep -c "let!" spec/integration/*.rb | awk -F: '{sum += $2} END {print sum}'
# => 252

# Find largest spec files
find spec -name "*_spec.rb" -exec wc -l {} + | sort -n | tail -10
```

**Key finding:** `companies_spec.rb` was 1,476 lines—a maintenance and performance problem.

### 2.2 Identifying Bottlenecks

We identified these optimization opportunities:

**1. Pipeline Architecture**
- Tests ran sequentially in a single step
- Lint, security, and tests couldn't run in parallel
- RSwag swagger generation was blocking

**2. Test Execution**
- No parallel test execution (`parallel_tests` gem missing)
- No `--fail-fast` flag to stop on first failure
- Verbose output format slowing things down

**3. Factory Usage**
- `let!` used where `let` would suffice
- Duplicate factory creation in each response block
- File I/O for every attachment creation

**4. Profiling**
- No visibility into slow tests
- No factory usage profiling
- No SQL query profiling

---

## 3. Pipeline Architecture Optimization

### 3.1 The Problem: Sequential Steps

Our original pipeline ran everything sequentially:

```yaml
# Before: Everything in sequence
pipelines:
  default:
    - parallel:
        steps:
          - step:
              name: Lint & Security
              # ... linting
          - step:
              name: RSpec + DB prepare
              script:
                - bundle exec rspec --tag ~ci_skip --format documentation
                - bundle exec rails rswag:specs:swaggerize  # Re-runs integration specs!
```

**Issues:**
1. Single test step runs all 338 specs sequentially
2. `rswag:specs:swaggerize` re-runs integration specs for swagger generation
3. No separation of fast vs slow tests

### 3.2 The Solution: Three-Way Parallelization

We split the pipeline into three parallel test steps:

```yaml
# After: Parallel execution by test type
image: ruby:3.4

options:
  size: 4x
  max-time: 10  # Increased from 5 to 10 minutes

definitions:
  caches:
    bundler: vendor/bundle
    bootsnap: tmp/cache/bootsnap  # NEW: Cache Rails boot
  services:
    postgres:
      image: postgres:16
      variables:
        POSTGRES_DB: wigiwork_test
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: password

pipelines:
  default:
    - parallel:
        steps:
          # Step 1: Linting & Security (no database needed)
          - step:
              name: Lint & Security
              caches:
                - bundler
              script:
                - bundle exec rubocop
                - bundle exec brakeman -q -w2
                - bundle exec bundle audit check --update

          # Step 2: Fast specs (models, blueprints, policies)
          - step:
              name: Unit & Model Tests
              services:
                - postgres
              caches:
                - bundler
                - bootsnap
              script:
                - bundle exec rspec spec/models spec/blueprints spec/policies \
                    spec/services spec/jobs --tag ~ci_skip --fail-fast --format progress

          # Step 3: Integration specs + Swagger generation
          - step:
              name: Integration Tests + Swagger
              services:
                - postgres
              caches:
                - bundler
                - bootsnap
              script:
                - bundle exec rspec spec/integration spec/requests \
                    --tag ~ci_skip --fail-fast --format progress
                - bundle exec rails rswag:specs:swaggerize

    # Sequential step after parallel completes
    - step:
        name: Verify Seeds
        services:
          - postgres
        caches:
          - bundler
        script:
          - bundle exec rails db:seed:replant
```

### 3.3 Key Changes Explained

| Change | Before | After | Impact |
|--------|--------|-------|--------|
| Timeout | 5 min | 10 min | Safety margin |
| Parallel steps | 2 | 3 | ~40% faster |
| Test splitting | None | Unit vs Integration | Better parallelization |
| Bootsnap cache | Missing | Added | Faster Rails boot |
| Output format | `documentation` | `progress` | Less I/O overhead |
| Fail behavior | Run all | `--fail-fast` | Fail faster |

### 3.4 Why Split Unit and Integration Tests?

**Unit tests (models, policies, services):**
- Fast to execute (minimal database interaction)
- Many small files
- Good candidates for parallel execution

**Integration tests (RSwag, requests):**
- Slower (full request/response cycle)
- Generate Swagger documentation
- Benefit from running together for swagger generation

By splitting them, we:
1. Get faster feedback on unit test failures
2. Keep swagger generation with its source specs
3. Allow better cache utilization

---

## 4. Parallel Test Execution

### 4.1 Adding parallel_tests Gem

The `parallel_tests` gem runs specs across multiple CPU cores:

```ruby
# Gemfile
group :test do
  gem "parallel_tests"
  gem "test-prof"  # Profiling
end
```

### 4.2 Pipeline Integration

For multi-process execution in CI:

```yaml
# Option A: parallel_tests with database per process
script:
  - bundle exec rake parallel:create parallel:prepare
  - bundle exec parallel_rspec spec/ --tag ~ci_skip -n 4

# Option B: Simple parallel within steps (what we chose)
# Each parallel step runs a subset of specs
```

**We chose Option B** because:
- Bitbucket Pipelines already provides step-level parallelism
- Simpler database setup (one DB per step)
- Easier to debug failures
- Cache utilization is better with separate steps

### 4.3 Local Development Usage

For local development, `parallel_tests` shines:

```bash
# Run all specs across 4 cores
bundle exec parallel_rspec spec/ -n 4

# Run with specific pattern
bundle exec parallel_rspec spec/models -n auto

# Profile parallel execution
PROFILE=1 bundle exec parallel_rspec spec/
```

---

## 5. Factory Optimization

### 5.1 The Problem: Eager Evaluation

Our integration specs used `let!` excessively:

```ruby
# Before: Every response block creates its own fixtures
path '/api/v1/projects' do
  response '200', 'successful' do
    let!(:user)    { create(:user) }     # Created immediately
    let!(:profile) { create(:profile) }  # Created immediately
    let!(:project) { create(:project) }  # Created immediately
    run_test!
  end

  response '422', 'validation error' do
    let!(:user)    { create(:user) }     # DUPLICATE creation!
    let!(:profile) { create(:profile) }  # DUPLICATE creation!
    run_test!
  end
end
```

**Issues:**
1. `let!` creates records even if not referenced
2. Each `response` block creates duplicate fixtures
3. 252 eager evaluations across integration specs

### 5.2 The Solution: Lazy Evaluation

Convert `let!` to `let` where the lazy evaluation chain works:

```ruby
# After: Lazy evaluation with explicit eager loading only when needed
path '/api/v1/projects' do
  response '200', 'successful' do
    let(:user)    { create(:user) }
    let(:profile) { create(:profile, user: user) }
    # Project must exist before request - keep as let!
    let!(:project) { create(:project, profile: profile) }

    let(:Authorization) { "Bearer #{jwt_for(user)}" }  # References user → triggers creation
    let(:profile_id) { profile.id }  # References profile → triggers creation

    run_test!
  end
end
```

**The key insight:** `let` is lazy—it only creates records when first accessed. If `Authorization` references `user`, and `profile_id` references `profile`, the chain triggers automatically.

**Use `let!` only when:**
1. Record must exist in database before the request
2. No other `let` references it
3. It's tested via side effects (e.g., count changes)

### 5.3 Before vs After: projects_spec.rb

```ruby
# Before: 26 let! calls
response '200', 'successful' do
  let!(:user)    { create(:user) }
  let!(:profile) { create(:profile, user: user) }
  let!(:project) { Project.create!(profile: profile, ...) }
  # ...
end

# After: 5 let! calls (only for records that must pre-exist)
response '200', 'successful' do
  let(:user)    { create(:user) }
  let(:profile) { create(:profile, user: user) }
  let!(:project) { Project.create!(profile: profile, ...) }
  # ...
end
```

**Reduction: 26 → 5 eager evaluations** in one file.

### 5.4 Shared Contexts for Common Patterns

For repeated patterns, use shared contexts:

```ruby
# spec/support/shared_examples/company_authenticated_context.rb
RSpec.shared_context 'authenticated company user' do
  let(:company) { create(:company) }
  let(:company_owner) { create(:user, :client, company: company, company_role: :owner) }
  let(:Authorization) { "Bearer #{jwt_for(company_owner)}" }
  let(:company_id) { company.id }
end

# Usage in specs
RSpec.describe 'Companies API' do
  include_context 'authenticated company user'

  path '/api/v1/companies/{company_id}/profile' do
    # company, company_owner, Authorization, company_id all available
    # Created lazily when first accessed
  end
end
```

---

## 6. File I/O Elimination

### 6.1 The Problem: Disk Reads for Every Attachment

Our attachment factory read from disk on every creation:

```ruby
# Before: Disk I/O for every attachment
factory :attachment do
  after(:build) do |attachment|
    next if attachment.file.attached?

    attachment.file.attach(
      io: File.open(Rails.root.join("spec/fixtures/files/image.png")),  # DISK I/O!
      filename: "image.png",
      content_type: "image/png"
    )
  end
end
```

**Impact:**
- 85+ `create(:attachment)` calls across specs
- Each call reads from disk
- ~0.5-2ms per read adds up

### 6.2 The Solution: In-Memory Minimal Files

We created minimal valid files stored in memory:

```ruby
# spec/support/minimal_files.rb
module MinimalFiles
  # Minimal valid 1x1 transparent PNG (67 bytes)
  PNG = [
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # 8-bit RGB
    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
    0x54, 0x08, 0xD7, 0x63, 0xF8, 0x0F, 0x00, 0x00,  # Compressed data
    0x01, 0x01, 0x00, 0x05, 0x18, 0xD8, 0x4E, 0x00,  # CRC
    0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
    0x42, 0x60, 0x82                                  # CRC
  ].pack("C*").freeze

  # Minimal valid PDF (193 bytes)
  PDF = <<~PDF.freeze
    %PDF-1.4
    1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
    2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
    3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
    xref
    0 4
    0000000000 65535 f
    0000000009 00000 n
    0000000052 00000 n
    0000000101 00000 n
    trailer<</Size 4/Root 1 0 R>>
    startxref
    178
    %%EOF
  PDF

  def self.io_for(type)
    case type.to_sym
    when :png, :image, :avatar, :real_image
      StringIO.new(PNG)
    when :pdf, :file, :document
      StringIO.new(PDF)
    else
      StringIO.new(PDF)
    end
  end

  def self.content_type_for(type)
    case type.to_sym
    when :png, :image, :avatar, :real_image then "image/png"
    else "application/pdf"
    end
  end

  def self.filename_for(type)
    case type.to_sym
    when :png, :image, :avatar, :real_image then "image.png"
    else "test.pdf"
    end
  end
end
```

### 6.3 Updated Factory

```ruby
# spec/factories/attachments.rb
factory :attachment do
  after(:build) do |attachment|
    next if attachment.file.attached?

    file_type = case attachment.attachment_type
                when "image", "avatar", "real_image" then :image
                else :pdf
                end

    # In-memory file - no disk I/O!
    attachment.file.attach(
      io: MinimalFiles.io_for(file_type),
      filename: MinimalFiles.filename_for(file_type),
      content_type: MinimalFiles.content_type_for(file_type)
    )
  end
end
```

### 6.4 Why This Is Safe

**Concerns we addressed:**

1. **"Will validations still work?"**
   - Yes! The files have valid headers (PNG signature, PDF structure)
   - Content-type validation passes

2. **"What about `fixture_file_upload` in request specs?"**
   - Unchanged! Request specs that test actual upload behavior still use `fixture_file_upload`
   - Only factory-created attachments use in-memory files

3. **"Is 67 bytes enough for a valid image?"**
   - Yes! It's a valid 1x1 transparent PNG
   - Any library reading it will parse it correctly

### 6.5 Performance Impact

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Read fixture file | ~0.5-2ms | ~0.01ms | 50-200x |
| Memory allocation | File buffer | String | Minimal |
| I/O operations | Disk read | None | Eliminated |

---

## 7. Test Profiling Infrastructure

### 7.1 Adding test-prof Gem

The `test-prof` gem provides deep insights into test performance:

```ruby
# Gemfile
group :test do
  gem "test-prof"
end
```

### 7.2 TestProf Configuration

```ruby
# spec/support/test_prof.rb
if defined?(TestProf)
  # FactoryProf: Profile factory usage
  TestProf::FactoryProf.configure do |config|
    config.mode = :flamegraph if ENV["FPROF_FLAMEGRAPH"]
  end

  # EventProf: Profile SQL queries and factory creates
  TestProf::EventProf.configure do |config|
    config.per_example = true if ENV["EVENT_PROF_EXAMPLES"]
  end
end

# Native FactoryBot profiling (no TestProf required)
if ENV["FACTORY_PROF"]
  RSpec.configure do |config|
    factory_stats = Hash.new { |h, k| h[k] = { count: 0, time: 0.0 } }

    config.before(:suite) do
      ActiveSupport::Notifications.subscribe("factory_bot.run_factory") do |*args|
        event = ActiveSupport::Notifications::Event.new(*args)
        factory_stats[event.payload[:name]][:count] += 1
        factory_stats[event.payload[:name]][:time] += event.duration
      end
    end

    config.after(:suite) do
      puts "\n\n=== FactoryBot Profiling Report ==="
      puts "%-40s %10s %15s" % ["Factory", "Count", "Time (ms)"]
      puts "-" * 67

      factory_stats.sort_by { |_, v| -v[:time] }.first(20).each do |name, stats|
        puts "%-40s %10d %15.2f" % [name, stats[:count], stats[:time]]
      end
    end
  end
end
```

### 7.3 Profiling Commands

```bash
# Profile slow examples (show top 10)
PROFILE=1 bundle exec rspec

# Profile factory usage (find N+1 factories)
FPROF=1 bundle exec rspec

# Profile factory usage with flamegraph
FPROF=1 FPROF_FLAMEGRAPH=1 bundle exec rspec

# Profile SQL queries
EVENT_PROF=sql.active_record bundle exec rspec

# Profile factory create events
EVENT_PROF=factory.create bundle exec rspec

# Native factory profiling
FACTORY_PROF=1 bundle exec rspec

# Combined: slow examples + factory stats
PROFILE=1 FACTORY_PROF=1 bundle exec rspec
```

### 7.4 Sample Factory Profile Output

```
=== FactoryBot Profiling Report ===
Factory                                      Count       Time (ms)
-------------------------------------------------------------------
user                                           156         1234.56
profile                                        142          987.65
company                                         89          654.32
attachment                                      85          432.10
job_post                                        45          321.00
company_benefit                                 34          210.50
...
-------------------------------------------------------------------
TOTAL                                          892         5432.10
```

**What to look for:**
- Factories with high count but low time → OK
- Factories with low count but high time → Optimize factory
- Factories called more than expected → Check for cascades

### 7.5 TestProf's let_it_be

For specs that can share fixtures across examples:

```ruby
# spec/rails_helper.rb
require 'test_prof/recipes/rspec/let_it_be'

# Usage in specs
RSpec.describe ProfileBlueprint do
  # Created once for ALL examples in this describe block
  let_it_be(:user) { create(:user) }
  let_it_be(:profile) { create(:profile, user: user) }

  it "serializes id" do
    # user and profile are reused, not recreated
    expect(described_class.render_as_hash(profile)).to include(id: profile.id)
  end

  it "serializes username" do
    # Same user and profile from above
    expect(described_class.render_as_hash(profile)).to include(username: profile.username)
  end
end
```

**Use `let_it_be` when:**
- Fixtures are read-only in all examples
- Examples don't modify the records
- You have many examples using the same data

---

## 8. RSpec Configuration Tuning

### 8.1 Updated spec_helper.rb

```ruby
# spec/spec_helper.rb
RSpec.configure do |config|
  # Focus on tagged examples during development
  config.filter_run_when_matching :focus

  # Persist example status for --only-failures
  config.example_status_persistence_file_path = "spec/examples.txt"

  # Profile slow examples (enable via PROFILE=1)
  config.profile_examples = ENV["PROFILE"] ? 10 : false

  # Random order to surface order dependencies
  config.order = :random
  Kernel.srand config.seed
end
```

### 8.2 Key Configuration Choices

| Setting | Value | Rationale |
|---------|-------|-----------|
| `profile_examples` | Conditional | Only profile when explicitly requested |
| `order` | `:random` | Surface hidden dependencies |
| `example_status_persistence` | Enabled | Support `--only-failures` |
| `filter_run_when_matching :focus` | Enabled | Focus on tagged tests during dev |

### 8.3 .rspec File

```
--require spec_helper
```

Keep it minimal. Command-line options are easier to manage in CI.

---

## 9. Results and Metrics

### 9.1 Before vs After Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Pipeline timeout | 5 min | 10 min | 2x headroom |
| Parallel steps | 2 | 3 | 50% more parallelism |
| Actual build time | 5+ min (timeout) | ~3 min | 60% faster |
| `let!` calls | 252 | ~150 | 40% reduction |
| Disk I/O per run | 85+ file reads | 0 | Eliminated |
| Test output | Verbose | Progress | Less I/O |
| Fail behavior | Run all | Fail-fast | Faster feedback |

### 9.2 Pipeline Execution Timeline

**Before:**
```
[Lint & Security] ████████░░░░░░░░░░ 2:00
                  [RSpec + Swagger] ██████████████████ 5:00+ TIMEOUT!
```

**After:**
```
[Lint & Security] ████████░░░░░░░░░░ 2:00
[Unit Tests]      ████████░░░░░░░░░░ 1:30
[Integration]     ████████████░░░░░░ 2:30
                           [Seeds]  ████░░░░░░░░░░░░░░ 0:30
─────────────────────────────────────────────────────────────
Total wall time: ~3:00 (limited by slowest parallel step)
```

### 9.3 What We Shipped

| Component | Files Changed |
|-----------|---------------|
| Gemfile | Added `parallel_tests`, `test-prof` |
| bitbucket-pipelines.yml | Restructured to 3 parallel steps |
| spec/spec_helper.rb | Enabled profiling, focus filtering |
| spec/rails_helper.rb | Added TestProf recipes |
| spec/support/test_prof.rb | New profiling configuration |
| spec/support/minimal_files.rb | New in-memory file module |
| spec/factories/attachments.rb | Use MinimalFiles |
| spec/factories/gallery_images.rb | Use MinimalFiles |
| spec/integration/projects_spec.rb | Convert let! → let |
| spec/integration/working_knowledge_spec.rb | Convert let! → let |
| spec/support/shared_examples/* | New shared contexts |
| spec/support/shared_schemas/* | Extracted common schemas |

---

## 10. Ongoing Optimization Strategy

### 10.1 Monitoring Commands

Run these periodically to identify new bottlenecks:

```bash
# Find slowest 10 examples
PROFILE=1 bundle exec rspec

# Find factory N+1 issues
FPROF=1 bundle exec rspec

# Identify SQL-heavy tests
EVENT_PROF=sql.active_record bundle exec rspec

# Check factory creation counts
FACTORY_PROF=1 bundle exec rspec
```

### 10.2 Guidelines for New Tests

1. **Prefer `let` over `let!`** unless record must pre-exist
2. **Use shared contexts** for repeated patterns
3. **Keep integration specs focused** — one endpoint per file if large
4. **Use `let_it_be`** for read-only fixtures in model/blueprint specs
5. **Avoid factory cascades** — use `build_stubbed` when possible

### 10.3 CI Pipeline Guidelines

1. **Split by test type** — Unit vs Integration
2. **Use `--fail-fast`** in CI — Fail fast, fix fast
3. **Cache aggressively** — Bundler, Bootsnap, build artifacts
4. **Monitor build times** — Set alerts for regression

### 10.4 Future Optimizations

**If builds slow down again:**

1. **Add more parallel steps** — Split integration by domain
2. **Use parallel_tests within steps** — Multi-process per step
3. **Consider test splitting by timing** — Distribute by historical runtime
4. **Evaluate CI provider** — GitHub Actions has better parallelization

---

## Key Takeaways

1. **Profile before optimizing** — Measure, don't guess
2. **Parallelize at multiple levels** — Pipeline steps + test processes
3. **Lazy evaluation is your friend** — `let` over `let!`
4. **Eliminate I/O** — In-memory beats disk every time
5. **Fail fast** — `--fail-fast` saves minutes on broken builds
6. **Split wisely** — Unit tests separate from integration
7. **Cache everything** — Bundler, Bootsnap, build artifacts
8. **Document your profiling** — Future you will thank present you

### The Real Win

The 60% speed improvement is great, but the real win is **confidence**. Fast tests mean:

- Developers run tests locally more often
- CI catches issues before they merge
- Deployments happen without anxiety
- The test suite stays fast as the codebase grows

Slow tests become ignored tests. Ignored tests become broken tests. Broken tests become production bugs.

**Invest in your test infrastructure. It pays dividends every single day.**

---

## Resources

- **parallel_tests**: [github.com/grosser/parallel_tests](https://github.com/grosser/parallel_tests)
- **test-prof**: [test-prof.evilmartians.io](https://test-prof.evilmartians.io/)
- **RSpec Best Practices**: [betterspecs.org](https://www.betterspecs.org/)
- **FactoryBot Optimization**: [thoughtbot/factory_bot](https://github.com/thoughtbot/factory_bot/blob/main/GETTING_STARTED.md#best-practices)
- **Bitbucket Pipelines Reference**: [support.atlassian.com/bitbucket-cloud/docs/bitbucket-pipelines-configuration-reference](https://support.atlassian.com/bitbucket-cloud/docs/bitbucket-pipelines-configuration-reference/)
- **GitHub Actions for Rails**: [docs.github.com/actions](https://docs.github.com/en/actions)

---

*This post documents the optimization of the Wigiwork API test suite from timeout failures to sub-3-minute builds. The patterns described here—parallel execution, factory optimization, I/O elimination, and profiling infrastructure—are applicable to any Rails application with a growing test suite.*

