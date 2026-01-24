---
layout: post
title: "From Monolithic Seeds to Enterprise-Ready Data Generation: Building a Scalable Rails Seed System"
date: 2026-01-24
author: Max Lukin
tags: [rails, database, seeding, testing, refactoring, architecture, performance, qa, ai-training]
categories: [engineering, rails, best-practices, architecture]
description: "A comprehensive guide to building an enterprise-grade database seeding system in Rails—from a 3,600-line monolith to a modular architecture supporting 100k+ full candidate profiles with skills, work experiences, education, and all associations for AI training, QA stress testing, and frontend performance validation."
---

> _"Good seed data is the difference between a demo that impresses and a demo that embarrasses."_

Every growing Rails application faces the same challenge: how do you populate your database with realistic data for development, demos, testing, and stakeholder presentations? Simple `db/seeds.rb` files work for small projects, but as your application scales, so do your seeding requirements.

This post documents how we transformed a 3,600-line monolithic seed file into an enterprise-ready data generation system that creates 100,000+ full candidate profiles with all associations—serving AI training, QA stress testing, and frontend performance validation.

---

## Table of Contents

1. [The Problem: Why Seed Data Matters](#1-the-problem-why-seed-data-matters)
2. [Before: The Monolithic Nightmare](#2-before-the-monolithic-nightmare)
3. [The Refactoring Journey](#3-the-refactoring-journey)
4. [Feature 1: Modular Step Architecture](#4-feature-1-modular-step-architecture)
5. [Feature 2: Context Object for State Management](#5-feature-2-context-object-for-state-management)
6. [Feature 3: Conditional Execution via ENV Flags](#6-feature-3-conditional-execution-via-env-flags)
7. [Feature 4: Progress Reporting with Timing](#7-feature-4-progress-reporting-with-timing)
8. [Feature 5: Post-Seed Data Validation](#8-feature-5-post-seed-data-validation)
9. [Feature 6: 100k+ Full Profile Scaling](#9-feature-6-100k-full-profile-scaling)
10. [Benefits and Use Cases](#10-benefits-and-use-cases)
11. [Testing the Seed System](#11-testing-the-seed-system)
12. [Three Bonus Ideas Worth Implementing](#12-three-bonus-ideas-worth-implementing)
13. [Conclusion](#13-conclusion)

---

## 1. The Problem: Why Seed Data Matters

### 1.1 Who Uses Seed Data?

| Stakeholder | What They Need | Why It Matters |
|-------------|----------------|----------------|
| **Frontend Developers** | Realistic UI data | Test pagination, search, empty states |
| **Backend Developers** | Consistent test fixtures | Debug API responses locally |
| **QA Team** | Volume for stress testing | Find N+1 queries, memory leaks |
| **AI/ML Team** | Training data at scale | Validate models with realistic distributions |
| **Product Managers** | Demo-ready environments | Impress stakeholders, test features |
| **CEO/Leadership** | Production-like demos | Investor presentations, board meetings |
| **New Engineers** | Quick environment setup | Onboard in minutes, not hours |

### 1.2 The Reality Check

Most Rails projects start with something like this:

```ruby
# db/seeds.rb
User.create!(email: 'admin@example.com', password: 'password')
Company.create!(name: 'Test Company')
# ... done
```

Then requirements grow:
- "We need 50 users with different roles"
- "Profiles need skills, work experiences, education"
- "QA needs 100,000 profiles for load testing"
- "AI team needs realistic job title distributions"
- "CEO wants the demo to look like a real platform"

Before you know it, your seed file is 3,600 lines of spaghetti.

### 1.3 Our Starting Point

| Metric | Value |
|--------|-------|
| Seed file size | 3,610 lines |
| Total methods | 59 |
| Instance variables | 8 (shared state) |
| Dependencies | Complex, undocumented |
| Test coverage | 0% |
| Documentation | None |

**Pain points:**
- ❌ Changes broke unrelated features
- ❌ No way to run individual steps
- ❌ No progress indication
- ❌ No validation of seeded data
- ❌ Impossible to scale to 100k records
- ❌ New engineers couldn't understand the flow

---

## 2. Before: The Monolithic Nightmare

### 2.1 The Original Structure

```ruby
# db/seeds/steps.rb - 3,610 lines!
module Seeds
  module Steps
    class << self
      def run
        seed_predefined_avatar_assets
        seed_company
        seed_job_titles
        seed_admin_users
        # ... 32 more method calls
        print_summary
      end

      private

      def seed_company
        @company = Company.find_or_initialize_by(name: 'Bluegeko')
        @company.assign_attributes(
          # ... 50 lines of attributes
        )
        @company.save!
        
        # ... 200 more lines for demo companies
      end

      def seed_admin_users
        @admin_user = User.find_or_initialize_by(email: 'admin@bluegeko.com')
        # ... 300 lines
      end

      # ... 56 more methods
    end
  end
end
```

### 2.2 The Problems

| Problem | Impact |
|---------|--------|
| **Single 3,600-line file** | IDE struggles, git conflicts |
| **Implicit dependencies** | Can't run steps individually |
| **Instance variable soup** | `@company` used 28 times across methods |
| **No progress feedback** | "Is it stuck or working?" |
| **No validation** | Broken seeds discovered in production demos |
| **No scalability** | Creating 100k records = 100k individual inserts |
| **Zero documentation** | New engineers lost for days |

### 2.3 Instance Variable Reference Count

| Variable | References |
|----------|-----------|
| `@company` | 28 |
| `@admin_user` | 18 |
| `@candidate_demo_user` | 15 |
| `@access_request_user` | 14 |
| `@standard_user` | 8 |
| `@full_data_candidate_users` | 5 |
| `@demo_job_posts` | 5 |
| `@admin_profile` | 2 |

These shared variables made refactoring terrifying—change one method, break five others.

---

## 3. The Refactoring Journey

### 3.1 Implementation Priority Matrix

| # | Feature | Effort | Priority | Status |
|---|---------|--------|----------|--------|
| 1 | Modular step architecture | High | Critical | ✅ Done |
| 3 | Conditional ENV flags | Low | High | ✅ Done |
| 4 | Context object | Medium | High | ✅ Done |
| 5 | Progress + timing | Medium | High | ✅ Done |
| 6 | Data validation | Low | High | ✅ Done |
| 7 | 100k batch processing | High | Very High | ✅ Done |
| 2 | Parallel execution | Medium-High | Medium | ⏳ Future |

### 3.2 Final Architecture

```
db/seeds/
├── seeds.rb                    # Entry point (29 lines)
├── support.rb                  # Helpers (387 lines)
├── reference_data.rb           # Lookup tables (889 lines)
├── steps.rb                    # Orchestrator (217 lines)
├── context.rb                  # State management (233 lines)
├── timing.rb                   # Progress tracking (186 lines)
├── validation.rb               # Data integrity (331 lines)
├── batch_profiles.rb           # 100k scaling (825 lines)
├── README.md                   # Documentation (1,797 lines)
├── SEEDS_REFACTORING.md        # Implementation notes (643 lines)
└── steps/                      # 37 individual step files
    ├── 01_predefined_avatar_assets.rb
    ├── 02_company.rb
    ├── ...
    └── 37_batch_profiles.rb
```

**Result: 3,610 lines → 37 focused files averaging 80 lines each**

---

## 4. Feature 1: Modular Step Architecture

### 4.1 The Approach: Singleton Class Reopening

Instead of a massive refactor, we used Ruby's ability to reopen classes:

```ruby
# db/seeds/steps/02_company.rb
module Seeds
  module Steps
    class << self
      private

      def seed_company
        ctx.company = Company.find_or_initialize_by(name: "Bluegeko")
        ctx.company.assign_attributes(company_attributes)
        ctx.company.save!

        log_seed "Company upserted: #{ctx.company.name}"
        seed_demo_companies
      end

      def company_attributes
        {
          industry: "Technology",
          website_url: "https://bluegeko.com",
          # ... attributes
        }
      end
    end
  end
end
```

### 4.2 Orchestrator Pattern

The main `steps.rb` became a thin orchestrator:

```ruby
# db/seeds/steps.rb
module Seeds
  module Steps
    OPTIONAL_STEPS = {
      seed_reports: "SKIP_SEED_REPORTS",
      seed_full_data_candidates: "SEED_FULL_CANDIDATES",
      seed_batch_profiles: "CREATE_BATCH_PROFILES"
    }.freeze

    class << self
      def run
        initialize_context
        Seeds::Support::Timing.start_run(all_steps.size)

        # Execute steps in order
        run_step :seed_predefined_avatar_assets
        run_step :seed_company
        run_step :seed_job_titles
        # ... 34 more steps
        run_step :seed_batch_profiles

        # Validate and summarize
        validate_seed_data
        print_summary
        Seeds::Support::Timing.print_summary

        ctx
      end

      private

      def run_step(step_name)
        return if skip_step?(step_name)

        Seeds::Support::Timing.track_step(step_name) do
          send(step_name)
        end
      end

      def skip_step?(step_name)
        env_var = OPTIONAL_STEPS[step_name]
        return false unless env_var

        if env_var.start_with?("SKIP_")
          ENV[env_var] == "true"
        else
          ENV[env_var] != "true"
        end
      end
    end
  end
end
```

### 4.3 Benefits of Modular Architecture

| Aspect | Before | After |
|--------|--------|-------|
| **File size** | 3,610 lines | ~80 lines avg |
| **Git conflicts** | Constant | Rare |
| **IDE navigation** | Painful | Instant |
| **Step isolation** | Impossible | Easy |
| **Testing** | Untestable | Per-step specs |
| **Onboarding** | Days | Hours |

---

## 5. Feature 2: Context Object for State Management

### 5.1 The Problem: Instance Variable Chaos

```ruby
# Before: 95 instance variable references across 37 steps
def seed_admin_users
  @admin_user = User.create!(...)
end

def seed_job_posts
  job = JobPost.create!(company: @company)  # Where is @company set?
end
```

**Issues:**
- No IDE autocomplete
- No documentation of what's available
- No validation that required data exists
- Testing requires complex setup

### 5.2 The Solution: Explicit Context Object

```ruby
# db/seeds/context.rb
module Seeds
  module Support
    class Context
      # Core entities
      attr_accessor :company
      attr_accessor :admin_user, :standard_user
      attr_accessor :candidate_demo_user, :access_request_user
      attr_accessor :admin_profile, :full_data_candidate_users
      attr_accessor :demo_job_posts

      # Client roles
      attr_accessor :client_user, :client_owner, :client_manager

      # Batch processing
      attr_accessor :batch_profile_result

      def initialize
        @full_data_candidate_users = []
        @demo_job_posts = []
      end

      # Convenience methods
      def company?
        !@company.nil?
      end

      def batch_profiles?
        @batch_profile_result&.success? == true
      end

      def batch_profile_count
        @batch_profile_result&.profiles_created || 0
      end

      # Dependency validation
      def require!(*attrs)
        missing = attrs.select { |attr| send(attr).nil? }
        raise "Missing required context: #{missing.join(', ')}" if missing.any?
      end

      # Debugging helper
      def summary
        {
          company: @company&.name,
          admin_user: @admin_user&.email,
          full_data_candidates: @full_data_candidate_users.size,
          batch_profiles: batch_profile_count
        }
      end
    end
  end
end
```

### 5.3 Usage in Steps

```ruby
# Access via ctx helper
def seed_job_posts
  ctx.require!(:company, :admin_user)  # Fail fast if deps missing

  job = JobPost.create!(
    company: ctx.company,
    user: ctx.admin_user,
    title: "Senior Engineer"
  )
  ctx.demo_job_posts << job
end
```

### 5.4 Why Context Object Matters

| Aspect | Instance Variables | Context Object |
|--------|-------------------|----------------|
| **Discovery** | `grep @` across files | `ctx.` autocomplete |
| **Documentation** | None | `attr_accessor` list |
| **Validation** | Runtime errors | `ctx.require!` |
| **Testing** | Mock everything | Inject test context |
| **Debugging** | puts everywhere | `ctx.summary` |

---

## 6. Feature 3: Conditional Execution via ENV Flags

### 6.1 Use Cases

| Use Case | ENV Flag | Behavior |
|----------|----------|----------|
| Skip slow reports | `SKIP_SEED_REPORTS=true` | Reports step skipped |
| Create 40 full candidates | `SEED_FULL_CANDIDATES=true` | Rich candidate data |
| Create 100k profiles | `CREATE_BATCH_PROFILES=true` | Batch processing enabled |

### 6.2 Implementation

```ruby
# db/seeds/steps.rb
OPTIONAL_STEPS = {
  # Skip steps (default: run)
  seed_reports: "SKIP_SEED_REPORTS",

  # Enable steps (default: skip)
  seed_full_data_candidates: "SEED_FULL_CANDIDATES",
  seed_full_data_candidates_job_board: "SEED_FULL_CANDIDATES",
  seed_batch_profiles: "CREATE_BATCH_PROFILES"
}.freeze

def skip_step?(step_name)
  env_var = OPTIONAL_STEPS[step_name]
  return false unless env_var

  if env_var.start_with?("SKIP_")
    ENV[env_var] == "true"  # Skip if true
  else
    ENV[env_var] != "true"  # Skip unless true
  end
end
```

### 6.3 Usage Examples

```bash
# Standard development seed (fast)
rails db:seed

# Full candidates for feature testing
SEED_FULL_CANDIDATES=true rails db:seed

# 100k profiles for QA stress testing
CREATE_BATCH_PROFILES=true rails db:seed

# Skip reports for faster iteration
SKIP_SEED_REPORTS=true rails db:seed

# Combined flags
SEED_FULL_CANDIDATES=true CREATE_BATCH_PROFILES=true rails db:seed
```

### 6.4 Benefits

| Scenario | Without Flags | With Flags |
|----------|--------------|------------|
| Daily development | ~5 min (full seed) | ~30 sec (minimal) |
| Feature testing | Edit code | Set ENV var |
| QA stress test | Impossible | One command |
| CI pipeline | Full seed always | Skip reports |

---

## 7. Feature 4: Progress Reporting with Timing

### 7.1 The Problem: Silent Seeds

```bash
$ rails db:seed
# ... silence for 30 seconds ...
# ... more silence ...
# Is it working? Is it stuck?
```

### 7.2 The Solution: Real-Time Progress

```ruby
# db/seeds/timing.rb
module Seeds
  module Support
    module Timing
      class << self
        def start_run(total_steps)
          @total_steps = total_steps
          @current_step = 0
          @step_timings = {}
          @run_started_at = Time.current
        end

        def track_step(step_name)
          @current_step += 1
          started = Time.current

          print_progress(step_name) unless quiet?

          yield

          duration = Time.current - started
          @step_timings[step_name] = duration
        end

        def print_progress(step_name)
          puts format(
            "[%2d/%2d] %-40s",
            @current_step, @total_steps,
            step_name.to_s.gsub(/^seed_/, "").humanize
          )
        end

        def print_summary
          puts "\n#{'=' * 60}"
          puts "SEED TIMING SUMMARY"
          puts "=" * 60

          @step_timings.sort_by { |_, v| -v }.first(10).each do |step, duration|
            puts format("  %-40s %6.2fs", step, duration)
          end

          puts "-" * 60
          puts format("  %-40s %6.2fs", "TOTAL", total_duration)
          puts "=" * 60
        end
      end
    end
  end
end
```

### 7.3 Output Example

```
[ 1/37] Predefined avatar assets              
[ 2/37] Company                               
[ 3/37] Job titles                            
[ 4/37] Admin users                           
...
[35/37] Summary                               
[36/37] Demo recommendation                   

============================================================
SEED TIMING SUMMARY
============================================================
  seed_full_data_candidates                     12.34s
  seed_random_profiles                           8.21s
  seed_homepage_profiles                         4.56s
  seed_job_posts                                 3.12s
  ...
------------------------------------------------------------
  TOTAL                                         45.67s
============================================================
```

### 7.4 Benefits

| Aspect | Silent Seeds | Progress + Timing |
|--------|-------------|-------------------|
| **Feedback** | None | Real-time progress |
| **Debugging** | Which step failed? | Clear step names |
| **Optimization** | Guess which is slow | Timing breakdown |
| **CI logs** | Useless | Actionable |

---

## 8. Feature 5: Post-Seed Data Validation

### 8.1 The Problem: Silent Failures

```ruby
# Seeds "complete" but data is broken
def seed_admin_users
  @admin_user = User.find_or_initialize_by(email: 'admin@bluegeko.com')
  @admin_user.save  # No bang! Silent failure
end

# Later, in production demo...
# "Why is there no admin user?!"
```

### 8.2 The Solution: Validation Module

```ruby
# db/seeds/validation.rb
module Seeds
  module Support
    module Validation
      CHECKS = {
        # Integrity checks (errors)
        orphaned_profiles: -> { Profile.left_joins(:user).where(users: { id: nil }) },
        candidates_without_profiles: -> { User.candidate.left_joins(:profile).where(profiles: { id: nil }) },
        orphaned_job_posts: -> { JobPost.left_joins(:company).where(companies: { id: nil }) },

        # Minimum data checks (errors)
        minimum_users: -> { User.count >= 5 },
        minimum_profiles: -> { Profile.count >= 3 },
        minimum_companies: -> { Company.count >= 1 },
        minimum_job_posts: -> { JobPost.count >= 5 },

        # Quality checks (warnings)
        profiles_with_skills: -> { Profile.joins(:skills).distinct.count > 0 },
        profiles_with_work_experience: -> { Profile.joins(:work_experiences).distinct.count > 0 },
        users_with_login_methods: -> { User.joins(:login_methods).distinct.count > 0 }
      }.freeze

      class << self
        def run
          return skip_result if skip?

          result = ValidationResult.new
          run_integrity_checks(result)
          run_minimum_checks(result)
          run_quality_checks(result) unless strict?

          print_results(result)
          result
        end

        private

        def run_integrity_checks(result)
          %i[orphaned_profiles candidates_without_profiles orphaned_job_posts].each do |check|
            count = CHECKS[check].call.count
            if count > 0
              result.add_error(check, "Found #{count} #{check.to_s.humanize.downcase}")
            else
              result.add_passed(check)
            end
          end
        end
      end
    end
  end
end
```

### 8.3 Validation Output

```
============================================================
POST-SEED VALIDATION
============================================================
Integrity Checks:
  ✓ No orphaned profiles
  ✓ No candidates without profiles
  ✓ No orphaned job posts

Minimum Data Checks:
  ✓ Users: 47 (minimum: 5)
  ✓ Profiles: 42 (minimum: 3)
  ✓ Companies: 5 (minimum: 1)
  ✓ Job Posts: 25 (minimum: 5)

Quality Checks:
  ✓ Profiles with skills: 38
  ✓ Profiles with work experience: 35
  ⚠ Users with login methods: 0 (warning)

------------------------------------------------------------
Result: PASSED (14 checks, 1 warning)
============================================================
```

### 8.4 ENV Controls

```bash
# Skip validation (CI speed)
SKIP_SEED_VALIDATION=true rails db:seed

# Strict mode (fail on warnings)
SEED_VALIDATION_STRICT=true rails db:seed
```

---

## 9. Feature 6: 100k+ Full Profile Scaling

### 9.1 The Challenge

Our AI team needed 100,000 realistic candidate profiles for model training. QA needed the same for stress testing. Creating records one-by-one would take hours.

**Requirements:**
- Full profiles with ALL associations
- Category-appropriate job titles
- Skills, work experiences, education
- Portfolio, contact info, avatars
- Realistic data distributions
- Conditional execution (don't run in daily dev)

### 9.2 What Gets Created

Each batch profile is a **complete candidate** with:

| Association | Per Profile | Total (100k) |
|-------------|-------------|--------------|
| User + Login Security | 1 | 100,000 |
| Profile | 1 | 100,000 |
| Skills | 3-6 | ~450,000 |
| Work Experiences | 2-4 | ~300,000 |
| Education Items | 1-2 | ~150,000 |
| Languages | 1-3 | ~200,000 |
| Contact Infos | 2-4 | ~300,000 |
| Portfolio + Links | 3-9 | ~600,000 |
| Location Setting | 1 | 100,000 |
| Salary Expectation | 1 | 100,000 |
| Avatar Session + Images | 4-5 | ~450,000 |
| **Total Records** | ~20-30 | **~2,500,000+** |

### 9.3 Category-Specific Data

```ruby
CATEGORY_OCCUPATIONS = {
  "technology" => [
    "Software Engineer", "Senior Software Engineer", "Staff Software Engineer",
    "DevOps Engineer", "Data Scientist", "Machine Learning Engineer",
    "Mobile Developer", "Cloud Architect", "Security Engineer"
  ],
  "design" => [
    "UX Designer", "Product Designer", "Creative Director",
    "Interaction Designer", "Design Systems Lead"
  ],
  "business" => [
    "Project Manager", "Product Manager", "Business Analyst",
    "Strategy Consultant", "Operations Manager"
  ],
  # ... 9 categories total
}.freeze

CATEGORY_SKILLS = {
  "technology" => %w[Ruby Python JavaScript TypeScript Docker Kubernetes AWS],
  "design" => %w[Figma Sketch Photoshop Wireframing UserResearch],
  "business" => %w[Excel Salesforce Tableau Leadership Strategy],
  # ...
}.freeze
```

### 9.4 Implementation Highlights

```ruby
# db/seeds/batch_profiles.rb
module Seeds
  module Support
    module BatchProfiles
      DEFAULT_COUNT = 100_000
      CHUNK_SIZE = 500

      def run(count: target_count, on_progress: nil)
        result = BatchResult.new(target_count: count)

        count.times.each_slice(chunk_size) do |indices|
          chunk_result = process_chunk(indices)
          result.record_chunk(chunk_result)
          on_progress&.call(result)
        end

        result.finish!
        result
      end

      private

      def process_chunk(indices)
        indices.each do |index|
          # Select random category
          category = categories.sample

          # Create user (ActiveRecord for Devise)
          user = create_batch_user(index: index)

          # Create profile with category-appropriate job title
          profile = create_batch_profile(user: user, category: category)

          # Create ALL associations
          create_skills(profile, category.slug)
          create_work_experiences(profile, category.slug)
          create_education_items(profile)
          create_languages(profile)
          create_contact_infos(profile)
          create_portfolio(profile)
          create_location_setting(profile)
          create_salary_expectation(profile)
          create_avatar_data(profile)
        end
      end
    end
  end
end
```

### 9.5 Usage

```bash
# Create 100,000 full profiles (default)
CREATE_BATCH_PROFILES=true rails db:seed

# Create 10,000 for smaller tests
CREATE_BATCH_PROFILES=true BATCH_PROFILE_COUNT=10000 rails db:seed

# With verbose progress
CREATE_BATCH_PROFILES=true BATCH_VERBOSE=true rails db:seed
```

### 9.6 Output

```
======================================================================
[BATCH] Starting FULL candidate profile creation
======================================================================
  Target count:     100,000
  Chunk size:       500
  Associations:     Skills, Work Exp, Education, Languages, Contacts, etc.
======================================================================

  [=======>--------------------]  25.0% | Chunk 50/200 | 25000 profiles | 625,000 assoc

======================================================================
[BATCH] Full candidate profile creation complete!
======================================================================
  Users created:        100,000
  Profiles created:     100,000
  Associations created: 2,543,721
  Total duration:       3h 12m
  Rate:                 8.7 profiles/second
======================================================================
```

### 9.7 Performance Characteristics

| Count | Time | Records Created |
|-------|------|-----------------|
| 1,000 | ~2-3 min | ~25,000 |
| 10,000 | ~20-30 min | ~250,000 |
| 100,000 | ~3-5 hours | ~2,500,000 |

---

## 10. Benefits and Use Cases

### 10.1 Use Case Matrix

| Stakeholder | Command | Result |
|-------------|---------|--------|
| **Daily Dev** | `rails db:seed` | ~30s, minimal data |
| **Feature Testing** | `SEED_FULL_CANDIDATES=true rails db:seed` | ~2 min, 40 rich profiles |
| **QA Stress Test** | `CREATE_BATCH_PROFILES=true rails db:seed` | ~3h, 100k profiles |
| **AI Training** | `CREATE_BATCH_PROFILES=true BATCH_PROFILE_COUNT=500000 rails db:seed` | ~15h, 500k profiles |
| **CEO Demo** | `rails db:seed` | Production-like feel |
| **New Engineer** | `rails db:seed` | Working environment in 30s |

### 10.2 Before vs After Comparison

| Aspect | Before | After |
|--------|--------|-------|
| **File organization** | 1 file, 3,610 lines | 37 files, ~80 lines each |
| **Test coverage** | 0% | 400+ specs |
| **Documentation** | None | 1,797-line README |
| **Progress feedback** | Silent | Real-time with timing |
| **Data validation** | None | 14 automated checks |
| **Scalability** | ~100 profiles | 100,000+ profiles |
| **Conditional execution** | Edit code | ENV flags |
| **Onboarding time** | Days | Hours |
| **Git conflicts** | Daily | Rare |

### 10.3 ROI

**Time saved per week:**
- 5 engineers × 10 min/day waiting for seeds = 4+ hours
- 2 QA engineers × 1 hour/week debugging broken seeds = 2 hours
- 1 demo preparation × 2 hours = 2 hours

**Total: ~8 hours/week = 1 FTE day**

---

## 11. Testing the Seed System

### 11.1 Test Structure

```
spec/seeds/
├── support/
│   ├── helpers_spec.rb           # Unit tests for helpers
│   ├── context_spec.rb           # Context object tests
│   ├── timing_spec.rb            # Timing module tests
│   ├── validation_spec.rb        # Validation tests
│   └── batch_profiles_spec.rb    # Batch processing tests
├── reference_data_spec.rb        # Reference data tests
├── integration_spec.rb           # Full seed run tests
└── steps/
    ├── shared_examples.rb        # Reusable step examples
    ├── company_spec.rb           # Step-specific tests
    └── ...
```

### 11.2 Shared Examples for Steps

```ruby
# spec/seeds/steps/shared_examples.rb
RSpec.shared_examples "a seed step that creates records" do |model_class, expected_count:|
  it "creates #{expected_count} #{model_class.name.pluralize}" do
    expect { run_step }.to change(model_class, :count).by(expected_count)
  end
end

RSpec.shared_examples "a seed step that is idempotent" do
  it "does not create duplicates on second run" do
    run_step
    expect { run_step }.not_to change(described_model, :count)
  end
end
```

### 11.3 Test Coverage

| Component | Specs | Coverage |
|-----------|-------|----------|
| Helpers | 45 | 100% |
| Context | 32 | 100% |
| Timing | 28 | 100% |
| Validation | 31 | 100% |
| Batch Profiles | 49 | 100% |
| Reference Data | 89 | 100% |
| Individual Steps | 126 | Key paths |
| **Total** | **400+** | High |

---

## 12. Three Bonus Ideas Worth Implementing

### 12.1 Idea 1: Seed Data Snapshots

**Problem:** Recreating 100k profiles takes 3 hours every time.

**Solution:** Database snapshots for instant restore.

```ruby
# Potential implementation
module Seeds
  module Snapshots
    def save(name)
      `pg_dump wigiwork_development > snapshots/#{name}.sql`
    end

    def restore(name)
      `psql wigiwork_development < snapshots/#{name}.sql`
    end
  end
end

# Usage
# After 3-hour batch: SEED_SNAPSHOT=save rails db:seed
# Next time: SEED_SNAPSHOT=restore:batch_100k rails db:seed (~30 sec)
```

**Benefit:** 3 hours → 30 seconds for QA environments.

### 12.2 Idea 2: Faker Seed Consistency

**Problem:** Random data changes every seed run, breaking visual regression tests.

**Solution:** Seed Faker's random generator.

```ruby
# db/seeds/support.rb
def with_consistent_faker
  original_seed = Faker::Config.random
  Faker::Config.random = Random.new(42)
  yield
ensure
  Faker::Config.random = original_seed
end

# Usage
with_consistent_faker do
  seed_profiles  # Same names, emails, etc. every time
end
```

**Benefit:** Consistent screenshots for visual regression testing.

### 12.3 Idea 3: Seed Data Metrics Dashboard

**Problem:** No visibility into what's seeded without running queries.

**Solution:** Post-seed metrics report.

```ruby
# db/seeds/metrics.rb
module Seeds
  module Metrics
    def report
      {
        users: {
          total: User.count,
          by_role: User.group(:role).count,
          with_profiles: User.joins(:profile).count
        },
        profiles: {
          total: Profile.count,
          with_skills: Profile.joins(:skills).distinct.count,
          avg_skills: Profile.joins(:skills).group(:id).count.values.sum.to_f / Profile.count,
          by_category: Profile.joins(:category).group("categories.slug").count
        },
        companies: {
          total: Company.count,
          with_jobs: Company.joins(:job_posts).distinct.count
        }
      }
    end
  end
end
```

**Output:**

```yaml
Users:
  total: 100,047
  by_role: { admin: 2, candidate: 100,040, client: 5 }
  with_profiles: 100,042

Profiles:
  total: 100,042
  with_skills: 99,800
  avg_skills: 4.2
  by_category: { technology: 45,000, design: 15,000, ... }

Companies:
  total: 5
  with_jobs: 3
```

**Benefit:** Instant insight into seed data quality and distribution.

---

## 13. Conclusion

### 13.1 What We Achieved

| Metric | Before | After |
|--------|--------|-------|
| Lines in main file | 3,610 | 217 |
| Number of files | 1 | 37 |
| Test coverage | 0% | 400+ specs |
| Documentation | 0 lines | 1,797 lines |
| Max profiles | ~100 | 100,000+ |
| Progress feedback | None | Real-time |
| Data validation | None | 14 checks |
| Conditional execution | None | 5 ENV flags |

### 13.2 Key Takeaways

1. **Modular beats monolithic** — Split large files into focused modules
2. **Explicit state beats implicit** — Context objects over instance variables
3. **Conditional execution is essential** — ENV flags for different scenarios
4. **Visibility prevents pain** — Progress reporting and timing
5. **Validation catches bugs** — Automated checks before they reach demos
6. **Scale when needed** — Batch processing for volume requirements
7. **Document everything** — Future you (and new engineers) will thank you

### 13.3 The Real Win

The technical improvements are measurable, but the real win is **confidence**:

- Confident that seeds work (validation)
- Confident about progress (timing)
- Confident in isolation (modular files)
- Confident at scale (batch processing)
- Confident for demos (realistic data)
- Confident for new engineers (documentation)

**Invest in your seed system. It's the foundation everything else is built on.**

---

## Resources

- **Rails Guides on Seeds**: [guides.rubyonrails.org/active_record_migrations.html#migrations-and-seed-data](https://guides.rubyonrails.org/active_record_migrations.html#migrations-and-seed-data)
- **Faker Gem**: [github.com/faker-ruby/faker](https://github.com/faker-ruby/faker)
- **FactoryBot**: [github.com/thoughtbot/factory_bot](https://github.com/thoughtbot/factory_bot)
- **Database Cleaner**: [github.com/DatabaseCleaner/database_cleaner](https://github.com/DatabaseCleaner/database_cleaner)
- **Our Seed System Documentation**: See `db/seeds/README.md` in your codebase

---

*This post documents the transformation of the Wigiwork seed system from a 3,600-line monolith to an enterprise-grade data generation platform. The patterns described here—modular architecture, context objects, conditional execution, progress tracking, validation, and batch processing—are applicable to any Rails application that has outgrown simple seeds.*
