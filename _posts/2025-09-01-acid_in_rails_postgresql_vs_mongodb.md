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

# ACID, Atomicity, and Rails Patterns: PostgreSQL vs MongoDB

This post consolidates our full discussion about **ACID** properties,
what's atomic and what isn't, and how this applies to **Ruby on Rails**
with **PostgreSQL** and **MongoDB**. It includes explanations, Rails
best practices, anti-patterns, and corrected implementations.

------------------------------------------------------------------------

## 1. What is ACID?

**ACID** is a set of four properties that guarantee database
reliability:

1.  **Atomicity** -- A transaction is "all or nothing". Either every
    operation succeeds, or none are applied.
2.  **Consistency** -- Data must always move from one valid state to
    another. Constraints, validations, and referential integrity must
    hold true.
3.  **Isolation** -- Concurrent transactions should not interfere with
    each other. Each transaction should behave as if it's running alone.
4.  **Durability** -- Once a transaction is committed, it survives
    crashes, restarts, and power loss.

------------------------------------------------------------------------

## 2. ACID in PostgreSQL (Rails default relational DB)

PostgreSQL is **fully ACID-compliant**:

-   ✅ **Atomicity**: `ActiveRecord::Base.transaction` ensures rollback
    if any statement fails.\
-   ✅ **Consistency**: Enforced with primary keys, foreign keys, NOT
    NULL, CHECK, Rails validations, etc.\
-   ✅ **Isolation**: PostgreSQL supports multiple isolation levels
    (`READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`). Rails
    defaults to `READ COMMITTED`.\
-   ✅ **Durability**: Uses write-ahead logging (WAL). Once committed,
    data is safe.

Example in Rails:

``` ruby
ActiveRecord::Base.transaction do
  user.save!
  profile.save!
end
```

If `profile.save!` fails, `user.save!` rolls back automatically.

------------------------------------------------------------------------

## 3. ACID in MongoDB (NoSQL)

MongoDB is **not fully ACID** in the same sense as PostgreSQL:

-   ✅ **Atomicity**: Guaranteed **per single document**.\
    ❌ Multi-document atomicity is only possible with multi-document
    transactions (added in MongoDB 4.0, but with overhead).\
-   ⚠️ **Consistency**: Schema-less by default. Rails (via `mongoid`)
    must enforce validations at app level.\
-   ⚠️ **Isolation**: Document-level isolation only. If two transactions
    modify separate fields of the same document concurrently, one may
    overwrite the other without detecting conflict.\
-   ⚠️ **Durability**: Configurable via **write concerns** (`w:1`,
    `w:majority`). If not set properly, writes can be acknowledged
    before being persisted.

Rails (with Mongoid) example:

``` ruby
User.with_session do |session|
  session.start_transaction
  user.update!(name: "Max")
  profile.update!(bio: "Hello") # multi-doc transaction
  session.commit_transaction
end
```

Without a transaction, only `user.update!` might persist, breaking
atomicity.

------------------------------------------------------------------------

## 4. What Should Be **Atomic** in Rails?

Atomicity should be applied to operations where **partial success would
corrupt data integrity**:

-   ✅ **Creating related records** (e.g., `User` + `Profile`).\
-   ✅ **Money transfers / payments** (must debit & credit atomically).\
-   ✅ **Bulk inserts / updates** where all must succeed together.\
-   ✅ **Inventory changes** (e.g., decrementing stock and creating an
    order).

What doesn't need to be atomic:

-   ❌ **Read-only queries** (no state change).\
-   ❌ **Logging / analytics writes** (failure doesn't break core
    business).\
-   ❌ **Background jobs** (can retry independently).\
-   ❌ **Non-critical side effects** (sending emails, audit trails ---
    wrap in `after_commit` hooks instead).

------------------------------------------------------------------------

## 5. Rails Anti-Patterns vs Fixed Atomic Patterns

### PostgreSQL Examples

