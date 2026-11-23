---
layout: post
title: "Case Studies in SQL, Caching, Memory, Concurrency, and Production Failures"
date: 2026-11-23
author: Max Lukin
tags: [software-engineering, performance, caching, memory, postgresql, concurrency, reliability, ruby, rails, kubernetes, observability]
categories: [engineering, performance, reliability]
description: "Twelve engineering case studies: symptoms, diagnostics, fixes, measured results and open questions across SQL, caching, memory, races and production failures."
published: true
---

## TL;DR

**A development SQL query fell from about 1.56 seconds to 69 ms after better expression statistics. A local card-rendering component's median fell from 213.4 ms to 58.8 ms with current-input score reuse, allocating 76.6% fewer objects.** Those are measurements of specific work, with the conditions recorded below.

Across three investigations, we also simplified reference-data delivery, implemented changes to avoid demonstrated catalog retention and redundant scheduled scans, and corrected six reproduced deadlocks plus a separate stale-association failure. Public API behavior stayed unchanged, including ordering, translations, freshness and atomic privacy writes.

Other cases ended with a narrower diagnosis: liveness probes explained web-container termination, a pool-registration race was reproducible but unfixed, and a fast 503 still lacked an identified emitter. This post follows each case from symptom through evidence to the fix—or the next check needed to justify one.

## Results at a glance

