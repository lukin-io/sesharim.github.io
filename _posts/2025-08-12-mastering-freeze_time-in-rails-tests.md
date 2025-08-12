---
layout: post
title: "Mastering freeze_time in Rails Tests: Practical Patterns and Pitfalls"
date: 2025-08-12 00:01:01
author: Max Lukin
categories: rails testing time freeze_time
---

If your test suite ever fails “only sometimes,” there’s a good chance time is involved. Rails ships with the excellent `ActiveSupport::Testing::TimeHelpers`, giving you tools like `freeze_time`, `travel_to`, and `travel` to control the clock deterministically. In this post, you’ll learn when to use `freeze_time`, how it differs from `travel_to`, and a handful of real-world patterns (Rails 7/8+ friendly) you can drop straight into your specs.

---

## TL;DR

- **Use `freeze_time`** when the *current moment* shouldn’t move during a test (timestamps, cache keys, token generation).
- **Use `travel_to`** when you want the current time to be a specific instant (and keep it fixed).
- **Use `travel`** when you want to *advance/rewind* the clock relative to now.
- Prefer **`Time.current`** over `Time.now` so your tests respect Rails time zones.
- Always **`travel_back`** (or use the block form) to avoid leaking frozen time to other tests.

---

## Setup (RSpec & Minitest)

### RSpec

```ruby
# spec/rails_helper.rb
RSpec.configure do |config|
  config.include ActiveSupport::Testing::TimeHelpers

  # Optional: automatically unfreeze/travel back after each example
  config.around do |example|
    travel_back
    example.run
    travel_back
  end
end
```

You can also use block forms of `freeze_time`/`travel_to` to avoid needing `travel_back`.

### Minitest

```ruby
# test/test_helper.rb
class ActiveSupport::TestCase
  include ActiveSupport::Testing::TimeHelpers
end
```

---

## 1) Stabilize Timestamps in Model Specs

```ruby
RSpec.describe Profile, type: :model do
  it "sets deterministic timestamps" do
    freeze_time do
      profile = Profile.create!(name: "Max")
      expect(profile.created_at).to eq(Time.current)
      expect(profile.updated_at).to eq(Time.current)
    end
  end
end
```

---

## 2) Token Generation & Expiration

```ruby
RSpec.describe JwtIssuer do
  it "sets exp 15 minutes from now and expires correctly" do
    freeze_time do
      token = JwtIssuer.issue(sub: 123)
      payload = JwtIssuer.decode(token)

      expect(payload["iat"]).to eq(Time.current.to_i)
      expect(payload["exp"]).to eq(15.minutes.from_now.to_i)
    end

    travel 16.minutes
    expect { JwtIssuer.decode(token) }.to raise_error(JwtIssuer::ExpiredToken)
  ensure
    travel_back
  end
end
```

---

## 3) Cache Keys & Expirations

```ruby
RSpec.describe Profiles::CachedFinder do
  it "caches and expires as expected" do
    profile = create(:profile)

    freeze_time do
      expect { described_class.call(profile.id) }
        .to change { Rails.cache.exist?("profile:#{profile.id}:#{profile.updated_at.to_i}") }
        .from(false).to(true)
    end

    travel 1.hour
    expect(
      Rails.cache.exist?("profile:#{profile.id}:#{profile.updated_at.to_i}")
    ).to be(false)
  ensure
    travel_back
  end
end
```

---

## 4) Time-Dependent Scopes

```ruby
RSpec.describe Session, type: :model do
  it "moves from active to expired over time" do
    freeze_time do
      session = create(:session, expires_at: 10.minutes.from_now)
      expect(Session.active).to include(session)
    end

    travel 11.minutes
    expect(Session.active).to be_empty
  ensure
    travel_back
  end
end
```

---

## 5) Background Jobs

```ruby
RSpec.describe ReminderScheduler do
  include ActiveJob::TestHelper

  it "schedules a reminder exactly 24 hours before" do
    freeze_time do
      event = create(:event, starts_at: 3.days.from_now)
      expect {
        ReminderScheduler.schedule!(event)
      }.to have_enqueued_job(ReminderJob)
        .at(2.days.from_now)
        .with(event.id)
    end
  end
end
```

---

## 6) Humanized Times

```ruby
RSpec.describe ActivityPresenter do
  it "renders stable relative time" do
    freeze_time do
      activity = create(:activity, created_at: 5.minutes.ago)
      text = ActivityPresenter.new(activity).relative_created_at
      expect(text).to eq("5 minutes ago")
    end
  end
end
```

---

## 7) DST & Time Zones

```ruby
RSpec.describe "DST boundary", type: :system do
  it "shows local times correctly across DST change" do
    Time.use_zone("Europe/Kyiv") do
      freeze_time Time.zone.parse("2025-03-30 02:30") do
        visit dashboard_path
        expect(page).to have_content("02:30")
      end
    end
  end
end
```

---

## 8) Grace Periods

```ruby
RSpec.describe Orders::CancellationPolicy do
  it "rejects cancellation after 24 hours" do
    freeze_time do
      order = create(:order, created_at: Time.current)
      expect(described_class.allowed?(order)).to be(true)
    end

    travel 25.hours
    expect(described_class.allowed?(Order.last)).to be(false)
  ensure
    travel_back
  end
end
```

---

## 9) Deterministic Factories

```ruby
RSpec.describe AttachmentBlueprint do
  it "serializes with fixed timestamps" do
    freeze_time do
      attachment = create(:attachment, :with_file)
      json = AttachmentBlueprint.render_as_hash(attachment)
      expect(json[:created_at]).to eq(Time.current.iso8601)
      expect(json[:updated_at]).to eq(Time.current.iso8601)
    end
  end
end
```

---

## freeze_time vs travel_to vs travel

- **`freeze_time`** – Freeze the current time and keep it from moving.
- **`travel_to(time)`** – Set the current time to a specific instant.
- **`travel(duration)`** – Move the clock forward/back.

---

## Pitfalls

1. Use `Time.current` instead of `Time.now`.
2. DB-side NOW() is not affected by Ruby helpers.
3. Always `travel_back` if not using block form.
4. Watch out for libs reading OS time.
5. Be careful with DST.

---

## Final Thoughts

`freeze_time` reduces flakiness, makes assertions crisp, and keeps tests fast. If your tests depend on the current moment, wrap them in `freeze_time` and combine with `travel` for simulating time passage.

Happy testing!
