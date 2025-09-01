---
layout: post
title: ACID in Rails PostgreSQL vs MongoDB - with Atomic Patterns
author: Max Lukin
categories: rails databases transactions atomicity acid
date: 2025-09-01 09:00:00
tags: [rails-8, database]
categories: rails patterns acis
excerpt: ACID in Rails PostgreSQL vs MongoDB with Atomic Patterns
---

# ACID in Rails: PostgreSQL vs MongoDB (with Atomic Patterns)

As a Rails engineer, you often hear about **ACID** compliance in
databases. But how does it actually apply when building endpoints with
**PostgreSQL** (the Rails default) versus **MongoDB**? Let's break it
down with clear examples.

------------------------------------------------------------------------

## 1. What is ACID?

**ACID** stands for:

1.  **Atomicity** -- all-or-nothing transactions.
2.  **Consistency** -- data moves only between valid states.
3.  **Isolation** -- transactions behave as if running alone.
4.  **Durability** -- committed data survives crashes.

------------------------------------------------------------------------

## 2. PostgreSQL in Rails (ActiveRecord)

PostgreSQL is **fully ACID-compliant**.

### ✅ Atomic User + Profile Creation

``` ruby
ActiveRecord::Base.transaction do
  user    = User.create!(email: "a@b.com")
  profile = Profile.create!(user: user, name: "Max")
end
```

### ✅ Atomic Money Transfer with Locks

``` ruby
class Payments::TransferFunds
  def self.call(from_id:, to_id:, amount_cents:)
    ActiveRecord::Base.transaction do
      from = Account.lock.find(from_id)
      to   = Account.lock.find(to_id)

      raise "Insufficient funds" if from.balance_cents < amount_cents

      from.balance_cents -= amount_cents
      to.balance_cents   += amount_cents

      from.save!
      to.save!
    end
  end
end
```

### ✅ Side Effects After Commit

``` ruby
class User < ApplicationRecord
  after_commit :enqueue_welcome_email, on: :create

  def enqueue_welcome_email
    SendWelcomeEmailJob.perform_later(id)
  end
end
```

------------------------------------------------------------------------

## 3. MongoDB in Rails (Mongoid)

MongoDB is **not fully ACID**. By default:

-   Atomicity is guaranteed **per document**.
-   Multi-document transactions exist (since v4.0) but add overhead.

### ✅ Multi-Document Transaction (User + Profile)

``` ruby
Mongoid::Clients.default.with(write: { w: :majority }) do |client|
  session = client.start_session
  session.with_transaction do
    user    = User.with(session: session).create!(email: "a@b.com")
    profile = Profile.with(session: session).create!(user_id: user.id, name: "Max")
  end
end
```

### ✅ Atomic Inventory Decrement (`$inc`)

``` ruby
Product.where(id: product_id, :stock.gte => 1)
       .find_one_and_update(
         { '$inc' => { stock: -1 } },
         return_document: :after
       )
```

### ✅ Multi-Document Money Transfer

``` ruby
session.with_transaction do
  from = Account.with(session: session).find(from_id)
  to   = Account.with(session: session).find(to_id)

  raise "Insufficient funds" if from.balance_cents < amount_cents

  from.inc(balance_cents: -amount_cents)
  to.inc(balance_cents: amount_cents)
end
```

------------------------------------------------------------------------

## 4. What Must Be Atomic?

**Should be atomic:** - Creating related records (User + Profile) -
Money transfers - Inventory decrements - State transitions with
invariants

**Doesn't need atomicity:** - Logging/analytics - Emails/notifications -
Background jobs - Cache writes

------------------------------------------------------------------------

## 5. Quick Checklist

-   ✅ Wrap multi-record writes in `transaction` (Postgres).
-   ✅ Use row locks for contested records (balances, seats).
-   ✅ Enforce consistency with DB constraints + Rails validations.
-   ✅ In MongoDB, prefer single-document atomic ops (`$inc`).
-   ✅ For multi-doc writes in MongoDB, use transactions
    (`w: :majority`).
-   ✅ Push side-effects (`emails`, `logs`) to `after_commit` or jobs.
-   ✅ Keep transactions short; lock rows in consistent order.

------------------------------------------------------------------------

## 6. Final Thoughts

-   **PostgreSQL** is ACID by design --- perfect for transactional
    business logic.
-   **MongoDB** is atomic per document; use transactions only where
    needed.
-   In Rails, **make critical paths atomic, and decouple side-effects**.

With these patterns, you'll avoid data corruption and keep your Rails
apps both reliable and scalable.
