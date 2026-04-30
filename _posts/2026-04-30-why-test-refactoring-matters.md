---
layout: post
title: "Why Test Refactoring Matters: Turning 12-Minute Builds Into a 39-Second Proof Loop"
date: 2026-04-30
author: Max Lukin
tags: [rails, rspec, ci, testprof, profiling, technical-debt, productivity, verification]
categories: [engineering, rails, best-practices, testing, ci]
description: "A metric-based look at why profiling and refactoring Rails tests matters when you ship around 10 PRs a day, each with multiple commits, and every slow build compounds into hours of lost engineering time."
---

> _"Slow tests do not only slow CI. They change how often you are willing to prove that the system still works."_

## TL;DR

| Metric | Before | Current | Change |
| --- | ---: | ---: | ---: |
| Old build/proof loop used for planning math | **~12 min** | **39.42s local fast verification** | **~18.3x faster** |
| Initial broad profiled RSpec runtime | **4m 8.6s** | **2m 43.1s split profiled runtime** | **~34% faster** |
| SQL events | **571,641** | **413,055** | **-158,586 / ~28% fewer** |
| Factory calls | **36,133** | **31,935** | **-4,198 / ~12% fewer** |
| Fast verification proof | n/a | **8,659 examples / 0 failures / 28 pending** | green |
| Parallel RSpec phase | n/a | **32.35s** | green |
| Full `bin/verify` local loop | n/a | **39.42s** | green |
| Processed executable test files | n/a | **~72 / 714** | **~10.1%** |
| Current heavy-tail status | n/a | **39 tests still use broad local reference context** | next target |

The important part is not that 10% of files were touched.

The important part is that the **right 10%** was touched first.

That 10.1% of executable test files produced:

- ~34% less profiled runtime
- ~28% fewer SQL events
- a fast local proof loop around 39 seconds
- no API behavior changes
- no removed assertions
- no reduction in request/integration confidence

If you are shipping around **10 PRs per day**, and each PR gets about **3 commits**, that is roughly:

```text
10 PR/day * 3 commits = 30 proof loops/day
```

With a 12-minute build:

```text
30 * 12 min = 360 min/day = 6 hours/day waiting on proof
```

With the current 39.42-second local proof loop:

```text
30 * 39.42s = 1,182.6s = 19.7 min/day
```

So the saved time is:

```text
360 min - 19.7 min = 340.3 min/day
```

That is **5 hours 40 minutes per day** back.

Or, if you reinvest only the saved waiting time into additional current-speed proof loops:

```text
340.3 min / 0.657 min = ~518 extra proof loops/day
```

That does not mean you should make 518 more commits per day.

It means the old loop made verification expensive enough that you would naturally batch risk. The new loop makes verification cheap enough that you can commit smaller, check more often, and keep moving without gambling.

---

## The cost of not refactoring

The easiest way to undervalue test performance is to look at one build.

One 12-minute build is annoying.

Thirty 12-minute proof loops per day is a workflow tax.

| Cadence | Old 12-minute loop | Current 39.42-second loop | Time recovered |
| --- | ---: | ---: | ---: |
| 1 proof loop | 12 min | 39.42 sec | 11m 20s |
| 30 proof loops/day | 6h/day | 19.7m/day | 5h 40m/day |
| 150 proof loops/week | 30h/week | 1h 38m/week | 28h 22m/week |
| 600 proof loops/month | 120h/month | 6h 34m/month | 113h 26m/month |

This is why slow tests are not only a developer-experience issue.

They change engineering behavior:

- you commit less often
- you batch more risk
- you delay verification
- you wait longer to discover drift
- you become tempted to skip checks

Fast tests do not guarantee quality.

But slow tests make quality expensive enough that people naturally start negotiating with it.

---

## The honest caveat

There are two "current time" numbers worth separating:

| Current number | What it means |
| --- | --- |
| **39.42s** | Local `bin/verify` fast loop: RuboCop, parallel RSpec, RSwag generation. This is the day-to-day proof loop. |
| **2m 43.1s** | Instrumented TestProf split profile. This pays profiling overhead and is used for diagnosis, not every commit. |