| Case and measured work | Before → after / result | Scope |
| --- | --- | --- |
| [1. SQL query estimates](#case-1-query-plans) | About 1,560 → 69.325 ms; **95.6% less SQL time** | Development database; same results; buffer states not controlled. |
| [1. Prepared alias lookup](#case-1-query-plans) | 306.092 → 3.481 ms; **98.9% less lookup time** | Local prefix fixture; warm DB buffers, cold application cache. |
| [4. Current-input score reuse](#case-4-current-input-cache) | 213.430 → 58.807 ms median; **76.6% fewer allocated objects** | Warm calculation cache, 81 cards, 20 local component calls. Cold results below. |
| [5. Catalog retention](#case-5-worker-memory) | 3,000 projected + 3,000 source models retained → **zero of either** | One isolated 3,000-item diagnostic, after full GC; not production RSS. |
| [8–9. Locking and deletion](#case-8-lock-order) | **Six deadlock REDs and one separate foreign-key RED** corrected | Real local database operations; production recovery unrecorded. |
| [3. Artifact build validation](#case-3-build-validation) | Checker **exit 1 → exit 0**, unchanged archive | Integrity checks retained; compiled-data parity verified separately. |

Timing reductions use `(before − after) / before`. These results are not additive: SQL time, component latency, retained objects and correctness tests measure different things. No conversion from allocation counts to RAM, CPU utilization or production capacity is implied. Detailed conditions sit beside each case; the [verification ledger](#verification-and-rollout) separates local checks, deployment and observed recovery.

## System context and case index

> **Public-example note:** domain objects, routes and application names use fictional MMORPG terminology, following the convention in my [Rails CI case study]({% post_url 2026-08-29-rspec-ci-optimization-rails-bitbucket %}). The measurements and technical mechanisms are unchanged. Code examples below illustrate the design with renamed interfaces.

Think of a game lobby displaying public Character cards. Next.js renders the page, Rails supplies the data, Redis stores prepared selections, PostgreSQL holds current state, and Puma runs behind Istio in Kubernetes. Accounts own Characters; Characters have quest history, realm preferences and visibility protections. Solid Queue workers synchronize a cosmetic catalog, discover daily digest recipients and publish character-card snapshots. A world atlas supplies settlement autocomplete and nearby travel hubs. A separate public endpoint decides whether a Character page may be indexed by search engines.

The November 13–20, 2026 investigations crossed those boundaries without establishing one shared cause. Atlas queries and reference preparation came first; an export exposed a storage limit. Slow lobby requests then coincided with web liveness failures. Separate later events involved a 503, missing pool registration, worker OOMs and a web deadlock. The constraint stayed the same: improve stability while preserving existing API behavior.

All incident times are UTC. Each case starts with its outcome and status so it can be read independently.

- **Query and request work:** [1. Query estimates and aliases](#case-1-query-plans), [2. Fixed reference data](#case-2-fixed-reference), [3. Artifact build rejection](#case-3-build-validation), [4. Work after a cache hit](#case-4-current-input-cache).
- **Memory and background execution:** [5. Retained graphs and worker OOMs](#case-5-worker-memory), [6. Overlapping scheduled scans](#case-6-job-admission).
- **Concurrency and state:** [7. Pool registration](#case-7-pool-registration), [8. Explicit and foreign-key locks](#case-8-lock-order), [9. Stale associations](#case-9-stale-association).
- **Production failures:** [10. Liveness restarts](#case-10-liveness), [11. Export storage eviction](#case-11-export-storage), [12. Intermittent HTTP 503](#case-12-http-503).

## Case 1. SQL estimates and prepared aliases {#case-1-query-plans}

**Outcome and status:** Improved in development and local comparisons; a later production sample confirmed serving behavior. Its unmatched baseline cannot establish a production speedup.

The settlement dropdown looked simple. Its implementation combined bundled
realm/subdivision references, a separately downloaded settlement corpus, Geo
queries, normalization and translated option construction. “The database is
slow” described only part of the request.

We captured the application's actual query before proposing another index. An
exact-name batch scanned approximately **3.9 million rows** despite existing
partial expression indexes. Ordinary `ANALYZE` still left a poor plan. For this
query, the missing piece was useful relation-level statistics for its English-name
expression, not another copy of the same index.

This is the shape of the owner-run correction, using fictional relation names:

~~~sql
-- Approved source-owner maintenance, not a request or application startup task.
CREATE STATISTICS world_atlas_english_name_stats
  ON (lower(jsonb_extract_path_text(tags, 'name:en')))
  FROM public.world_atlas;

ANALYZE public.world_atlas;
~~~

[PostgreSQL supports statistics on expressions](https://www.postgresql.org/docs/18/sql-createstatistics.html),
including on materialized views. Creating the object and collecting its samples
are separate steps. The real maintenance script checked the source relation,
owner and existing definition, and used bounded lock/statement timeouts. A materialized-view
refresh retained the statistics object but required fresh samples; dropping
and recreating the relation required restoring the object too.

The recorded development query then used existing indexes: about **1.56 seconds
became 69.325 ms**, with the same 106 lookup keys, 4,932 rows and 52 resolved
identities. Grouping realm/name evidence subsequently reduced transfer to 1,443
rows without losing ambiguity information. The plan and result comparison—not
the mere existence of an index—supported the change.

A separate wide-prefix query benefited from a narrow covering candidate phase
before fetching full tags. We retained the original path for ambiguous internal
or boundary ties rather than silently introducing a new ordering rule. In the
local 500,000-row fixture, all 70 ordered comparisons matched, but those two
fallback cases were **35.8% and 31.3% slower**. Correctness-preserving fallback is
a real cost, not an exception to hide beneath the best-case speedup.

The runtime queries stayed in ActiveRecord/Arel. PostgreSQL-specific DDL lived in
explicit source-owner scripts, not in a migration for the wrong Rails database.
Concurrent index creation still needed definition/validity checks and a recovery
path: [PostgreSQL documents its extra scans, waits and possible invalid index](https://www.postgresql.org/docs/18/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY).
We did not recreate valid indexes on every deployment. The earlier
[query-plan walkthrough]({% post_url 2026-11-16-slow-api-endpoints-postgresql-query-optimization %})
contains the longer SQL diagnostic sequence; the later work here tested its
runtime and rollout limits.

### Nearby hubs were slow before the hub lookup

The other endpoint first resolved a settlement, then searched nearby travel
hubs. The costly part expanded names and aliases from JSON during each new
settlement search. The bounded hub query already used its index; adding another
hub-table index had no supporting plan evidence.

The atlas data owner instead published a normalized alias table. Each row carried
a searchable name, eligibility, coordinates and explicit tie ranks. Rails could
filter by realm and prefix, order by population, name rank and stable source
order, then fetch one winner. It no longer expanded the source names on that
request. Existing caches remained useful for repeats; the indexed reader reduced
work on a miss.

Publication alone was not activation. The developer's fast owner-role query
initially concealed two blockers: the application role lacked `SELECT`, and the
serving process still had the alias flag off. We had to verify the compatible
table/index, grant, result parity and **effective configuration in running
processes**, then measure the endpoint. A saved deployment secret was not proof
that old pods had consumed it. An enabled but unavailable alias source retained
its typed failure; it could not become a cached successful empty result.

### Query and lookup measurements

The location investigation began on November 13. The query comparison used the development database; the other two comparisons used local fixtures. These are component measurements.

| Measured boundary | Before | After | Scope and correctness evidence |
| --- | ---: | ---: | --- |
| Exact Geo name batch, development database | About 1,560 ms | 69.325 ms | **About 95.6% less SQL time** after expression statistics; same 4,932 rows and 52 resolved identities. Buffer states were not controlled. |
| Subdivision resolver, local component | 4,277.970 ms total | 59.802 ms total | **98.6% less elapsed time** across 3,247 exact-parity cases; not a per-request time. |
| Settlement-prefix reader, local fixture | 306.092 ms | 3.481 ms | **98.9% less** for one prefix; warm DB buffers, cold application cache; 50,012 settlements / 140,016 aliases, eleven matching winners across the cases. |

### A separate SQL-observability gap

During the November 17 lobby investigation, a read of `public.pg_stat_statements` against the primary application database returned `relation does not exist`. This was a separate database from the external atlas used by the queries above. The error established the absence of that named relation at that connection and schema; it did not establish that query statistics were unavailable everywhere.

We wrote a separate discovery and enablement plan. Useful initial reads include:

~~~sql
SELECT current_database(), current_user;

SELECT e.extversion, n.nspname AS extension_schema
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'pg_stat_statements';

SELECT name, setting, pending_restart
FROM pg_settings
WHERE name IN ('shared_preload_libraries', 'compute_query_id');
~~~

The database owner needed to establish server configuration, extension schema and observer privileges. [PostgreSQL documents the distinction between server preload and database-local extension objects](https://www.postgresql.org/docs/18/pgstatstatements.html). No `pg_stat_statements` enablement, observer grant, restart or preload change was made for this investigation. Better measurement was planned; it was not a performance fix already delivered.

## Case 2. Replace an unnecessary reference-data lifecycle {#case-2-fixed-reference}

**Outcome and status:** Fixed-reference design delivered and observed serving requests. Local parity and fork/GC checks passed; representative Linux first-worker and load acceptance remained incomplete.

The first autocomplete improvement moved source preparation outside requests.
It used durable/shared storage, immutable generations, publication leases,
scheduled refresh, background polling and last-good fallback. That solved a real
request-time problem, but introduced a new release dependency: enabling the reader
before a complete compatible snapshot existed prevented readiness.

The complexity was not free after startup either. A local background-refresh
experiment exposed roughly **230 ms of scheduling delay on a short request** with
whole-snapshot loading. Changed-country publication reduced that work but still
needed lifecycle machinery. Lower loader priority was a scheduling hint, not a
latency guarantee.

Then we revisited the requirement. The dropdown needed fast reads of a fixed
reference; **automatic settlement updates were not required**. We bundled the
approved corpus and its compiled search structures in the image instead:

~~~text
Offline compilation + reviewed source content
  → gzip JSON and manifest: hashes, formats, counts, coverage
  → image-build validation
  → load after Rails eager initialization, before web readiness/fork
  → requests read the prepared immutable reference
~~~

The captured package contained **249 realm groups, 162,740 settlement rows and
1,190,774 indexed labels**, occupying 43,585,628 compressed bytes. It was JSON,
not a database dump. The original upstream commit had not been recorded; the
package was pinned to captured content rather than pretending a mutable source
URL identified a revision. All 249 reconstructed/recompiled payloads matched,
including the prefix and duplicate-name indexes.

We kept locale behavior, homonyms, ordering and saved-selection round trips. The
request reader returned loaded data or failed; it never downloaded or compiled a
corpus for the first visitor. Snapshot refresh, polling and preparation-specific
pipeline/chart machinery were retired. A temporary local-check command and no-op
job preserved compatibility with older hooks and serialized work during rollout.

This removed one lifecycle, **not the external Geo database or the nearby-hub
alias lookup**. Live SQL, normal Rails work and GC could still vary. Reverting to
the old reader would also require its snapshot infrastructure; an image rollback
alone could not recreate blobs with a 48-hour expiry.

### Less isolated memory was not a better worker

A per-country decoding prototype used less memory in isolation but worsened
early GC pauses after fork. We rejected it and retained complete-archive decoding
at the established boot phase. No manual GC or tuning flag was added to hide the
regression.

The accepted local macOS comparison used 1,000 repeated requests per implementation,
with external Geo disabled: 500 realm-scoped and 500 global requests. Responses matched and major-GC counts stayed zero;
repeat-query sample p95s were similar or lower. Separate fresh-process pairs had
global-query p95 **1.2–2.6% higher**, without an extra observed GC boundary. That
small test was not proof of identical tails on deployed Linux workers. Boot,
first request, post-fork behavior and steady state needed separate observations.

An earlier user probe made the distinction visible: application time fell from
**1.004 to 0.335 seconds**, while client total fell from **1.323 to 0.809 seconds**.
Network time was part of the wait, but could not explain the server-side change.
Neither “cache warmup” nor “GC” was uniquely established without the corresponding
worker, SQL, allocation and cache evidence. A first request in a curl loop is not
necessarily a cold process or cold PostgreSQL buffer cache.

### What the deployed request sample established

After the fixed-reference release, a separate production check on **November 17
around 16:39 UTC** made five sequential GETs for each query. All 15 returned HTTP
200, with the same response hash within each query's five samples:

| Production request, fictional domain labels | Mean application time | Application range | Client total range |
| --- | ---: | ---: | ---: |
| Realm-scoped settlement autocomplete, `sa`, eight results | 537.524 ms | 344.84–785.52 ms | 677.64–1,347.55 ms |
| Global settlement autocomplete, `san`, eight results | 370.622 ms | 222.26–708.43 ms | 540.20–1,022.42 ms |
| Nearby travel hubs for one settlement | 29.144 ms | 18.38–46.09 ms | 324.81–453.92 ms |

Application time is `X-Runtime` converted to milliseconds. The original alert
showed 9.8 seconds for autocomplete over three calls and 7.0 seconds for nearby
hubs over two, but retained neither parameters nor a UTC window. **There is no
defensible production improvement percentage between those unmatched samples.**
The later check established serving behavior, not a cold-worker test, p95 or SLO.
CDN status was `DYNAMIC`; Rails result caches could still have been warm.

## Case 3. A source fingerprint rejected valid packaged data {#case-3-build-validation}

**Outcome and status:** Checker failure reproduced and corrected on unchanged data. The repair was included in the later sampled image; content and format validation remained mandatory.

A production image build failed during these changes. We needed to establish whether the [card-cache optimization](#case-4-current-input-cache) had broken the release or whether the failure came from another dependency.

The Jenkins/Kaniko log showed dependency installation succeeding. The failure occurred in the **packaged world-atlas artifact validator**, before Helm update. An application-source fingerprint was being used to decide whether bundled reference data remained compatible.

Tracing the validator's dependency list showed that a separate change to a broad source file altered the fingerprint. The homepage optimization had touched neither the fingerprint inputs nor the build instruction. The failed image never became the running application, so it could not explain the earlier pod restarts.

The location investigation supplied the repair; the lobby investigation independently checked attribution and later release inclusion. With the unchanged archive, the standalone checker went from **exit 1 to exit 0** after removing the whole-source/gem fingerprint. Archive and per-group checksums, format, sizes, coverage and compiled-buffer checks remained. An offline recompile of the captured corpus also matched all 249 payloads. We did not regenerate data or restamp a checksum to silence the error.

The lesson is to distinguish **artifact provenance** from **runtime compatibility**: a source hash can tell you what changed without proving that an existing data format is unusable. Structural validation still cannot prove semantic equivalence after a real normalization/compiler change; that needs parity testing. The standalone gate needed no Rails boot, database, cache or network. Both affected development and intended production builds rejected the fingerprint; an earlier “development passed” report was not evidence that this same revision passed.

Release-source checks and the subsequent Argo CD image observation confirmed that the score-reuse mitigation was deployed. The production checkpoint is recorded in [case 2](#case-2-fixed-reference).

## Case 4. Reuse expensive calculations after a cache hit {#case-4-current-input-cache}

**Outcome and status:** Current-input score reuse verified locally and observed deployed. Payload and freshness behavior stayed intact; sustained production recovery under comparable load was unverified.

The first useful correction was to ask **what the cache actually stored**.

Redis held selected, prepared cards. After reading them, Rails still checked current eligibility and refreshed volatile fields. That overlay loaded rating inputs, recalculated each character's score, rendered through Blueprinter and fingerprinted the result. A fresh Redis entry therefore left substantial request work intact.

The frontend team supplied two production examples from November 17 at 13:42:

| Fresh cache hit | Rails elapsed | ActiveRecord | Queries | GC |
| --- | ---: | ---: | ---: | ---: |
| Request A | 995 ms | 43 ms | 6 | 66 ms |
| Request B | 1,483 ms | 49 ms | 6 | 169 ms |

Those figures justified investigating work outside the logged database time. They did **not** prove that every remaining millisecond was Ruby CPU. Waiting, scheduling and runtime work needed further separation; subtracting ActiveRecord time from total time is not a CPU profile.

We inspected the overlay and measured its scoring path locally. When [SQL improvements leave an API slow]({% post_url 2026-11-16-slow-api-endpoints-postgresql-query-optimization %}), measure the remaining stages before adding another index or increasing a cache TTL.

### Component measurements

These November 17 local measurements cover the **Rails component that refreshes and renders selected character cards**. They exclude HTTP, network time, frontend rendering and concurrent production traffic.

| Component measurement | Original | New, calculation cache cold | New, calculation cache warm |
| --- | ---: | ---: | ---: |
| Median elapsed time | 213.430 ms | 194.399 ms | **58.807 ms** |
| Sample p95, 20 calls | 328.069 ms | 300.087 ms | 62.211 ms |
| Mean allocated objects per call | 698,237.8 | 693,234.7 | **163,361.6** |
| Total GC time across 20 calls | 1,351.116 ms | 987.386 ms | 43.809 ms |
| SQL SELECTs per call | 5 | 5 | 5 |

The warm median was **72.4% lower**, or **3.63× faster**. The cold median improved by 8.9%; cold allocations fell only 0.7%. Reductions use `(before − after) / before`. Allocated-object counts measure allocation volume, **not retained RAM, RSS or CPU utilization**; we did not establish percentage improvements for those metrics. The p95 describes this small sample, not a production tail-latency estimate.

The instrumented test fixture used Ruby 3.4.4 and an isolated PostgreSQL test database: 81 characters, each with six skills, four quest-history entries and two contact entries; 45 had saved biography scores and 36 required fallback scoring. Each scenario had three unmeasured warmups and 20 measured calls, fresh ActiveRecord objects, SQL query caching disabled, and GC enabled. Cold runs cleared only the new calculation cache before each call. Full rendered payloads and ETags remained equal, and the stored base payload remained unchanged.

### Reuse the calculation while reading current inputs

The safe reuse boundary was the numeric character score. Current visibility, selection, rendering and response validation could continue as before.

The revised path was:

~~~text
Read prepared cards from Redis
  → read current eligibility and narrow scoring inputs
  → hash the complete scoring inputs
  → reuse a score on a match; otherwise call the existing scorer
  → render current cards and compute the response fingerprint
~~~

We replaced full child-record hydration with batch scalar projections. Lightweight input objects still delegated to the canonical scorer, so the optimization did not introduce a second set of scoring rules. Contact values were reduced to the counts the scorer actually used before forming the cache identity.

The central operation can be expressed as this schematic Ruby:

~~~ruby
# Illustrative interfaces; these names are fictional.
SCORE_CACHE = ActiveSupport::Cache::MemoryStore.new(
  size: 4.megabytes,
  expires_in: 1.hour
)

def character_score(inputs)
  # inputs must contain every current value used by CanonicalCharacterScore.
  key = Digest::SHA256.hexdigest(Marshal.dump(inputs))
  cached = begin
    SCORE_CACHE.read(key)
  rescue StandardError
    nil
  end
  return cached if cached.is_a?(Float) && cached.finite? && cached.between?(0, 5)

  score = CanonicalCharacterScore.call(inputs)
  begin
    SCORE_CACHE.write(key, score)
  rescue StandardError
    # A publication failure must not discard a freshly calculated result.
  end
  score
end
~~~

The real implementation batches both input reads and cache reads/writes, and separately handles legacy ambiguity. Only cache-operation failures become misses; a scoring defect must remain visible.

**The hour controls retention. Current inputs determine validity.** If a skill changes, a child row is deleted or a shared classification changes, the next read derives a different key. This also covers direct SQL and bulk updates that bypass model callbacks or leave the parent timestamp unchanged.

Only a digest and a numeric score survive between requests. The temporary serialization is used for hashing; no `Marshal.load` is involved. This choice avoided recursive JSON conversions on every lookup. It is a process-local identity, not a portable serialized format. Ruby explicitly warns against [loading untrusted Marshal data](https://docs.ruby-lang.org/en/3.4/Marshal.html#module-Marshal-label-Security+considerations).

Rails' [MemoryStore](https://api.rubyonrails.org/classes/ActiveSupport/Cache/MemoryStore.html) holds data within one process and prunes against its configured size. Our 4 MiB setting therefore applies per serving process; it is not a total application RSS limit. Each new process warms independently, and identical concurrent misses can still compute the same score. Correctness does not depend on cross-process sharing or single-flight behavior.

The five SQL reads in the benchmark remained five. That was intentional: freshness still required current inputs. We reduced repeated scoring and object construction while preserving the reads that made reuse safe.

We also added ActiveSupport notifications around input collection, scoring, rendering and fingerprinting, with bounded cache-hit counts. That gives the next investigation smaller stages to measure. Their export into SigNoz was not verified; defining an instrumentation event does not make it appear in a distributed trace. Future scoring-rule changes must update the projected inputs and their regression cases together.

### Preserve the awkward cases too

Legacy data exposed a subtle trap. Two skill names could normalize to the same value. The old scorer used a last-row-wins rule, making the result depend on the reader's existing row order. A narrower SELECT could change that order and silently change a score.

For an ambiguous batch, we kept the original reader and skipped reuse for the whole batch. Adding a new tie-breaker would have changed existing behavior. The fallback fixture preserved payloads and ETags but added one preliminary SELECT, moving from five to six reads, and about **0.8% more allocations**. Its production frequency was unknown. The headline warm-path saving does not apply to that case.

Regression coverage exercised direct writes and deletes with unchanged timestamps, classification changes, zero and half scores, duplicate names, malformed cached values, cache IO failures and mutation between input collection and publication. Visibility and eligibility still came from the live read; the optimization did not grant a stale character permission to appear.

The delivered change preserved card selection, JSON, ETags, existing conditional-request behavior, Redis keys and TTLs, and numeric rating semantics. It required no migration, new environment setting, cache reset or extra warming job. An image rollback could remove the optimization without deleting Redis data.

### Why we did not start with whole-page caching

Cloudflare HTML caching was proposed during the incident. The page varied by session, geography, theme, language and bot handling. CSP nonces also had to stay consistent, and requests to the same URL could expect either HTML or a React Server Components response. A simple URL cache key did not represent that response contract.

A separately reported frontend data-cache implementation used 60-second reuse, shared concurrent fetches, an eight-second timeout and bounded stale fallback. Its later deployment was not verified in this investigation. It could complement the backend fix: frontend reuse reduces backend calls, while score reuse reduces work in the calls that still arrive. Neither change proves traffic filtering or attack resistance. The frontend cache's freshness policy also needs its own review; it is not part of the backend's preserved current-input behavior.

## Case 5. Retained object graphs, query caches and worker OOMs {#case-5-worker-memory}

**Outcome and status:** Catalog retention corrected in local regressions and an isolated diagnostic. The memory patch was absent from the image observed during the OOM investigation; its production effect remained unmeasured.

The November 17 web-container evidence did not show `OOMKilled`. Two later worker terminations did: **November 19 at 19:35:54 and 23:30:54**, both at a **5,888 MiB limit—5.75 GiB**. The preceding container incarnations had lasted about four hours and 26 minutes, and seven hours and 50 minutes.

For the first kill, the alert reported a sampled working-set peak of 5,830 MiB. That is not necessarily the instantaneous usage at termination. The alert also suggested larger requests and limits, but those were heuristic headroom calculations, not evidence of a required steady state.

Each kill followed a catalog-job start by roughly 54 seconds. The second worker's bounded previous-log window contained only one unmatched job start: catalog synchronization. Its latest captured digest had finished earlier. The window could not account for work that began before it, lost completion logs or every allocation in the process.

A separate read-only sampling window on November 19, **20:05:47–20:09:18**, showed one worker’s container working set moving **5,357 → 5,637 → 5,267 MiB** during and after catalog work, with no concurrent digest captured there. Another stayed around **3,113–3,117 MiB** while digest sweeps overlapped. That strengthened the catalog lead. It was an observation before deployment, not a before/after improvement chart.

### The attached exception was a lead, not the crash reason

The first alert included an earlier `Net::OpenTimeout`: a handled, roughly three-second TLS connection timeout about two and a half hours before the kill. The second included an `ActiveRecord::Deadlocked` from a web request roughly 84 minutes before its worker died.

Those attachments were service-level recent exceptions. They did not establish causality. We joined the exact process, workload and timestamps before investigating either as an OOM explanation. That is the same discipline the 503 investigation needed: a nearby error is useful context, not a substitute for the missing causal edge.

The operator confirmed that the memory patch had not been deployed at the second OOM.

### Why batching retained completed records

The catalog synchronizer read in batches, but a shared cosmetic-type model lived longer than any batch. Assigning that model through an ActiveRecord association populated its inverse collection. The type could therefore keep projected items—and their source models—reachable after the loop moved on.

~~~text
Synchronizer
  └─ shared cosmetic type
       └─ inverse collection
            ├─ projected item from batch 1 ─ source item
            ├─ projected item from batch 2 ─ source item
            └─ ...
~~~

A batch size bounds the current query result. It does not bound everything reachable from a longer-lived object. Even unchanged rows took the assignment path, so a run that wrote little could still retain a large graph.

The fix assigned scalar foreign keys and retained the already-loaded type as a validation target without adding processed items to its inverse collection. That preserved validation while avoiding a lookup per row. Temporary indexes were cleared after use. We did not disable inverse behavior globally or bypass domain callbacks simply to make an object count smaller.

The decisive regression used **1,001 records across the real 1,000-row batch boundary**, then repeated unchanged projection. It failed on the old implementation and passed after the change. It also checked that the fix did not introduce validation N+1 queries. The separate 3,000-item diagnostic below isolated the reachability mechanism while keeping the synchronizer alive.

In [case 4](#case-4-current-input-cache), scoring allocated temporary objects. Here, references kept processed objects alive. Narrower representations helped both, but allocation volume and retained reachability required different measurements.

### Retained-object diagnostic

A separate November 19–20 investigation used fresh Ruby 3.4.4 / ActiveRecord 8.1.4.1 processes and **3,000 fabricated, unchanged cosmetic projections**. It measured after full GC while the synchronizer and shared type object remained reachable. Setup read schema metadata; the projection performed no SQL writes or S3 IO.

| Isolated projection measurement | Original assignment path | Revised assignment path |
| --- | ---: | ---: |
| Retained projection models | 3,000 | 0 |
| Retained source models | 3,000 | 0 |
| Measured Ruby heap change from baseline | About +18.36 MiB | Approximately baseline: −65,328 bytes in this run |
| Live-slot change from baseline | +163,574 | −1,442 in this run |
| Assignment-loop elapsed time | 2,657.8 ms | 95.1 ms |

The byte estimate came from `ObjectSpace.memsize_of_all`; it is not total native/process memory. Negative deltas are collection/baseline effects, not negative allocations. The timing covers that loop, excluding full-GC sampling, catalog listing and database writes. It is a **single isolated diagnostic, not a full-job benchmark, CPU-utilization result or production RAM saving**. The reachability result establishes retention within a projection; it does not prove a permanent cross-run leak or account for a multi-gigabyte container limit.

### Query-cache lifetime was another retention boundary

Solid Queue 1.2.1 ran job execution through the Rails executor. ActiveRecord's query cache could retain SELECT results during that work. The installed Rails 8.1.4.1 implementation had a default limit of **100 cache entries**, with eviction and write invalidation. An entry limit is not a byte limit: a small number of wide result sets can still matter.

We wrapped the full catalog synchronization and standalone projection in `uncached` scopes, preserving normal write invalidation and restoring the caller's cache state on both success and failure. The exact query-cache bytes at either kill were not measured; the fix removes an unnecessary retention source without declaring it the whole OOM cause.

A schematic boundary is:

~~~ruby
# Fictional names; the application retains its existing publication checks.
def synchronize_cosmetics
  ApplicationRecord.uncached do
    synchronize_complete_catalog
  end
ensure
  clear_temporary_catalog_indexes
end
~~~

The complete object-store metadata and catalog indexes **were still materialized**. Deactivation and publication still waited for a complete, successful listing. Streaming everything or publishing partial batches would have needed a different consistency design. The patch removed demonstrated retention while preserving source identity, ownership, claims and atomic publication.

### A falling Ruby heap need not produce a falling RSS

Full GC belonged in the isolated diagnostic, not at the end of every production job. A process can release Ruby objects while the allocator keeps pages; native allocation, shared pages and concurrent jobs also affect resident memory.

We added inexpensive lifecycle and catalog-phase samples: PID, current RSS, mounted-cgroup usage, allocator-map presence and available Ruby heap/GC counters. The sampler omitted inaccessible fields and did not change job outcomes on sampling failure. It used no forced GC, ObjectSpace traversal or subprocesses in normal job execution.

| Signal | Useful question | Interpretation limit |
| --- | --- | --- |
| Ruby live slots / heap pages | Did the Ruby heap grow, and did natural collection occur? | Live slots can include garbage not yet collected; they are not total process bytes. |
| Allocation and major/minor GC counters | What changed during this process interval? | Cumulative per process; concurrent jobs contribute to the same delta. |
| Process RSS | How much memory is resident now? | Not a peak; summing forked processes can double-count shared pages. |
| Mounted-cgroup usage / container working set | What memory is charged or reported at that scope? | Neither is interchangeable with Ruby heap; the mounted root may have broader scope. |
| Allocator library mapping | Is a matching library loaded in this process? | Presence alone does not prove which allocation paths use it or whether it helps. |

Catalog phase timing was cumulative. The early interval included lock wait and listing; the finished sample preceded final reference cleanup. An OOM can prevent both completion and failure logs. For deployed follow-up, correlate job identity through the logging context and compare the same process incarnation rather than assigning every process delta to the named job. These new samples had not yet been observed on the running image at the retained checkpoint.

The image installed jemalloc, but the direct worker command bypassed the web entrypoint that configured preloading. Production process mappings were unavailable through the authorized access path. We left the allocator and resource limits unchanged instead of treating installation as proof of use. A new diagnostic Rails process would have measured itself, not the existing worker.

## Case 6. Coalesce overlapping scheduled scans {#case-6-job-admission}

**Outcome and status:** Finite admission control implemented and tested with the real queue adapter. Redundant overlap was observed before the fix; post-release memory and execution acceptance were unrecorded.

Digest discovery ran every minute, while recorded sweeps took **189–298 seconds**. Two sweeps overlapped in one process for at least **129 seconds**, and another worker also scanned. Ready depth could be zero while jobs were already claimed and retaining their working state.

The correction was admission control for redundant discovery ticks. In the installed Solid Queue version, the design was equivalent to:

~~~ruby
# Illustrative job name and key; the domain's send/receipt rules stay unchanged.
class DiscoverDailyDigestsJob < ApplicationJob
  limits_concurrency to: 1,
    key: -> { "daily-digest-discovery" },
    duration: 15.minutes,
    on_conflict: :discard
end
~~~

A constant key made this one global permit for that job class, not one permit per recipient. The [Solid Queue concurrency controls](https://github.com/rails/solid_queue/blob/v1.2.1/README.md#concurrency-controls) describe admission, conflict handling and finite duration. Discarding a redundant scan was acceptable only because the existing recipient-local scheduling, eligibility, delivery receipts and unfinished-run recovery remained intact.

The lease was not an execution-lifetime mutex. Queue waiting consumed its duration; expiration could admit new work while an old execution was still alive. Legacy jobs without a concurrency key and direct execution could also overlap. Tests used the actual adapter to cover queued/running conflicts, normal and failure release, expiry and legacy jobs. Delivery idempotency remained necessary.

### Count what the deployment actually launches

The deployment had two worker pods and one pod called the scheduler. The scheduler's plain `bin/jobs start` command also launched configured workers. At one general-worker process per launcher, each launcher supplied five general threads and a separate one-thread lobby worker: **18 execution slots and six worker processes across three launchers**, plus supporting processes.

That was the observed topology, not a recommended fleet size. `RAILS_MAX_THREADS` did not override the queue's five-thread setting. Database-pool budgeting had to include all processes and rollout overlap, rather than multiply only the visibly named worker pods.

An empty ready queue did not justify manually starting another catalog sync. The catalog already serialized its core work with a database lock; another invocation could add waiting threads instead of useful throughput.

## Case 7. A missing pool looked like an upstream outage {#case-7-pool-registration}

**Outcome and status:** Registration race reproduced with zero database connections. No fix was implemented, and the exact production interleaving remained unproved.

On **November 19 at 12:15:16**, a character-card publication job failed with a
typed “travel hub source unavailable” error wrapping
`ActiveRecord::ConnectionNotDefined`. It looked like an external atlas
outage. The inner exception pointed to a different boundary: Rails could not
find the registered pool for that connection name, role and shard.

The wrapper caught several ActiveRecord errors. Its generic message did not
distinguish missing registration from a PostgreSQL socket failure, exhausted
server slots or a pool-checkout timeout. A local diagnostic using the real
initializer and ActiveRecord 8.1.4.1 forced this interleaving:

~~~text
A and B both observe no shared pool
A registers the pool
B resumes its earlier initialization and removes that registration
A requests connection_pool during the gap → ConnectionNotDefined
B completes registration
~~~

It reproduced the exception with **zero database connections**. The diagnostic
exited successfully because it captured the failure, not because a fix passed.
The exact production interleaving remained unproven: jobs overlapped in the
retained window, but the original registry stack and competing initializer calls
were unavailable. Later healthy atlas pods could not establish their health at
the incident time either.

The shared initializer still lacked synchronization at the source checkpoint.
Preparing the pool in Puma did not prepare separate job processes; a per-Character
job limit did not serialize different Characters initializing one shared pool.
The proposed correction was to guard the shared state check and registration,
recheck inside the guard, and test concurrent first use, failure/retry and fork
behavior.

Running a connection-statistics rake task would inspect its new process's pools,
not the failed worker's registry. PostgreSQL session counts describe another
boundary again. That process-locality distinction also matters for the allocator
and memory measurements elsewhere in this article. This race was separate from the atlas build gate,
the later database deadlock and the unresolved HTTP 503.

## Case 8. Include foreign-key checks in the lock graph {#case-8-lock-order}

**Outcome and status:** Six local deadlocks reproduced and corrected on November 20 with consistent acquisition order. Two participants in the historical production cycle remained unidentified; deployment and recovery were unrecorded.

The web request attached to the second worker alert failed at about **22:06:29 on November 19**. It added quest history during Character onboarding. The request lasted about 1.095 seconds, with **1.003 seconds** in a Character `SELECT … FOR UPDATE` span.

PostgreSQL reported a **three-session wait cycle**. One edge was an exclusive lock on a tuple, not a table-wide exclusive lock. The other two transactions were unidentified. Retained web logs began after the event, and the available database-log access did not yield the historical report. Current activity views could not reconstruct those ended sessions.

Source inspection nevertheless exposed a concrete inversion. Quest-history persistence and its visibility-protection update acquired Account then Character. Realm-preference completion and the name-only update path could acquire Character then Account. Those controller paths did not already hold the missing Account lock; mixed contact/name updates could acquire it earlier.

~~~text
Locally reproduced two-transaction cycle:

Quest-history write                  Realm/name write
  owns Account                         owns Character
  waits for Character ───────────────→ held here
       held here ←──────────────────── waits for Account
~~~

[PostgreSQL's locking documentation](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-DEADLOCKS) explains why consistent acquisition order matters and why a victim transaction does not identify the whole cycle. Our two-party reproduction proved the application defect. It did not identify the other two participants in the historical three-session incident.

### The first INSERT exposed edges hidden from a code search

Fixing the explicit opposite-order calls was only the beginning. First snapshot publication, share creation and Character-offline system messages inserted rows with an Account foreign key while holding Character.

A simplified share case looked like this:

~~~text
Quest-history transaction:
  owns Account → waits for Character

First share publication:
  owns Character → INSERT references Account
                 → foreign-key check waits for Account
~~~

The second path did not need to call `account.lock!` explicitly to participate. Tests that updated only existing rows could miss the first-insert edge.

We moved the common root lock to the transaction boundary:

~~~ruby
# Fictional names; existing validation, outcomes and writes stay inside the locks.
character.account.with_lock do
  character.with_lock do
    create_share_with_existing_checks(character)
  end
end
~~~

The shared aggregate fence was more careful than this single-owner sketch: sorted Account locks first, an uncached Character-ID read, sorted Character locks, then uncached set revalidation. It retained up to three savepoint attempts when the set changed. Account deletion acquired the fence before its audit insert and dependent callbacks.

Direct publication became Account → Character → snapshot. Durable publication kept Account → Character → refresh → snapshot plus its execution-token checks, last-known-good payload and trailing-generation behavior. Character-only writers retained their existing ordering; we did not impose a new Account lock on every write or claim safety for arbitrary ownership reassignment.

### Regression evidence for lock order and deletion

The lock regressions used committed records, separate connections, real transactions and foreign-key INSERTs. Bounded barriers and SQL observation brought the operations to the contested boundary; bounded joins and cleanup prevented a failed test from leaving threads behind.

| Original-path regression | RED evidence | Corrected coverage |
| --- | --- | --- |
| Onboarding versus realm completion and name change | Two real PostgreSQL deadlocks | Both writes complete; quest history, visibility protection and refresh intent survive. |
| First snapshot, direct and execution-fenced | Two real PostgreSQL deadlocks | Publication succeeds while preserving execution ownership and payload behavior. |
| Share creation and offline transition | Two real PostgreSQL deadlocks | The share and actual request/system-message outcomes remain correct. |
| [Separate stale-association deletion](#case-9-stale-association) | One real foreign-key violation | Account, Character and refresh state are removed consistently. |

Mocking `ActiveRecord::Deadlocked` can test an error branch. It cannot show that the acquisition cycle has been removed. We also kept existing first-Character, replacement, rollback, owner-restriction and deletion tests. Provider/dispatch side effects could be stubbed; the contested SQL was real.

The privacy invariant was non-negotiable: save quest history **and** its required visibility protection, or roll both back. Moving protection into a best-effort after-commit callback or swallowing the exception would have made the endpoint look healthier while weakening its behavior. Blanket transaction retries were also not a substitute for fixing order.

More Account locks intentionally serialized same-owner work earlier. That can increase waiting; no general latency or throughput gain was measured. The correction removed the demonstrated cycles while preserving routes, parameters, JSON, statuses, authorization, validation and domain side effects. The exact historical production graph still needed its server log.

## Case 9. Reset stale association state after acquiring the fence {#case-9-stale-association}

**Outcome and status:** Separate foreign-key regression corrected locally on November 20. It used sequential committed writes through separate instances, not an overlapping creation-thread race.

An Account instance had cached `character == nil`; a first Character then committed through another model instance. The aggregate fence from [case 8](#case-8-lock-order) locked the current Account and Character rows before deletion. Dependent destruction still read the original instance's cached absence, skipped the Character, and failed the foreign key when deleting the Account.

The correction was small but belonged **after** the fence:

~~~ruby
# Called inside the destruction transaction, before dependent callbacks.
def lock_current_aggregate
  AccountCharacterFence.lock!(account_ids: id)
  association(:character).reset
end
~~~

This targeted reset preserved intentional unsaved Account attributes. An indiscriminate reload would have introduced another behavior change.

The local regression failed with the original cached absence and passed with the targeted reset. The [lock-regression table](#case-8-lock-order) includes its foreign-key result separately from the six deadlocks. The reusable distinction is between locking current database rows and refreshing the in-memory association a later callback will read.

## Case 10. Liveness failures restarted web containers {#case-10-liveness}

**Outcome and status:** Kubernetes events confirmed the termination trigger. The cause of slow probe responses and sustained production recovery remained open.

The earlier web logs were more severe than the [fresh-hit examples in case 4](#case-4-current-input-cache). A retained excerpt from **09:33:05–09:33:55 on November 17** contained 79 GET starts, 76 for the global lobby feed. Seventy starts shared one logged source address. The excerpt's 80 visible completions were all HTTP 200, taking **3,145–6,440 ms**.

Starts and completions straddled the excerpt boundaries, so their counts did not match. The source address and user agent did not establish who sent the requests. This was a bounded traffic sample, not a complete attack census.

Kubernetes supplied stronger evidence about the restart mechanism. Between **09:25:35 and 13:02:56**, aggregated events recorded **20 liveness-triggered terminations for each of the two original web pods**. Proxy logs also showed header-deadline timeouts while probing Puma's health endpoint.

At **13:13:12**, the web-container restart counts were 22 and 20. Their last termination states were `Error`, exit code 1; neither last state was `OOMKilled`. The two worker pods and scheduler had zero restarts at that snapshot. The [later worker OOMs](#case-5-worker-memory) had different termination evidence.

The supported conclusion was: **failed liveness probes triggered repeated container termination**. Why those probes were slow still needed CPU/throttling, thread occupancy, queue, database-wait and lifecycle evidence from the same window. Kubernetes distinguishes [liveness failures that trigger restarts from readiness failures that remove traffic eligibility](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/); the two signals answer different questions.

For a similar incident, capture the evidence while the original pod still exists. These read-only commands use fictional workload names:

~~~bash
kubectl --context="$incident_context" -n game-api get pod "$incident_pod" -o json
kubectl --context="$incident_context" -n game-api get events \
  --field-selector "involvedObject.name=$incident_pod" -o json
kubectl --context="$incident_context" -n game-api logs "$incident_pod" \
  -c web --previous --timestamps
~~~

Set the context and exact pod deliberately. Keep the image, container state, pod creation time, event timestamps and relevant current logs together. A later ready pod cannot reconstruct the old one, and container restart counters do not capture every Puma worker replacement.

### A convincing before-and-after chart that would have been wrong

Two retained log cohorts had median Rails times of **4,566 ms and 1,538 ms**. It would have been easy to present that as a successful fix.

Both cohorts predated the optimization. Their windows overlapped across pods, while traffic composition changed substantially. They supported a workload-sensitive performance investigation, not an improvement attributable to the new code.

The [case 4 benchmark](#case-4-current-input-cache) isolated component work. Evaluating restart recovery required a separate window with comparable traffic, image identity, cache warmth, latency, resource measurements and probe/restart deltas.

## Case 11. A read-only export exhausted pod storage {#case-11-export-storage}

**Outcome and status:** Export recovered through bounded streaming and a full isolated restore. Scoped cleanup was recorded; incomplete multipart-upload auditing was unavailable.

Obtaining a local atlas copy exposed another failure on November 16. The export
wrote a compressed archive into a serving pod and exceeded its **1 GiB
ephemeral-storage limit**, causing eviction. Filesystem free space was not the
pod's storage budget. An older PostgreSQL client had also rejected the source
server's newer major version before the successful export.

The approved recovery streamed the compressed dump through bounded buffers to a
temporary object, then downloaded it over HTTPS. That removed the pod-local
archive and the VPN-bound download path; it did not eliminate database IO or
prove a new transfer-throughput figure. A dedicated, approved export workload is
a better starting point than borrowing a serving worker's headroom.

The **969,208,956-byte** archive passed integrity checks and a real isolated
restore with compatible PostgreSQL/PostGIS versions. Historical restore time was
**107.49 seconds**, followed by **2.76 seconds** for `ANALYZE`—restore timings, not
export or endpoint speedups. Three source materialized views were unpopulated;
the copy preserved that state rather than silently refreshing them.

This full-database archive was distinct from the packaged JSON reference.
[PostgreSQL's custom dump format](https://www.postgresql.org/docs/18/app-pgdump.html)
is restored with `pg_restore`; listing or decoding an archive alone does not test
its complete restore. Temporary files/completed objects were cleaned up within
the inspected scope, while incomplete multipart-upload auditing was denied.
That limit stayed in the record. Storage eviction was a separate mechanism from
the web probe restarts and later memory-limit kills.

## Case 12. Locate the emitter of an intermittent 503 {#case-12-http-503}

**Outcome and status:** Failed fetch observed and the investigation narrowed. The response body, emitting hop and repair remained unresolved; no retry or timeout change was made.

On **November 18 at 15:11:46.934**, a new alert pointed to a public Character page. Next.js metadata generation issued two parallel fetches: character details and a public crawl verdict.

The anonymized exception was:

~~~text
GET /api/characters/[id]/crawl_verdict failed: Service Unavailable
~~~

| Observation for the selected event | Result |
| --- | --- |
| Character-details fetch | 200, 270.56 ms; Rails logged 235 ms |
| Crawl-verdict fetch | **503, 151.40 ms**, 95 uncompressed response bytes |
| Matching Rails start for the failed fetch | Not found in the inspected combined logs |
| Nearby successful crawl-verdict requests | 17 ms before, 13 ms after |
| Outer page request | **200, 1.01 s** |

The short failure and missing Rails start made a failure before the action plausible. A dropped connection between the destination sidecar and Puma was one candidate. It was still a hypothesis.

All 19 spans in the selected trace belonged to the frontend service. The response body had not been retained. The internal destination had not been independently mapped to its Service, and the inspected frontend source revision had not been matched to the deployed revision. Sidecar logs showed control-plane messages, not a correlated access record.

Source inspection suggested another important boundary:

~~~text
Next.js metadata generation
  → internal frontend Service
  → Next.js API proxy
  → configured backend URL and any gateways
  → destination sidecar
  → Puma / Rails
~~~

That was the route to verify. A proxy could relay a 503 it received from another hop. The backend action did not explicitly return 503 and did not call the lobby score cache, but shared resource pressure was still possible.

The frontend team's four-second sample counted five requests across two pods. That was insufficient to exclude queueing: request starts do not show threads already occupied by older requests. Likewise, the outer 200 did not establish that the generated HTML or SEO metadata was correct. We had not inspected that output.

### Find the emitting hop before changing timeouts

The next investigation was deliberately narrower:

1. **Recover the response diagnostic.** Correlate the failed fetch with sanitized frontend non-2xx logs, content type and response body. Map the actual destination and deployed frontend revision.
2. **Follow the same request through access logs.** Record the reporting proxy, direction, upstream host, response flags and response-code details. Confirm the logs cover the window using a successful request nearby.
3. **Investigate the identified hop.** Correlate the named pod's Puma worker lifecycle, readiness, connection reuse, backlog or overflow counters with the failure.

The useful proxy distinctions are:

| Correlated proxy evidence | Next check |
| --- | --- |
| `via_upstream` | Follow the upstream that supplied the status. |
| `UH` / `no_healthy_upstream` | Endpoint availability, readiness and ejection state at that reporting proxy. |
| `UO` | Upstream connection or pending-request overflow limits. |
| `upstream_reset_before_response_started{…}` | Preserve the exact detail and upstream address; establish whether this was the app-facing connection. |
| Matching Rails 5xx completion | Follow the application request and revise the pre-Rails hypothesis. |

These terms come from [Envoy response-code details](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/response_code_details) and [response flags](https://www.envoyproxy.io/docs/envoy/latest/configuration/advanced/substitution_formatter). Check the installed version. A reset detail becomes evidence about Puma only after the reporting direction and local upstream are established; it still does not explain what triggered the reset.

Where request logs are missing, existing mesh metrics can help choose the next workload to inspect:

~~~promql
sum by (
  reporter, source_workload_namespace, source_workload,
  destination_service_namespace, destination_service_name,
  destination_workload, response_code, response_flags
) (
  increase(istio_requests_total{response_code="503"}[5m])
)
~~~

Evaluate the query at the incident time in the appropriate datasource. Keep source and destination reporters separate: [Istio can report the request from both perspectives](https://istio.io/latest/docs/reference/config/metrics/). Preserve unknown destinations and check scrape coverage before interpreting a missing series. Standard labels do not identify this individual path or trace; the query narrows the search rather than proving the failed hop.

The alert's 42 exception occurrences were also not 42 demonstrated outages. The selected trace alone contained duplicate exception events, and the alert combined a short trigger window with a longer lookup for the latest exception. Count distinct failed fetches before calculating an error rate.

We did not change retries, timeouts, keep-alive or probes for this event. The result was an open investigation with a discriminating next step. If historical logs had expired, the next action would be a time-limited, workload-scoped capture of naturally occurring failures, reviewed with the platform owner.

## Verification and rollout {#verification-and-rollout}

**Verified locally** means the described test or diagnostic passed. **Deployed** means the relevant change was observed in a running release. **Resolved in production** requires a representative observation window. The table records the last retained checkpoint for each change; it is not a fresh health check.

| Change / investigation | Verification evidence | Deployment / production status |
| --- | --- | --- |
| [4. Current-input score reuse](#case-4-current-input-cache) | 82 focused examples; final fast suite 24,733 examples, zero failures, four pending; controlled payload/ETag parity and component benchmark | Mitigation observed in a later running image. Sustained comparable-load recovery unverified. |
| [10. Web liveness restarts](#case-10-liveness) | Event/log correlation established the restart trigger | Cause of probe slowness remained open; later worker OOMs do not explain this earlier web snapshot. |
| [1–2. Atlas queries and fixed reference](#case-1-query-plans) | Development-query and local ordered-result parity; static-reference fast suite 24,680 examples, zero failures, four pending; local fork comparison with external Geo disabled | Later image observed serving all 15 sampled requests. Representative Linux first-worker, concurrency and latency-SLO acceptance remain incomplete. |
| [3. Packaged world-atlas validation](#case-3-build-validation) | Standalone checker exit 1 → 0 on unchanged data; 23 focused examples; fast suite 24,863 examples, zero failures, four pending; all 249 compiled payloads matched | Repair included in the later sampled image. The lobby investigation independently checked release attribution. |
| [7. Shared atlas pool registration](#case-7-pool-registration) | Forced two-thread failure with zero DB connections | No fix shipped; exact production schedule unproven. |
| [11. Atlas export](#case-11-export-storage) | Full isolated restore passed; source view state preserved | Scoped cleanup recorded; incomplete-upload audit unavailable. Not an ongoing backup/recovery guarantee. |
| [5–6. Catalog retention and job admission](#case-5-worker-memory) | 59 focused examples; fast suite 24,679 examples, zero failures, four existing pending; retention regression failed before the fix | Memory fix had not reached the observed image during the later OOM investigation. Post-release acceptance unrecorded. |
| [8–9. Lock order and stale associations](#case-8-lock-order) | Six deadlock REDs plus a separate FK RED; focused suites of 384 and 72 examples passed; fast suite 24,767 examples, zero failures, four existing pending | Implementation and delivery recorded; deployment and live acceptance unrecorded. Two historical database participants remain unknown. |
| [12. Public crawl-verdict 503](#case-12-http-503) | A failed fetch and missing correlated backend evidence narrowed the next checks | Emitting hop and repair remained unresolved. |

The focused suites overlap and are not added together. Fast verification included RuboCop and the relevant runtime specs, followed by the repository's contract audit. Swagger generation enumerated examples in a dry run; those counts were not extra executed tests. The runtime checks above are historical results, not application tests rerun for this article.

For the memory release, the proposed acceptance window grew from five to **at least eight hours of comparable workload** after the second failed incarnation had lived nearly seven hours and 50 minutes. The plan also required repeated complete catalog runs, process-scoped memory/GC measurements, ordinary queue and claimed-job age, and digest completion. A quiet or stalled worker must not masquerade as lower memory demand. The window was a minimum planned observation, not proof against all future workloads.

For locking, acceptance would include normal onboarding, realm/name updates, first snapshot publication, sharing, availability and lifecycle operations, plus error rate and same-account lock waits. We did not create artificial destructive contention in production to test a local fix.

## Keep the evidence useful for the next incident

We retained one dated record per coherent investigation and short summaries in the runtime, jobs, SQL and domain guides. An index answered which files to read; a reusable template kept future records comparable:

~~~text
Symptom and UTC window
  → confirmed findings, competing hypotheses and missing evidence
  → change and preserved API/side-effect contract
  → reproduction and actual verification results
  → deployment checkpoint and measured recovery window
  → open questions, next evidence and owner
~~~

The full record kept source/commit references, safe measurements, failed approaches and diagnostic artifacts. Global engineering guidance retained the reusable lessons: inspect expression estimates before adding indexes, measure first-use/fork behavior, inspect inverse associations when batching fails to bound reachability, include foreign keys in lock graphs, and keep domain recovery separate from admission leases. A later contributor can update a conclusion without rewriting what was known at the earlier checkpoint.

The common thread was measurement scope, not a shared cause. The cache hit, retained model graph, admission lease, database wait and HTTP failure each required evidence at its own boundary. A successful local reproduction was valuable even when the full production incident remained open.

## Conclusion

The most useful fixes changed a specific mechanism: better estimates let existing indexes do their job; prepared aliases removed repeated expansion; current-input keys reused scores without adding a stale-data allowance; scalar association handling stopped completed graphs from remaining reachable. Other changes repaired coordination: finite admission for redundant scans, root-first database locks and a targeted reset of stale model state.

The implementation details differ, but the debugging sequence is reusable: **observe the symptom → identify the work or state involved → reproduce the mechanism where possible → change it while preserving behavior → verify the result at the right scope**. The rejected smaller loader, slower compatibility fallbacks and unmatched HTTP samples were as useful as the headline improvements because they constrained what we could safely claim.

Several cases remain open: the pool-registration race has no implemented fix, the historical deadlock graph has missing participants, and the 503 still needs correlated proxy evidence. The case summaries and verification table keep those next steps attached to the evidence. A future investigation can continue from that checkpoint without treating a passing test, a deployment or a quiet dashboard as the same result.
