---
layout: post
title: "From MySQL to PostgreSQL: A Practical Migration Guide for Rails APIs"
date: 2025-12-03
author: Max Lukin
tags: [rails, postgresql, mysql, migration, database, orm, active-record, best-practices]
categories: [engineering, rails, databases, infrastructure]
description: "A comprehensive guide to migrating your Rails application from MySQL to PostgreSQL—covering database-agnostic code patterns, the migration process, PostgreSQL's advanced features, and multi-schema architecture strategies."
---

> _"The best time to write database-agnostic code is from day one. The second best time is before your migration."_

When we started building the Wigiwork API, we chose MySQL for its familiarity and ease of setup. As our requirements grew—AI vector embeddings, geospatial queries, graph routing—we realized PostgreSQL wasn't just an alternative, it was a necessity.

This post documents our migration journey and shares the patterns that made it nearly painless.

---

## Table of Contents

1. [Why We Migrated](#1-why-we-migrated)
2. [The Database-Agnostic Foundation](#2-the-database-agnostic-foundation)
3. [The Migration Process](#3-the-migration-process)
4. [PostgreSQL vs MySQL: A Technical Comparison](#4-postgresql-vs-mysql-a-technical-comparison)
5. [Advanced PostgreSQL Features](#5-advanced-postgresql-features)
6. [Multi-Schema Architecture](#6-multi-schema-architecture)
7. [Migration Tips and Lessons Learned](#7-migration-tips-and-lessons-learned)

---

## 1. Why We Migrated

### 1.1 The Growing Feature Requirements

Our application started as a straightforward REST API. Over time, we needed:

| Requirement | MySQL Solution | PostgreSQL Solution |
|-------------|---------------|---------------------|
| Vector similarity search (AI) | External service (Pinecone, Weaviate) | Native `pgvector` extension |
| Geospatial queries | Limited spatial functions | PostGIS (industry standard) |
| Graph routing | External graph DB | pgRouting extension |
| Full-text search | Basic FULLTEXT | Powerful tsvector/tsquery |
| JSON querying | JSON functions (limited) | JSONB with GIN indexes |

**The math was simple:** Three external services vs. one PostgreSQL instance.

### 1.2 The Hidden Costs of Multiple Databases

Running MySQL + Pinecone + a graph database meant:

- **3x infrastructure complexity** — More services to monitor, scale, and pay for
- **Data synchronization overhead** — Keeping vector embeddings in sync with source data
- **Network latency** — Cross-service queries add milliseconds
- **Operational burden** — Different backup strategies, different failure modes

PostgreSQL with extensions gave us **one database to rule them all**.

### 1.3 Our Starting Point

Before migration, our codebase analysis revealed:

| Category | Count | Status |
|----------|-------|--------|
| MySQL-specific SQL | 1 function | Required fix |
| JSON columns | 45 | Upgrade to JSONB |
| Check constraints | 11 | Already compatible |
| Raw SQL queries | 15+ | Already compatible |
| Configuration files | 4 | Required update |

**98% of our code was already database-agnostic.** This wasn't luck—it was intentional architecture.

---

## 2. The Database-Agnostic Foundation

### 2.1 Why Database-Agnostic Code Matters

Writing database-agnostic code isn't about planning to switch databases. It's about:

1. **Portability** — Your code works on any database Rails supports
2. **Testability** — SQLite in CI, PostgreSQL in production
3. **Maintainability** — Standard patterns are easier to understand
4. **Future-proofing** — Requirements change; your code adapts

### 2.2 The Rules We Follow

Our `AGENTS.md` (development guidelines) includes this rule:

> **Rule #9: Database-agnostic queries.**
> Use Arel and ActiveRecord abstractions instead of raw SQL or database-specific syntax. This ensures portability when migrating databases.

### 2.3 Patterns That Work Everywhere

**✅ Use ActiveRecord Query Interface**

```ruby
# Good: Works on any database
User.where(status: :active)
    .where("created_at > ?", 1.week.ago)
    .order(created_at: :desc)
    .limit(10)
```

**✅ Use Arel for Complex Queries**

```ruby
# Good: Database-agnostic date ranges
class CreditTransaction < ApplicationRecord
  scope :by_requested_dates, ->(dates) {
    ranges = Array(dates).filter_map do |date|
      year, month = date.split("-").map(&:to_i)
      start_date = Time.zone.local(year, month, 1).beginning_of_day
      end_date = start_date.end_of_month.end_of_day
      arel_table[:created_at].between(start_date..end_date)
    end
    where(ranges.reduce(:or))
  }
end
```

**✅ Use Standard SQL Functions**

```ruby
# Good: LOWER, COALESCE, CASE work everywhere
scope :search, ->(term) {
  where("LOWER(name) LIKE :term OR LOWER(email) LIKE :term",
        term: "%#{term.downcase}%")
}

# Good: COALESCE for fallbacks
order(Arel.sql("COALESCE(last_message_at, created_at) DESC"))

# Good: CASE for conditional ordering
order(Arel.sql("CASE WHEN status = 'urgent' THEN 0 ELSE 1 END"))
```

**✅ Process Dates in Ruby**

```ruby
# Good: Fetch timestamps, format in Ruby
def self.date_buckets_for(user, field:)
  pluck(field)
    .filter_map { |timestamp| timestamp&.strftime("%Y-%m") }
    .uniq
    .first(24)
end
```

### 2.4 Patterns to Avoid

**❌ MySQL-Specific Functions**

```ruby
# Bad: DATE_FORMAT is MySQL-only
month_sql = "DATE_FORMAT(created_at, '%Y-%m')"

# PostgreSQL equivalent: TO_CHAR(created_at, 'YYYY-MM')
# Better: Process in Ruby (see above)
```

**❌ Database-Specific Syntax**

```ruby
# Bad: MySQL's IFNULL
where("IFNULL(deleted_at, NOW()) > ?", 1.day.ago)

# Good: Standard COALESCE
where("COALESCE(deleted_at, CURRENT_TIMESTAMP) > ?", 1.day.ago)
```

**❌ String Concatenation Operators**

```ruby
# Bad: MySQL uses CONCAT(), PostgreSQL uses ||
select("CONCAT(first_name, ' ', last_name) AS full_name")

# Good: Use Ruby
def full_name
  "#{first_name} #{last_name}"
end
```

---

## 3. The Migration Process

### 3.1 Pre-Migration Audit

Before touching any configuration, we audited the entire codebase:

```bash
# Find MySQL-specific SQL
grep -r "DATE_FORMAT\|GROUP_CONCAT\|IFNULL\|BINARY\s" app/

# Find raw SQL that might be problematic
grep -r "\.where.*Arel\.sql\|execute\|connection\." app/

# Check for MySQL gem references
grep -r "mysql" Gemfile config/
```

**Our findings:**

| Issue | Location | Fix |
|-------|----------|-----|
| `DATE_FORMAT` | `app/models/access_request.rb` | Rewrote using Ruby |
| `mysql2` gem | `Gemfile` | Replaced with `pg` |
| MySQL config | `config/database.yml` | Rewrote for PostgreSQL |
| Docker MySQL | `docker-compose.dev.yml` | Replaced with PostgreSQL |

### 3.2 The Critical Fix

The only code change required was in `access_request.rb`:

```ruby
# Before: MySQL-specific
def self.date_buckets_for(user, field:)
  column = field.to_s
  qcol = connection.quote_column_name(column)
  month_sql = "DATE_FORMAT(#{qcol}, '%Y-%m')"  # ❌ MySQL-only

  for_user(user)
    .group(Arel.sql(month_sql))
    .pluck(Arel.sql(month_sql))
end

# After: Database-agnostic Ruby
def self.date_buckets_for(user, field:)
  column = field.to_s
  return [] unless DATE_BUCKET_FIELDS.include?(column)

  for_user(user)
    .where.not(column => nil)
    .order(column => :desc)
    .limit(500)
    .pluck(column)
    .filter_map { |timestamp| timestamp&.strftime("%Y-%m") }
    .uniq
    .first(24)
    .filter_map do |month|
      start_at = Time.zone.parse("#{month}-01")
      next unless start_at

      {
        id: month,
        name: start_at.strftime("%B %Y"),
        from: start_at.beginning_of_month.beginning_of_day.iso8601,
        to: start_at.end_of_month.end_of_day.iso8601
      }
    end
end
```

### 3.3 Configuration Changes

**Gemfile:**

```ruby
# Remove
gem 'mysql2', '~> 0.5.6'

# Add
gem 'pg', '~> 1.5'
```

**config/database.yml:**

```yaml
default: &default
  adapter: postgresql
  encoding: unicode
  pool: <%= ENV.fetch("RAILS_MAX_THREADS", 5) %>
  username: <%= ENV.fetch("POSTGRES_USER", "postgres") %>
  password: <%= ENV.fetch("POSTGRES_PASSWORD", "") %>
  host: <%= ENV.fetch("POSTGRES_HOST", "127.0.0.1") %>
  port: <%= ENV.fetch("POSTGRES_PORT", 5432) %>

development:
  <<: *default
  database: wigiwork_development

test:
  <<: *default
  database: wigiwork_test

production:
  <<: *default
  database: <%= ENV["POSTGRES_DB"] %>
```

**docker-compose.dev.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_DB: wigiwork_development
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### 3.4 JSON to JSONB Migration

MySQL's `JSON` type works, but PostgreSQL's `JSONB` is superior:

```ruby
# In migration files, change:
t.json :metadata

# To:
t.jsonb :metadata, default: {}
```

**Why JSONB?**

| Feature | JSON | JSONB |
|---------|------|-------|
| Storage | Text (parsed each query) | Binary (pre-parsed) |
| Indexing | ❌ Not supported | ✅ GIN indexes |
| Operators | Basic | Rich (`@>`, `?`, `?|`, `?&`) |
| Query speed | Slower | Faster |
| Write speed | Faster | Slightly slower |

**JSONB Query Examples:**

```ruby
# Find profiles with specific skill in JSONB array
Profile.where("skills @> ?", ['ruby'].to_json)

# Find users with specific setting
User.where("settings -> 'notifications' ->> 'email' = ?", 'true')

# Check if key exists
Product.where("metadata ? 'featured'")
```

### 3.5 Running the Migration

```bash
# 1. Update gems
bundle install

# 2. Create databases
rails db:create

# 3. Run migrations
rails db:migrate

# 4. Verify schema
rails db:schema:dump

# 5. Run test suite
bundle exec rspec

# 6. Seed development data
rails db:seed
```

**Total downtime: Zero** (for development). Production required a maintenance window for data migration.

---

## 4. PostgreSQL vs MySQL: A Technical Comparison

### 4.1 Feature Comparison

| Feature | MySQL | PostgreSQL |
|---------|-------|------------|
| **JSON Support** | JSON type, basic functions | JSONB with GIN indexes, rich operators |
| **Full-Text Search** | FULLTEXT indexes | tsvector/tsquery, ranking, dictionaries |
| **Geospatial** | Basic spatial | PostGIS (industry standard) |
| **Vector Search** | ❌ None | pgvector extension |
| **Graph Queries** | ❌ None | pgRouting, Apache AGE |
| **Arrays** | ❌ None | Native array types with operators |
| **Range Types** | ❌ None | int4range, daterange, etc. |
| **Check Constraints** | ✅ Supported | ✅ Supported |
| **Partial Indexes** | ❌ None | ✅ Supported |
| **Expression Indexes** | ❌ Limited | ✅ Full support |
| **CTEs (WITH queries)** | ✅ Basic | ✅ Recursive, materialized |
| **Window Functions** | ✅ Supported | ✅ More advanced |
| **UPSERT** | `ON DUPLICATE KEY` | `ON CONFLICT` (more flexible) |
| **Transactions** | ✅ InnoDB | ✅ MVCC |
| **Replication** | ✅ Built-in | ✅ Streaming, logical |

### 4.2 Performance Characteristics

**MySQL Strengths:**
- Simple read-heavy workloads
- Large-scale web applications with basic queries
- When you need maximum reads/second on simple queries

**PostgreSQL Strengths:**
- Complex queries with many joins
- Write-heavy workloads (better MVCC)
- Data integrity (stricter by default)
- Advanced data types and indexing

### 4.3 Why PostgreSQL Won for Us

**1. One Database for Everything**

Instead of:
```
MySQL (primary data)
  + Pinecone (vector search)
  + Neo4j (graph queries)
  + Elasticsearch (full-text)
```

We have:
```
PostgreSQL
  + pgvector (vector search)
  + pgRouting (graph queries)
  + Built-in full-text search
```

**2. Better Data Integrity**

```sql
-- PostgreSQL: Strict by default
INSERT INTO users (email) VALUES ('not-an-email');
-- ERROR: violates check constraint

-- MySQL: Often silently truncates or converts
INSERT INTO users (name) VALUES ('this string is way too long for the column');
-- Silently truncated (depending on sql_mode)
```

**3. Superior Indexing**

```ruby
# Partial index: Only index active users
add_index :users, :email, where: "status = 'active'"

# Expression index: Index lowercased emails
add_index :users, "LOWER(email)"

# GIN index on JSONB for fast JSON queries
add_index :profiles, :skills, using: :gin
```

**4. Native Array Support**

```ruby
# PostgreSQL array columns
t.string :tags, array: true, default: []

# Query arrays
Profile.where("'ruby' = ANY(tags)")
Profile.where("tags @> ARRAY[?]", ['ruby', 'rails'])
```

---

## 5. Advanced PostgreSQL Features

### 5.1 pgvector: AI Vector Embeddings

Store and query vector embeddings directly in PostgreSQL:

```ruby
# Enable extension
class EnablePgvector < ActiveRecord::Migration[8.0]
  def change
    enable_extension 'vector'
  end
end

# Add vector column
class AddEmbeddingToProfiles < ActiveRecord::Migration[8.0]
  def change
    add_column :profiles, :embedding, :vector, limit: 1536  # OpenAI dimension
    add_index :profiles, :embedding, using: :ivfflat, opclass: :vector_cosine_ops
  end
end
```

```ruby
# app/models/profile.rb
class Profile < ApplicationRecord
  def self.similar_to(embedding, limit: 10)
    where.not(embedding: nil)
      .order(Arel.sql("embedding <=> '#{embedding}'"))
      .limit(limit)
  end
end

# Usage
similar_profiles = Profile.similar_to(openai_embedding, limit: 5)
```

### 5.2 PostGIS: Geospatial Queries

```ruby
# Enable extension
enable_extension 'postgis'

# Add geography column
add_column :locations, :coordinates, :st_point, geographic: true
add_index :locations, :coordinates, using: :gist
```

```ruby
# Find locations within 10km
Location.where(
  "ST_DWithin(coordinates, ST_MakePoint(?, ?)::geography, ?)",
  longitude, latitude, 10_000  # meters
)
```

### 5.3 pgRouting: Graph Algorithms

```ruby
# Find shortest path between locations
execute <<-SQL
  SELECT * FROM pgr_dijkstra(
    'SELECT id, source, target, cost FROM edges',
    #{start_node},
    #{end_node},
    directed := true
  )
SQL
```

### 5.4 Full-Text Search

```ruby
# Add tsvector column
add_column :articles, :searchable, :tsvector
add_index :articles, :searchable, using: :gin

# Keep it updated with a trigger
execute <<-SQL
  CREATE TRIGGER articles_searchable_update
  BEFORE INSERT OR UPDATE ON articles
  FOR EACH ROW EXECUTE FUNCTION
  tsvector_update_trigger(searchable, 'pg_catalog.english', title, body);
SQL
```

```ruby
# Search with ranking
Article.where("searchable @@ plainto_tsquery('english', ?)", query)
       .order(Arel.sql("ts_rank(searchable, plainto_tsquery('english', '#{query}')) DESC"))
```

---

## 6. Multi-Schema Architecture

### 6.1 What Are PostgreSQL Schemas?

PostgreSQL schemas are **namespaces within a single database**. Think of them as folders for your tables:

```
database: wigiwork_production
├── public (default schema)
│   ├── users
│   ├── profiles
│   └── companies
├── analytics
│   ├── events
│   ├── page_views
│   └── conversions
├── audit
│   ├── user_actions
│   └── api_requests
└── cache
    ├── cached_profiles
    └── cached_searches
```

### 6.2 Benefits of Multi-Schema Architecture

**1. Logical Separation Without Multiple Databases**

```ruby
# One connection pool, multiple schemas
class AnalyticsEvent < ApplicationRecord
  self.table_name = 'analytics.events'
end

class AuditLog < ApplicationRecord
  self.table_name = 'audit.user_actions'
end
```

**2. Different Permissions Per Schema**

```sql
-- Analytics team can only access analytics schema
GRANT USAGE ON SCHEMA analytics TO analytics_role;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_role;

-- No access to public schema
REVOKE ALL ON SCHEMA public FROM analytics_role;
```

**3. Simplified Backup Strategies**

```bash
# Backup only the audit schema
pg_dump -n audit wigiwork_production > audit_backup.sql

# Backup everything except cache
pg_dump -N cache wigiwork_production > production_backup.sql
```

**4. Schema-Level Maintenance**

```sql
-- Truncate all cache tables without affecting production
TRUNCATE TABLE cache.cached_profiles, cache.cached_searches;

-- Drop and recreate analytics schema
DROP SCHEMA analytics CASCADE;
CREATE SCHEMA analytics;
```

### 6.3 Setting Up Multi-Schema in Rails

**Migration to create schemas:**

```ruby
class CreateAnalyticsSchema < ActiveRecord::Migration[8.0]
  def up
    execute "CREATE SCHEMA IF NOT EXISTS analytics"
    execute "CREATE SCHEMA IF NOT EXISTS audit"
    execute "CREATE SCHEMA IF NOT EXISTS cache"
  end

  def down
    execute "DROP SCHEMA IF EXISTS cache CASCADE"
    execute "DROP SCHEMA IF EXISTS audit CASCADE"
    execute "DROP SCHEMA IF EXISTS analytics CASCADE"
  end
end
```

**Models with schema prefixes:**

```ruby
# app/models/analytics/event.rb
module Analytics
  class Event < ApplicationRecord
    self.table_name = 'analytics.events'
  end
end

# app/models/audit/user_action.rb
module Audit
  class UserAction < ApplicationRecord
    self.table_name = 'audit.user_actions'
  end
end
```

**Cross-schema queries work seamlessly:**

```ruby
# Join across schemas
User.joins("JOIN audit.user_actions ON audit.user_actions.user_id = users.id")
    .where("audit.user_actions.action = ?", "login")
```

### 6.4 Schemas vs. Multiple Databases

| Aspect | Multiple Databases | Multiple Schemas |
|--------|-------------------|------------------|
| **Connection pools** | Separate per DB | Shared |
| **Cross-queries** | Complex/impossible | Native JOINs |
| **Transactions** | Distributed (2PC) | Single transaction |
| **Backups** | Per database | Per schema or together |
| **Permissions** | Database-level | Schema-level (granular) |
| **Migrations** | Separate per DB | Single migration |
| **Complexity** | Higher | Lower |
| **Rails support** | Multiple configs | Single config |

**Our recommendation:** Use schemas for logical separation within the same application. Use separate databases only for truly isolated services or multi-tenant SaaS.

### 6.5 When to Use Each Pattern

**Use Multiple Schemas When:**
- Separating concerns (analytics, audit, cache)
- Different retention policies per data type
- Granular permission control needed
- Data is related and needs cross-queries

**Use Multiple Databases When:**
- Complete data isolation required (multi-tenant)
- Different scaling requirements
- Regulatory compliance requires separation
- Microservices with independent lifecycles

---

## 7. Migration Tips and Lessons Learned

### 7.1 Before You Start

**1. Audit your codebase thoroughly**

```bash
# Find all raw SQL
grep -rn "execute\|\.sql\|Arel\.sql" app/ --include="*.rb"

# Find MySQL-specific functions
grep -rn "DATE_FORMAT\|IFNULL\|GROUP_CONCAT\|BINARY\|STRAIGHT_JOIN" app/

# Check gems for MySQL dependencies
bundle exec gem dependency mysql2
```

**2. Run tests on PostgreSQL locally first**

```yaml
# config/database.yml for CI
test:
  adapter: postgresql
  database: myapp_test
```

**3. Document all discrepancies**

Create a migration checklist (like our `mysql_to_postgresql.md`) tracking every issue found.

### 7.2 Data Migration Strategies

**Option A: Fresh Start (Recommended for Development)**

```bash
# On PostgreSQL
rails db:create db:migrate db:seed
```

**Option B: pgloader (For Production Data)**

```bash
# Install pgloader
brew install pgloader  # or apt-get

# Create migration script
cat > migrate.load << 'EOF'
LOAD DATABASE
  FROM mysql://root:password@localhost/myapp_production
  INTO postgresql://postgres@localhost/myapp_production

WITH include drop, create tables, create indexes, reset sequences

SET work_mem to '16MB', maintenance_work_mem to '512 MB'

CAST type datetime to timestamptz using zero-dates-to-null,
     type date to date using zero-dates-to-null

ALTER SCHEMA 'myapp_production' RENAME TO 'public';
EOF

# Run migration
pgloader migrate.load
```

**Option C: Rails-Native Export/Import**

```ruby
# Export from MySQL
namespace :export do
  task users: :environment do
    File.open('users.json', 'w') do |f|
      User.find_each { |u| f.puts u.to_json }
    end
  end
end

# Import to PostgreSQL
namespace :import do
  task users: :environment do
    File.readlines('users.json').each do |line|
      User.create!(JSON.parse(line))
    end
  end
end
```

### 7.3 Common Gotchas

**1. Auto-increment vs. SERIAL**

MySQL uses `AUTO_INCREMENT`, PostgreSQL uses `SERIAL` or `IDENTITY`. Rails handles this automatically, but check sequences after migration:

```sql
-- Fix sequence if IDs are out of sync
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
```

**2. Boolean Handling**

MySQL often stores booleans as `TINYINT(1)`. PostgreSQL uses native `BOOLEAN`:

```ruby
# May need explicit casting in raw SQL
where("active = true")  # PostgreSQL
where("active = 1")     # MySQL
```

**3. Case Sensitivity**

PostgreSQL string comparisons are case-sensitive by default:

```ruby
# MySQL: case-insensitive by default
User.where(email: 'Test@Example.com')  # Finds test@example.com

# PostgreSQL: case-sensitive
User.where("LOWER(email) = LOWER(?)", 'Test@Example.com')
# Or use citext extension for case-insensitive columns
```

**4. Group By Strictness**

PostgreSQL requires all non-aggregated columns in GROUP BY:

```ruby
# MySQL: Allows this (picks arbitrary value)
select("users.*, COUNT(orders.id)")
  .joins(:orders)
  .group("users.id")

# PostgreSQL: Must include all selected columns
select("users.id, users.email, COUNT(orders.id)")
  .joins(:orders)
  .group("users.id, users.email")
```

### 7.4 Post-Migration Checklist

```bash
# 1. Verify all tests pass
bundle exec rspec

# 2. Check for deprecation warnings
RAILS_ENV=test rails runner "puts ActiveRecord::Base.connection.adapter_name"

# 3. Regenerate schema
rails db:schema:dump

# 4. Verify schema.rb has PostgreSQL syntax
grep "create_table" db/schema.rb | head

# 5. Run security scan
bundle exec brakeman -q -w2

# 6. Regenerate API documentation
bundle exec rails rswag:specs:swaggerize

# 7. Performance baseline
rails runner "Benchmark.measure { User.count }"
```

### 7.5 Lessons We Learned

**1. Write database-agnostic code from day one**

The single MySQL-specific function we had took 30 minutes to rewrite. If we'd had dozens, it would have been a multi-day effort.

**2. Use JSONB defaults in migrations**

```ruby
# Always specify defaults for JSONB
t.jsonb :settings, default: {}
t.jsonb :tags, default: []
```

**3. Leverage PostgreSQL-specific features gradually**

Don't rewrite everything immediately. Start with:
- JSONB for new features
- Partial indexes for performance
- Full-text search when needed

**4. Monitor query performance post-migration**

PostgreSQL's query planner is different. Some queries may need new indexes:

```ruby
# Add explain logging in development
ActiveRecord::Base.logger = Logger.new(STDOUT)
User.where(status: :active).explain
```

**5. Document your extensions**

```ruby
# db/migrate/001_enable_extensions.rb
class EnableExtensions < ActiveRecord::Migration[8.0]
  def change
    # Core extensions we use
    enable_extension 'pgcrypto'  # UUID generation
    enable_extension 'citext'    # Case-insensitive text

    # Feature-specific (enable when needed)
    # enable_extension 'vector'   # AI embeddings
    # enable_extension 'postgis'  # Geospatial
  end
end
```

---

## Conclusion

Migrating from MySQL to PostgreSQL doesn't have to be painful. With database-agnostic code patterns and a systematic approach, our migration required:

- **1 code fix** (DATE_FORMAT → Ruby)
- **4 configuration file updates**
- **0 model changes** (beyond JSON → JSONB)
- **0 downtime** (for development)

The benefits far outweigh the effort:

| Before (MySQL + Services) | After (PostgreSQL) |
|---------------------------|-------------------|
| 3+ external services | 1 database |
| Multiple connection pools | Single pool |
| Cross-service latency | Native queries |
| Complex sync logic | Referential integrity |
| Higher infrastructure cost | Lower cost |

PostgreSQL isn't just a MySQL replacement—it's a **platform for building sophisticated applications**. With extensions like pgvector, PostGIS, and pgRouting, you can consolidate your entire data layer into a single, powerful database.

### Key Takeaways

1. **Write database-agnostic code** — Use ActiveRecord/Arel, avoid raw SQL functions
2. **Audit before migrating** — Find MySQL-specific code early
3. **Use JSONB over JSON** — Better indexing, better queries
4. **Consider schemas over databases** — Simpler architecture, better performance
5. **Leverage PostgreSQL features** — Partial indexes, arrays, full-text search
6. **Plan for extensions** — pgvector, PostGIS, pgRouting when needed
7. **Test thoroughly** — Run your full suite on PostgreSQL before production

The best database is the one that grows with your needs. PostgreSQL does exactly that.

---

## Resources

- **PostgreSQL Official Docs**: [postgresql.org/docs](https://www.postgresql.org/docs/)
- **pgvector Extension**: [github.com/pgvector/pgvector](https://github.com/pgvector/pgvector)
- **PostGIS Documentation**: [postgis.net/docs](https://postgis.net/docs/)
- **pgRouting Documentation**: [pgrouting.org](https://pgrouting.org/)
- **Rails PostgreSQL Guide**: [guides.rubyonrails.org/active_record_postgresql.html](https://guides.rubyonrails.org/active_record_postgresql.html)
- **pgloader**: [pgloader.io](https://pgloader.io/)

---

*This post documents our migration of the Wigiwork API from MySQL to PostgreSQL. The patterns described here enabled a migration with minimal code changes and zero regressions—proving that investment in database-agnostic code pays dividends when requirements evolve.*