The old **~12 min** number is the build-time pain point. The new **39.42s** is the observed local fast verification loop after parallelization and test cleanup. CI still has container, bundle, database, and service overhead, so I do not treat local time as a perfect CI replacement.

But the engineering lesson is still valid:

> The closer the proof loop gets to seconds instead of minutes, the more often you can afford to prove correctness.

---

## Why this refactor happened

The trigger was simple: CI started hitting build-time limits.

The request/integration step was the visible pain:

```sh
bundle exec rspec spec/integration spec/requests --tag ~full_only --fail-fast --format progress
```

At first, the temptation is obvious:

- increase CI timeout
- split one huge file
- skip slow tests
- move on

We did increase the Bitbucket `max-time` guard to 12 minutes, but that was not the fix. That was only a safety margin.

The actual fix was to profile the suite and stop guessing.

The first broad profile showed the shape of the problem:

| Run | Examples | Runtime | SQL events | SQL time | Factories |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial broad `spec/` profile | 8,659 | 4m 8.6s | 571,641 | 1m 57.4s | 36,133 |

Almost half the profiled runtime was SQL.

That matters because SQL-heavy tests are rarely fixed by staring at one assertion. The cost usually lives in setup:

- `create(:user)` cascades
- profile auto-creation
- company/reference catalogs
- callbacks
- chat/message graphs
- access-request state machines
- serializer renders that pull large association trees

So the question changed from:

> Which test is slow?

to:

> Which setup is repeated, realistic, and unnecessary for the behavior under test?

That is a better question.

---

## The operating rule: faster, not weaker

The rule for the session was strict:

> Optimize tests without losing confidence.

That meant no cheap wins like deleting assertions or converting request tests into shallow unit tests just to make the graph look better.

The safety rules were:

| Rule | How it was applied |
| --- | --- |
| Keep request/integration confidence | Request tests still hit real endpoints, auth, serializers, callbacks, and DB writes. |
| Keep mutation behavior real | Command, callback, uniqueness, destroy, chat/message, access-request, and job-state examples keep persisted rows. |
| Use `build_stubbed` only for read-only checks | Policy predicates, logger metadata, and serializer-only cases can be stubbed when the DB is not the behavior. |
| Use `let_it_be` only for stable records | Shared users, companies, jobs, and profiles are read-only parents; rows mutated by examples stay local. |
| Decouple app tests from seed runtime | App tests use explicit factory-backed local reference data, not `lib/tasks/seeds/**`. |
| Do not remove assertions for speed | The target is setup shape, not coverage reduction. |

This distinction matters.

Bad test optimization asks:

> How do we make the suite green faster?

Good test optimization asks:

> Which expensive work is unrelated to the behavior this example proves?

---

## What we did not do

This part matters because "test optimization" often sounds like a polite way to say "less coverage."

That was not the deal.

| Shortcut | Why we did not take it |
| --- | --- |
| Delete slow tests | Deleted tests make dashboards faster and confidence lower. That is not optimization. |
| Mock request/integration behavior | Request tests are expensive because they prove routing, auth, controller envelopes, policies, serializers, callbacks, and DB behavior together. |
| Replace mutation tests with read-only doubles | Commands, callbacks, uniqueness, destroy behavior, chat/messages, access requests, credits, and job state need persisted rows. |
| Hide seed problems by deleting seed tests | Seed runtime tests remain in the repo. They are skipped in the default suite and can be run when seed work is active. |
| Change API code to satisfy faster tests | This was test-only work. API behavior, JSON shape, authorization, and persistence rules stayed unchanged. |
| Split huge files just to make charts look better | Splitting can help ownership, but it does not remove SQL or factory cost by itself. Setup shape was the real target. |

The strongest signal from the session was this:

> We got faster by removing unrelated setup, not by reducing the behavioral contract.

---

## What changed

### 1. Added profiling as a real workflow

We made TestProf the profiling path and used:

```sh
env FPROF=1 EVENT_PROF=sql.active_record EVENT_PROF_EXAMPLES=1 EVENT_PROF_TOP=40 \
  bundle exec rspec spec/integration spec/requests --tag '~full_only' --format progress
```

and:

