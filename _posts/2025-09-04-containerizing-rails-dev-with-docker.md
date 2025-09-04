---
layout: post
title: "Containerizing Your Rails Development with Docker + Dev Containers"
author: Max Lukin
categories: rails docker devcontainers
date: 2025-09-04 09:00:00
tags: [docker, devcontainers, rails, mysql, redis, dotenv, bundler]
excerpt: Zero-setup onboarding, reproducible environments, and fewer 'works on my machine' moments.
---

> **TL;DR**
> Containerizing your Rails dev environment with Docker (and VS Code Dev Containers) gives every engineer a fast, identical setup: **Ruby + Bundler + MySQL + Redis** with one click. No more per‑machine MySQL installs, version drift, or “it works on my laptop.”

- **Repo paths used below**
  - `/.devcontainer/Dockerfile` – dev-only image
  - `/docker-compose.dev.yml` – dev stack (app, MySQL, Redis)
  - `/config/database.yml` – uses env vars (host, port, creds)
  - `/.env.example` → copied to `.env` on first boot
  - `/bin/setup` – idempotent bootstrap (optional but recommended)

---

## Why containerize local development?

| Benefit | Why it matters | Trade‑off |
|---|---|---|
| **Instant onboarding** | New devs open the repo and everything “just runs.” | Slightly larger first build; Docker Desktop required. |
| **Reproducible environments** | Everyone shares the same Ruby, MySQL, Redis, OS libs. | You maintain Dockerfiles/Compose. |
| **Isolation** | No conflicts with system MySQL/Redis or multiple projects. | File I/O can be slower than native (especially on macOS). |
| **Parity with CI/Prod** | Same images/services you ship are used in dev. | Can tempt you to over‑optimize images early. |
| **Easy cleanup** | `docker compose down -v` wipes everything clean. | You must understand volumes vs. containers. |

---

## The dev stack

### 1) Dev-only Dockerfile — `/.devcontainer/Dockerfile`

This keeps dev gems, installs to `/usr/local/bundle`, and doesn’t assume production secrets.

```dockerfile
# .devcontainer/Dockerfile
FROM ruby:3.4.4-slim

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8     BUNDLE_PATH=/usr/local/bundle BUNDLE_JOBS=4 BUNDLE_RETRY=3

RUN apt-get update -qq && apt-get install --no-install-recommends -y       ca-certificates curl bash tzdata libjemalloc2 libvips       default-mysql-client libmariadb3 build-essential git libpq-dev       libyaml-dev pkg-config default-libmysqlclient-dev     && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives

# Optional jemalloc preload
RUN echo "/usr/lib/$(uname -m)-linux-gnu/libjemalloc.so.2" > /etc/ld.so.preload || true

WORKDIR /workspaces/app

# Install Bundler matching Gemfile.lock if present
COPY Gemfile Gemfile.lock ./
RUN set -eux;   if grep -q "BUNDLED WITH" Gemfile.lock; then     v="$(awk '/BUNDLED WITH/{getline; gsub(/^ +/,""); print}' Gemfile.lock)";     gem install bundler -v "$v" --no-document;   else     gem install bundler --no-document;   fi;   bundle config unset without || true;   bundle config set path "$BUNDLE_PATH";   bundle install --jobs ${BUNDLE_JOBS} --retry ${BUNDLE_RETRY} || true

# App code
COPY . .

# Helpful default command for dev containers
CMD bash -lc 'bundle exec rails db:prepare && bundle exec rails s -b 0.0.0.0 -p 3000'
```

> **Why a dev‑only Dockerfile?**
> Your production Dockerfile often excludes `development/test` gems, precompiles assets, and assumes secrets. The dev image should keep **dev gems** (e.g., `debug`) and run comfortably without prod secrets.

---

### 2) Docker Compose for dev — `/docker-compose.dev.yml`

It wires up the Rails app, MySQL 8, and Redis 7. It also waits for MySQL to be healthy before starting Rails.

```yaml
# docker-compose.dev.yml
services:
  app:
    build:
      context: .
      dockerfile: .devcontainer/Dockerfile
    volumes:
      - .:/workspaces/app:cached
      - bundle_cache:/usr/local/bundle
    environment:
      RAILS_ENV: development

      # Match config/database.yml expectations
      MYSQL_DB_HOST: mysql
      MYSQL_DB_PORT: "3306"
      MYSQL_DB_USER: root
      MYSQL_DB_PASS: password
      MYSQL_NAME: wigiwork_development

      REDIS_URL: redis://redis:6379/0
      APP_VERSION: devcontainer
      RAILS_LOG_TO_STDOUT: "1"
    ports:
      - "${{RAILS_PORT:-3000}}:3000"
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_started
    command: >
      bash -lc "
        until mysqladmin ping -hmysql -P3306 -uroot -ppassword >/dev/null 2>&1; do
          echo 'Waiting for MySQL...'; sleep 1;
        done;
        bundle exec rails db:prepare &&
        bundle exec rails s -b 0.0.0.0 -p 3000
      "
    env_file:
      - .env

  mysql:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: wigiwork_development
    ports:
      - "3307:3306" # host:container for host access
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-ppassword"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data

volumes:
  bundle_cache:
  mysql_data:
  redis_data:
```