#### ❌ Bad: User + Profile creation (partial writes possible)

``` ruby
def create
  user = User.create!(email: params[:email])
  profile = Profile.create!(user: user, name: params[:name]) # may fail later
end
```

#### ✅ Fixed: Use transaction

``` ruby
ActiveRecord::Base.transaction do
  user    = User.create!(email: params[:email])
  profile = Profile.create!(user: user, name: params[:name])
end
```

------------------------------------------------------------------------

#### ❌ Bad: Money transfer without transaction

``` ruby
from.balance_cents -= amount
from.save!

to.balance_cents += amount
to.save!
```

#### ✅ Fixed: Use transaction + locks

``` ruby
ActiveRecord::Base.transaction do
  from = Account.lock.find(from_id)
  to   = Account.lock.find(to_id)

  raise "Insufficient funds" if from.balance_cents < amount

  from.balance_cents -= amount
  to.balance_cents   += amount

  from.save!
  to.save!
end
```

------------------------------------------------------------------------

#### ✅ Best practice: Emails/logging with `after_commit`

``` ruby
class User < ApplicationRecord
  after_commit :enqueue_welcome_email, on: :create

  private
  def enqueue_welcome_email
    SendWelcomeEmailJob.perform_later(id)
  end
end
```

------------------------------------------------------------------------

### MongoDB Examples

#### ❌ Bad: Multi-document creation without transaction

``` ruby
user    = User.create!(email: email)
profile = Profile.create!(user_id: user.id, name: name)
```

#### ✅ Fixed: Wrap in transaction

``` ruby
Mongoid::Clients.default.with(write: { w: :majority }) do |client|
  session = client.start_session
  session.with_transaction do
    user    = User.with(session: session).create!(email: email)
    profile = Profile.with(session: session).create!(user_id: user.id, name: name)
  end
end
```

------------------------------------------------------------------------

#### ❌ Bad: Inventory decrement (non-atomic)

``` ruby
product = Product.find(product_id)
product.stock -= 1
product.save!
```

#### ✅ Fixed: Use `$inc` (atomic operator)

``` ruby
Product.where(id: product_id, :stock.gte => 1)
       .find_one_and_update(
         { '$inc' => { stock: -1 } },
         return_document: :after
       )
```

------------------------------------------------------------------------

#### ✅ Money transfer with Mongoid transaction

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

## 6. How to Call These Patterns

``` ruby
# PostgreSQL
Payments::TransferFunds.call(from_id: 1, to_id: 2, amount_cents: 500)

# MongoDB
Users::CreateWithProfileMongo.call(email: "a@b.com", name: "Max")
Inventory::ReserveItemMongo.call(product_id: BSON::ObjectId("..."))
```

------------------------------------------------------------------------

## 7. What Must Be Atomic vs. Not

**Atomic:** - User + Profile creation - Money transfers -
Inventory/quotas - State transitions

**Not atomic:** - Emails - Logging - Background jobs - Cache

------------------------------------------------------------------------

## 8. Quick Checklist

-   [ ] Use `ActiveRecord::Base.transaction` in Postgres.\
-   [ ] Use row locks (`lock`, `with_lock`) where needed.\
-   [ ] Enforce invariants with DB constraints + app validations.\
-   [ ] Use `$inc` for atomic updates in MongoDB.\
-   [ ] Use MongoDB transactions for cross-doc operations.\
-   [ ] Use `after_commit` for side-effects.\
-   [ ] Keep transactions short.\
-   [ ] Consider idempotency keys for payments.

------------------------------------------------------------------------

## 9. Final Thoughts

-   **PostgreSQL** = full ACID, perfect for transactional systems.\
-   **MongoDB** = atomic per document, transactions available but
    heavier.\
-   **Rails best practice** = make critical paths atomic, decouple side
    effects.

By following these patterns, your Rails apps will remain consistent,
reliable, and scalable.