```sh
env FPROF=1 EVENT_PROF=sql.active_record EVENT_PROF_EXAMPLES=1 EVENT_PROF_TOP=40 \
  bundle exec rspec spec/bin spec/blueprints spec/channels spec/config spec/controllers spec/db \
  spec/forms spec/initializers spec/jobs spec/lib spec/mailers spec/middleware spec/models \
  spec/policies spec/queries spec/routing spec/services spec/smoke spec/tasks spec/validators \
  --tag '~full_only' --format progress
```

That gave two useful views:

- `EventProf` showed SQL cost by file and example
- `FactoryProf` showed factory cascades and top-level setup cost

Once the suite had numbers, the refactor stopped being emotional.

### 2. Split CI by work type

The Bitbucket flow now separates:

- lint/security
- unit/model/blueprint/policy/service/job/query/form/lib tests
- request/integration tests
- Swagger generation
- `full_only` tests

Request/integration and non-request tests can run in parallel workers.

The result is not just shorter wall time. It also makes slow areas easier to reason about. A slow request test and a slow model test are usually slow for different reasons.

### 3. Removed seed runtime from app tests

This was a key cleanup.

The app tests used to lean on seeded reference data. That made them realistic, but it also tied normal verification to seed runtime behavior and large catalogs.

We replaced that with explicit factory-backed local reference data:

- company types
- company industries
- company sizes
- profile taxonomy
- job post categories
- platforms
- contact types
- education levels
- business ID validation rules

Seed tests still exist. They are not deleted. They are skipped in the default suite and can be run locally when working on seeds.

This made the boundary cleaner:

| Area | Responsibility |
| --- | --- |
| App tests | Verify app behavior with explicit local reference rows. |
| Seed tests | Verify seed runtime when seed work is being changed. |

### 4. Started splitting broad local reference data

After moving away from seed runtime, a new cost appeared: the replacement local reference context was intentionally broad.

That was the right first move for reliability, but it became the next optimization target.

The broad context created:

- company options
- profile taxonomy
- platforms
- contact types
- education levels
- profile link titles
- business ID validation rows

Some tests only needed one slice.

So the first split introduced narrower contexts:

- `with local company reference data`
- `with local company types`
- `with local company industries`
- `with local company sizes`
- `with local business id validation rules`
- `with local education levels`
- `with local contact types`

Then seven tests moved off the broad context:

- `spec/services/companies/business_id_validator_spec.rb`
- `spec/models/business_id_validation_setting_spec.rb`
- `spec/models/company_size_spec.rb`
- `spec/models/company_type_spec.rb`
- `spec/models/company_industry_spec.rb`
- `spec/requests/api/v1/contact_types_spec.rb`
- `spec/requests/api/v1/public/vocabulary/education_levels_spec.rb`

Focused result:

| Batch | Examples | Runtime | SQL events | Factories | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Narrow reference-context batch | 106 | 0.92s | 1,558 | 160 | 0 failures |

### 5. Optimized the heaviest files first

This is where the 10% number becomes important.

We did not process 10% of files randomly.

We processed roughly **72 of 714 executable test files**, or **~10.1%**, sorted by profiling impact.

That included:

- request workflow tests
- policy tests
- blueprint tests
- model tests
- service tests
- seed/reference support boundaries

Examples of file-level wins:

| Test file | Before | After | Main change |
| --- | ---: | ---: | --- |
| `spec/policies/work_experience_policy_spec.rb` | ~1,320 SQL | 74 SQL | Role/company policy matrix moved to `build_stubbed`; scope records stayed persisted. |
| `spec/policies/profile_policy_spec.rb` | ~1,358 SQL | 83 SQL | Policy predicates moved to stubbed users/profiles; scope stayed persisted. |
| `spec/blueprints/messages/location_setting_blueprint_spec.rb` | ~1,207 SQL | 10 SQL | Serializer-only behavior stopped creating a full persisted profile graph. |
| `spec/blueprints/profile_note_blueprint_spec.rb` | ~742 SQL | 0 SQL | Plain object replaced DB-backed setup for serializer-only behavior. |
| `spec/services/visibility/visibility_flags_spec.rb` | ~1,702 SQL | 219 SQL | Read examples use stubbed/assigned profile; update behavior stayed persisted. |
| `spec/models/company_size_spec.rb` | 1,545 SQL | 153 SQL | Narrow company-size reference context. |
| `spec/models/company_type_spec.rb` | 1,560 SQL | 256 SQL | Narrow company-type reference context. |
| `spec/models/company_industry_spec.rb` | 1,628 SQL | 687 SQL | Company type + industry rows only. |
| `spec/requests/api/v1/users/profiles/request_access_spec.rb` | 5,659 SQL | 1,847 SQL | Stable actors shared; access, credits, chats, and jobs stayed real. |