> **Note on volumes:** the named volume `bundle_cache` persists Bundler gems across rebuilds. If the Gemfile changes groups (e.g., dev/test) or the cache gets stale, remove it:
> `docker volume rm $(docker volume ls -q | grep bundle)` and rebuild.

---

### 3) Rails DB config — `/config/database.yml`

Use env vars and default the **host to `mysql`** (the Compose service name).

```yaml
# config/database.yml
default: &default
  adapter: mysql2
  encoding: utf8mb4
  collation: utf8mb4_0900_ai_ci
  pool: <%= ENV.fetch("RAILS_MAX_THREADS", 5) %>
  username: <%= ENV.fetch("MYSQL_DB_USER", "root") %>
  password: <%= ENV.fetch("MYSQL_DB_PASS", "password") %>
  host:     <%= ENV.fetch("MYSQL_DB_HOST", "mysql") %>
  port:     <%= ENV.fetch("MYSQL_DB_PORT", "3306") %>
  variables:
    sql_mode: STRICT_ALL_TABLES
  time_precision: 6

development:
  <<: *default
  database: <%= ENV.fetch("MYSQL_NAME", "wigiwork_development") %>

test:
  <<: *default
  database: <%= ENV.fetch("DB_DATABASE", "wigiwork_test") %>
```

> If you run Rails **from the host** against the containerized DB, use `127.0.0.1:3307` (not `mysql:3306`).
> Example: `DATABASE_URL=mysql2://root:password@127.0.0.1:3307/wigiwork_development`

---

## Commands you’ll actually use

```bash
# Validate compose (what Dev Containers runs under the hood)
docker compose -f docker-compose.dev.yml config

# Build & start everything in detached mode
docker compose -f docker-compose.dev.yml up -d --build

# Exec into the app container
docker compose -f docker-compose.dev.yml exec app bash

# Inside the container
bundle exec rails db:prepare
rails s -b 0.0.0.0 -p 3000

# Start only MySQL (handy for host Rails or GUI tools)
docker compose -f docker-compose.dev.yml up -d mysql

# Stop/start only the app
docker compose -f docker-compose.dev.yml stop app
docker compose -f docker-compose.dev.yml start app

# View status and logs
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs -f app
```

**Detached mode?** `-d` means containers run in the **background**; your terminal is free and logs aren’t attached. Use `logs -f` to tail when you need.

---

## Lessons learned (from real debugging)

- **Empty port envs → “invalid proto”**
  Always default your port mappings, e.g. `"${{RAILS_PORT:-3000}}:3000"`.

- **Environment syntax**
  In YAML map style use `KEY: value` (not `KEY=value`). This avoided errors like `could not find expected ':'`.

- **Dev gems must be installed**
  Excluding `development/test` caused `cannot load such file -- debug/prelude`. Keep dev gems in your **dev image**.

- **Dotenv 2.x vs 3.x API**
  `Dotenv.instrumenter=` was removed in 3.x. Either pin `dotenv-rails` to `~> 2.8` or remove the old API usage.

- **Bundle cache volume can shadow image gems**
  If gems seem “missing” after a rebuild, delete the bundle volume and rebuild with `--no-cache`.

- **Service discovery**
  - **Inside containers**: DB host is `mysql:3306`.
  - **From host**: DB is `127.0.0.1:3307` (published port).

- **MySQL readiness**
  Use healthchecks plus a small wait loop before starting Rails.

---

## Troubleshooting cookbook

**“invalid proto:” in compose**
→ A port mapping used an empty env var. Add defaults: `- "${{RAILS_PORT:-3000}}:3000"`.

**`cannot load such file -- debug/prelude`**
→ Dev gems weren’t installed. Don’t set `bundle config set without 'development test'` for dev images.

**`Dotenv NoMethodError: instrumenter=`**
→ You’re on dotenv 3.x but using a 2.x method. Pin to `dotenv-rails ~> 2.8` or remove that call.

**`Could not find … in locally installed gems` after rebuild**
→ Your bundle cache volume is stale. Remove it and rebuild:
`docker volume rm <bundle_volume>; docker compose build --no-cache app`.

**`Unknown MySQL server host 'mysql'` when running Rails on host**
→ From the host, use `127.0.0.1:3307`, not `mysql`.

---

## Pros & cons recap

**Pros**
- ✅ Zero‑setup onboarding; consistent environments
- ✅ Isolation from host toolchains
- ✅ CI/prod parity; easier “it fails only in prod” bugs
- ✅ Fast resets (containers/volumes are disposable)

**Cons**
- ❌ Slight perf overhead vs native (I/O heavy workloads)
- ❌ Extra YAML/Dockerfiles to maintain
- ❌ Requires Docker Desktop & familiarity with containers

---

## Final checklist

- [ ] Add `/.devcontainer/Dockerfile` and `/docker-compose.dev.yml`.
- [ ] `config/database.yml` defaults to `host: mysql`, reads envs.
- [ ] `.env.example` exists; copied to `.env` on first boot (or via `bin/setup`).
- [ ] `depends_on: condition: service_healthy` for MySQL + wait loop.
- [ ] Use `bundle exec` for Rails commands.
- [ ] Optional named volume for gems; remove it if cache causes issues.

Happy shipping — and goodbye to “works on my machine.” 🚀
