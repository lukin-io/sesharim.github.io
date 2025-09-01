---
layout: post
author: Max Lukin
title: A tiny Rails console banner that show app stats every time you run rails c
date: 2025-08-25 09:00:00
tags: [rails-8, console]
categories: rails performance api optimization blueprinter ransack caching
excerpt: A tiny Rails console banner that show app stats every time you run rails c
---

> Quick win for everyday Rails work: print a small, colorized stats banner **every time** you open `rails console` — users, companies, profiles, attachments, etc. It’s zero‑maintenance and runs only in the console.

## TL;DR / Roadmap
1. **Pick one approach**:
   - **Option A — Initializer (console‑only)**: `config/initializers/console_banner.rb`
   - **Option B — Console hook (bulletproof)**: `config/console_banner.rb` + a small addition in `config/application.rb`
2. Run `rails c` and enjoy the banner.
3. If you use **Spring**, run `bin/spring stop` once (or `DISABLE_SPRING=1 rails c`) if you don’t see it the first time.
4. Optional: colorize, add DB/Redis checks, or timing per query.

---

## Why this exists
When I open the console, I want context fast: *how many users are in the DB? which environment am I in? what database am I connected to?*
A tiny banner answers those in ~1ms of code you’ll forget about.

---

## Option A — Initializer that runs only in the console
Create **`config/initializers/console_banner.rb`**:
```ruby
# config/initializers/console_banner.rb
# Prints a banner when you start `rails console` (and only then).

if defined?(Rails::Console)
  Rails.application.config.after_initialize do
    begin
      # Ensure DB is reachable
      ActiveRecord::Base.connection

      models = {
        "Users"          => User,
        "Companies"      => (defined?(Company) ? Company : nil),
        "Profiles"       => (defined?(Profile) ? Profile : nil),
        "Resumes"        => (defined?(Resume) ? Resume : nil),
        "Attachments"    => (defined?(ActiveStorage::Attachment) ? ActiveStorage::Attachment : nil),
        "AccessRequests" => (defined?(AccessRequest) ? AccessRequest : nil)
      }.compact

      width = models.keys.map(&:length).max
      puts "\n\e[1m--- Application Stats ---\e[0m"
      models.each do |label, klass|
        count = begin
          klass.count
        rescue StandardError
          "N/A"
        end
        color = (count.is_a?(Integer) && count.zero?) ? 31 : 32 # red if 0, green otherwise
        printf "Total %-#{width}s: \e[#{color}m%s\e[0m\n", label, count
      end

      db_name = ActiveRecord::Base.connection_db_config.database rescue "unknown"
      puts "Environment: #{Rails.env} | DB: #{db_name}"
      puts "---------------------------\n\n"
    rescue StandardError => e
      warn "[console banner] skipped: #{e.class}: #{e.message}"
    end
  end
end
```

**Pros:** minimal code, works in most setups.
**Cons:** very rare boot orders may skip it; see Option B if that happens.

---

## Option B — Console hook (bulletproof)
1) Create **`config/console_banner.rb`**:
```ruby
# config/console_banner.rb
module ConsoleBanner
  def self.print!
    ActiveRecord::Base.connection

    models = {
      "Users"          => User,
      "Companies"      => (defined?(Company) ? Company : nil),
      "Profiles"       => (defined?(Profile) ? Profile : nil),
      "Resumes"        => (defined?(Resume) ? Resume : nil),
      "Attachments"    => (defined?(ActiveStorage::Attachment) ? ActiveStorage::Attachment : nil),
      "AccessRequests" => (defined?(AccessRequest) ? AccessRequest : nil)
    }.compact

    width = models.keys.map(&:length).max
    puts "\n\e[1m--- Application Stats ---\e[0m"
    models.each do |label, klass|
      count = klass.count rescue "N/A"
      color = (count.is_a?(Integer) && count.zero?) ? 31 : 32
      printf "Total %-#{width}s: \e[#{color}m%s\e[0m\n", label, count
    end

    db_name = ActiveRecord::Base.connection_db_config.database rescue "unknown"
    puts "Environment: #{Rails.env} | DB: #{db_name}"
    puts "---------------------------\n\n"
  rescue StandardError => e
    warn "[console banner] skipped: #{e.class}: #{e.message}"
  end
end

ConsoleBanner.print!
```

2) Register it in **`config/application.rb`** (inside `class Application < Rails::Application`):
```ruby
# config/application.rb
module YourApp
  class Application < Rails::Application
    # ... other config

    console do
      require Rails.root.join("config/console_banner")
    end
  end
end
```

**Pros:** guaranteed to run **only** in console and always load.
**Cons:** two small files instead of one.

---

## Example: What it looks like

```
rails c

--- Application Stats ---
  User Count (19.0ms)  SELECT COUNT(*) FROM `users` /*application='WigiworkBack'*/
Total Users         : 53
  Company Count (3.2ms)  SELECT COUNT(*) FROM `companies` /*application='WigiworkBack'*/
Total Companies     : 2
  Profile Count (0.3ms)  SELECT COUNT(*) FROM `profiles` /*application='WigiworkBack'*/
Total Profiles      : 52
  Resume Count (0.2ms)  SELECT COUNT(*) FROM `resumes` /*application='WigiworkBack'*/
Total Resumes       : 37
  ActiveStorage::Attachment Count (0.3ms)  SELECT COUNT(*) FROM `active_storage_attachments` /*application='WigiworkBack'*/
Total Attachments   : 0
  AccessRequest Count (0.2ms)  SELECT COUNT(*) FROM `access_requests` /*application='WigiworkBack'*/
Total AccessRequests: 4
Environment: development | DB: wigiwork_development
---------------------------

Loading development environment (Rails 8.0.2)
3.4.4 :001 >
```

> Note: The SQL lines appear if you have SQL logging enabled (default in development). The “green/red” colorization shown in the code depends on whether the count is zero.

---

## Troubleshooting
- **Nothing prints?**
  - Stop Spring: `bin/spring stop`, then `rails c`.
  - Try **Option B** so the code is wired via the `console` hook.
- **Errors about constant not defined?**
  - Wrap optional models with `defined?(Model) ? Model : nil` (already done above).
- **Production console**
  - This also runs in production console; that’s usually fine. If you want it dev‑only, guard with `if Rails.env.development?`.

---

## Optional enhancements
- **Timing per query:** wrap `klass.count` in a small timer and print duration.
- **Health checks:** ping Redis or Sidekiq before printing.
- **More models:** add whatever gives you signal (e.g., `MessageThread`, `JobTitle`, etc.).

---

## How you’ll use it (nothing fancy)
```bash
bin/rails console
# or just
rails c
```

---

## Steps checklist
- [ ] Choose **Option A** (initializer) or **Option B** (console hook).
- [ ] Create the files at the exact paths above.
- [ ] (If using Spring) run `bin/spring stop` once.
- [ ] `rails c` → confirm the banner displays.
- [ ] Extend with timers / health checks as needed.