This is why profiler order matters.

If the current 10.1% of files produced a 34% runtime reduction, the naive math says:

```text
34% / 10.1% = 3.37x impact per file-percent
```

If that scaled linearly to 100%, it would imply:

```text
3.37 * 100% = 337% runtime reduction
```

That is impossible.

And that impossibility is the point.

The first 10% was not normal. It was the expensive slice. Profiling let us find the part of the suite where small, careful changes had disproportionate return.

The realistic lesson is:

> Do not optimize all tests equally. Optimize the tests that are paying rent in every build.

---

## The time math at shipping cadence

Assume this daily cadence:

```text
10 PRs/day
3 commits/PR
30 proof loops/day
```

### Old loop: 12 minutes

```text
30 * 12 min = 360 min/day
```

That is:

- 6 hours/day
- 30 hours/week
- 120 hours/month

That is not a test suite.

That is a part-time job waiting for CI.

### Current fast loop: 39.42 seconds

```text
39.42s = 0.657 min
30 * 0.657 min = 19.7 min/day
```

That is:

- 19.7 minutes/day
- 1 hour 38 minutes/week
- 6 hours 34 minutes/month

### Time recovered

```text
360 min/day - 19.7 min/day = 340.3 min/day
```

That is:

- 5 hours 40 minutes/day
- 28 hours 22 minutes/week
- 113 hours/month

If you spend that recovered time only on additional current-speed proof loops:

```text
340.3 min/day / 0.657 min = ~518 extra proof loops/day
```

Again, this is not a recommendation to make hundreds of commits.

It is a way to feel the magnitude.

A slow build taxes every commit. A fast proof loop makes small commits cheap.

### Conservative profiler-time version

If we use the slower instrumented profile number instead:

```text
2m 43.1s = 2.718 min
30 * 2.718 min = 81.5 min/day
360 - 81.5 = 278.5 min/day saved
```

Even with the conservative number, the suite gives back:

- 4 hours 38 minutes/day
- 23 hours 12 minutes/week

That is still huge.

---

## Why this matters more with AI-assisted development

With AI, generating a patch is no longer the bottleneck.

The bottleneck becomes:

- proving the patch
- reviewing the patch
- finding subtle drift
- avoiding slow feedback loops
- keeping confidence high while throughput rises

If you can create 10 PRs a day, but each proof loop costs 12 minutes, the system pushes you toward bad habits:

- bigger commits
- fewer local checks
- more batching
- delayed feedback
- risk discovered late
- more review anxiety

That is how technical debt quietly taxes AI productivity.

AI can generate code quickly, but CI decides how quickly you can trust it.

This is why test refactoring belongs in the same conversation as AI productivity. It is not janitorial work. It is throughput infrastructure.

---

## What stayed reliable

The most important result is not speed. It is speed without weakening the test suite.

The current proof still runs:

| Check | Current result |
| --- | --- |
| RuboCop | clean |
| Parallel RSpec | 8,659 examples, 0 failures, 28 pending |
| RSwag Swaggerize | generated successfully |
| Contract audit | 6/6 checks passed |

And the behavioral boundaries stayed intact:

- request tests still exercise real routes
- authentication is still real
- serializers are still rendered
- DB-backed mutation behavior stays DB-backed
- authorization scopes remain persisted where scope behavior is under test
- seed tests remain in the repository
- app tests no longer accidentally depend on seed runtime

This is the difference between optimization and coverage erosion.

---

## What is still left

This is not done.

The remaining heaviest chunk is still visible:

1. continue splitting broad `with local reference data`
2. `spec/requests/llm_gateway/sessions_spec.rb`
3. `spec/requests/api/v1/profiles/profile_cards_spec.rb`
4. `spec/requests/api/v1/companies/profile/public_jobs_spec.rb`
5. `spec/requests/api/v1/companies/team_management_spec.rb`
6. `spec/requests/api/v1/users/conversation_messages_spec.rb`
7. broad `spec/requests/api/v1/profiles_spec.rb`

There are still 39 tests using the broad local reference context.

There are still request tests with 4,000-6,700 SQL events each.

There are still workflow tests where the cost is real and should not be mocked away.

That is fine.

The goal is not to make every test microscopic.

The goal is to make expensive tests expensive for a reason.

---

## How to start tomorrow

If I had to start this again in another Rails API, I would not begin by editing tests.

I would begin with a short checklist:

| Step | Command or action | Why |
| --- | --- | --- |
| 1 | Install or enable TestProf | You need numbers before opinions. |
| 2 | Run `FPROF=1 EVENT_PROF=sql.active_record` on the slowest suite | This finds SQL and factory pressure. |
| 3 | Sort files by SQL events and factory count | Optimize cost, not file count. |
| 4 | Pick one file | Small batches keep reliability easy to verify. |
| 5 | Identify examples above ~250 SQL events | Those examples usually have setup duplication. |
| 6 | Move stable read-only setup to `let_it_be` | Avoid rebuilding the same parent graph. |
| 7 | Use `build_stubbed` only for pure read/predicate checks | Do not fake DB behavior that is under test. |
| 8 | Keep mutation rows per-example | State transitions must stay isolated. |
| 9 | Rerun the focused file | Prove the local change first. |
| 10 | Rerun full verification | Make sure the suite still tells the truth. |

The first useful command is usually:

```sh
env FPROF=1 EVENT_PROF=sql.active_record EVENT_PROF_EXAMPLES=1 EVENT_PROF_TOP=40 \
  bundle exec rspec spec/path/to/heavy_spec.rb --format progress
```

The first useful question is:

> What did this example create that it never actually used?

That question is where most safe wins start.

---

## The practical playbook

This is the pattern I would reuse:

### 1. Measure before changing

Use SQL and factory profiling:

```sh
env FPROF=1 EVENT_PROF=sql.active_record EVENT_PROF_EXAMPLES=1 EVENT_PROF_TOP=40 \
  bundle exec rspec spec/path/to/heavy_spec.rb --format progress
```

Do not guess.

### 2. Sort by cost, not file count

The current 10.1% progress produced a 34% runtime reduction because the files were chosen by cost.

Randomly refactoring 10% of files would not do that.

### 3. Separate read behavior from mutation behavior

Use:

- `build_stubbed` for pure read/predicate checks
- `let_it_be` for stable read-only parents
- persisted per-example rows for mutations, callbacks, uniqueness, scopes, and state transitions

### 4. Split broad fixtures into narrow catalogs

This is especially important for reference data.

If a test only needs education levels, do not load company industries, platforms, categories, specializations, and business ID rules.

### 5. Keep request tests honest

Do not replace request tests with unit tests just because request tests are slower.

Request tests buy confidence across:

- routing
- auth
- controller envelope
- policy
- serializer
- DB state
- callbacks

Only move assertions down to blueprint/model/service tests when the request test is only duplicating shape checks already covered elsewhere.

### 6. Make verification cheap enough to run constantly

The goal is not only faster CI.

The goal is a proof loop cheap enough that you naturally run it before you are nervous.

---

## Closing

Test refactoring is easy to postpone because it rarely ships a visible feature.

But at high throughput, slow verification is not a background inconvenience. It is a tax on every commit.

At **10 PRs/day** and **3 commits/PR**, a 12-minute build turns into **6 hours/day** of waiting.

At the current **39.42-second** proof loop, that same cadence costs about **20 minutes/day**.

That is the difference between:

- batching risk because proof is expensive
- proving continuously because proof is cheap

This is why the refactor mattered.

Not because the suite became pretty.

Because the suite became usable at the speed the work was happening.
