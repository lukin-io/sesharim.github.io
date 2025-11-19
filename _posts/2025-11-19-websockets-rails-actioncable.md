---
layout: post
title: "From Theory to Production: Reliable WebSockets with Ruby on Rails, JWT & ActionCable"
date: 2025-11-19
tags: [rails, websockets, actioncable, jwt, architecture, scalability]
categories: [engineering, rails, AI, websocket, action_cable]
description: Step-by-step guide to building reliable, authenticated, and scalable WebSockets in Rails using ActionCable and JWT, with practical code examples and architecture patterns.
author: Max Lukin
---

> _“WebSockets are easy… until you have to make them reliable and scalable.”_

Most WebSocket tutorials stop at building a simple chat demo. But real systems need **authentication**, **reliability**, **scalability**, and **good architecture**.

In this post we’ll connect:

- The **WebSocket fundamentals & best practices** from three in-depth articles fileciteturn0file0turn0file1turn0file2
- A **real-world Rails API backend** using **Devise + JWT**
- **ActionCable** as the WebSocket layer
- Concrete **code examples**
- Extra **use cases**, **WebSocket vs pub/sub comparisons**, and **sharding/scaling patterns**

---

## 1. WebSockets in a Nutshell (For Rails Developers)

### 1.1 What is a WebSocket?

A WebSocket is a **full-duplex, persistent TCP connection** between client and server. After a one-time HTTP handshake (using `Upgrade: websocket`), both sides can send messages **at any time**, without repeated HTTP requests. fileciteturn0file0

Compared to classic HTTP:

| Feature                | HTTP                          | WebSocket                              |
|------------------------|-------------------------------|----------------------------------------|
| Connection             | Short-lived per request       | Long-lived, persistent                 |
| Direction              | Client → Server (request)     | Bidirectional                          |
| Latency                | Higher (headers + handshakes) | Lower after initial upgrade            |
| Model                  | Request/response              | Event/message-based                    |

WebSockets shine in **realtime use cases** such as chat, multiplayer games, collaborative editing, IoT telemetry, live dashboards, and more. fileciteturn0file0

---

### 1.2 The Less Glamorous Bits: Reliability & Scaling

Out of the box, **WebSockets don’t give you**: fileciteturn0file1turn0file2

- Delivery guarantees (messages may be lost on disconnect)
- Message ordering guarantees
- Automatic reconnection
- Backpressure / rate limiting
- Fault tolerance across multiple servers

At scale, you also run into: fileciteturn0file2

- **Stateful connections** (harder load balancing than stateless HTTP)
- **N² message explosion** (many clients talking to many clients)
- **Backpressure** (slow consumers, fast producers)
- **Global distribution & redundancy** requirements

The WebSocket articles break these down into **architectural** and **operational** best practices: sharding, sticky sessions, pub/sub, backpressure, monitoring, and fault tolerance. fileciteturn0file2

The good news: **Rails + ActionCable + Redis** give us a solid foundation. We just need to wire things correctly and add a few patterns.

---

## 2. WebSockets vs Pub/Sub (and HTTP): Who Does What?

It’s easy to confuse **WebSockets** and **pub/sub** as alternatives. In reality they solve **different layers** of the problem.

- **HTTP** – Request/response, great for CRUD APIs, not great for realtime.
- **WebSocket** – A **transport** for bidirectional, low-latency communication. fileciteturn0file0
- **Pub/Sub** – A **messaging pattern** (and often a dedicated system) for fanning messages out to many consumers. fileciteturn0file2

Think of it like this:

- WebSocket: _“How do I keep the pipe open between browser and backend?”_
- Pub/Sub: _“How do I deliver the right messages to the right set of subscribers?”_

A typical production system uses **both**:

1. Browsers connect to your backend over WebSockets.
2. Each backend node connects to a **pub/sub layer** (Redis, Kafka, Ably, etc.). fileciteturn0file2
3. When any node publishes an event to a topic, the pub/sub layer delivers it to all interested nodes, which then forward it to their connected WebSocket clients.

### 2.1 Comparison Table

| Aspect             | WebSocket                                  | Pub/Sub                                        |
|--------------------|--------------------------------------------|------------------------------------------------|
| Scope              | Transport between **one client & one server** | Logical messaging between many producers/consumers |
| Direction          | Bidirectional                              | Usually one-way per message (publish → subscribe) |
| Responsibility     | Keep connection open & deliver raw frames  | Route messages to interested subscribers       |
| Scaling focus      | Concurrent connections, keep-alives        | Fan-out, throughput, durability, ordering      |
| In Rails           | ActionCable connections & channels         | Redis ActionCable adapter, message buses       |

In Rails, **ActionCable + Redis** is basically **WebSocket + pub/sub** out of the box. ActionCable uses Redis to broadcast between server processes, following the pub/sub architecture pattern recommended in the best-practices article. fileciteturn0file2

---

## 3. Rails Stack Overview

We’ll assume a stack like this:

- **Rails API-only app**
- **Devise + devise-jwt** for authentication
- **ActionCable** for WebSockets
- **Redis** as ActionCable’s pub/sub backend
- A frontend (Rails, React, Vue, etc.) that:
  - Uses **JWT** for HTTP API auth
  - Uses the **same JWT** to authenticate WebSocket connections

Let’s wire this up step-by-step.

---

## 4. Authenticating WebSockets with Devise + JWT

The articles highlight that WebSocket itself doesn’t define an auth mechanism — it’s up to you to layer one on top (cookies, JWT, etc.). fileciteturn0file0

In a Rails API-only app, JWT is a natural choice.

### 4.1 Pass JWT to ActionCable

Frontend connects like this:

```js
// Example with ActionCable JS (Rails 7+)
import * as ActionCable from "@rails/actioncable";

const jwt = localStorage.getItem("jwt"); // issued by Devise + devise-jwt

const cable = ActionCable.createConsumer(
  `wss://api.example.com/cable?token=${encodeURIComponent(jwt)}`
);

const subscription = cable.subscriptions.create(
  { channel: "ChatChannel", room_id: 42 },
  {
    received: (data) => console.log("New message:", data),
  }
);
```

We attach the JWT as a **query parameter** (`token=`) so it’s accessible during the WebSocket handshake.

---

### 4.2 Decode JWT in `ApplicationCable::Connection`

`ApplicationCable::Connection` is the entry point for all WebSocket connections. This is where we validate the JWT and reject unauthorized users.

```ruby
# app/channels/application_cable/connection.rb
module ApplicationCable
  class Connection < ActionCable::Connection::Base
    identified_by :current_user

    def connect
      self.current_user = find_verified_user
    end

    private

    def find_verified_user
      token = request.params[:token]

      raise "Missing token" if token.blank?

      # Using devise-jwt under the hood
      payload = Warden::JWTAuth::TokenDecoder.new.call(token)
      user = User.find_by(id: payload["sub"])

      user || reject_unauthorized_connection
    rescue => e
      Rails.logger.warn("[ActionCable] Unauthorized connection: #{e.message}")
      reject_unauthorized_connection
    end
  end
end
```

This gives us:

- A **per-connection `current_user`**
- The same identity model as our HTTP API

It follows the article’s recommendation to handle authentication at the handshake and/or application levels. fileciteturn0file0

---

## 5. ActionCable Channels: From Chat to General Realtime

Let’s start with the “classic” chat example, then generalize.

### 5.1 Basic Chat Channel

```ruby
# app/channels/chat_channel.rb
class ChatChannel < ApplicationCable::Channel
  def subscribed
    @room = Room.find(params[:room_id])
    # Authorization example
    reject unless @room.users.include?(current_user)

    stream_for @room
  end

  def receive(data)
    # Simple example: create message & broadcast
    message = @room.messages.create!(
      user: current_user,
      content: data["content"]
    )

    ChatChannel.broadcast_to(
      @room,
      {
        id: message.id,
        content: message.content,
        user_id: current_user.id,
        created_at: message.created_at.iso8601
      }
    )
  end
end
```

Corresponding model:

```ruby
# app/models/message.rb
class Message < ApplicationRecord
  belongs_to :room
  belongs_to :user

  validates :content, presence: true
end
```

This gives you a basic **authenticated chat** over WebSockets. But to align with the articles’ **reliability** recommendations, we need to go further.

---

## 6. Reliability Patterns in Rails (From the Articles)

### 6.1 Heartbeats & Reconnection

ActionCable already supports **heartbeat pings** and automatic reconnection in the JS client, matching the best practice of keep-alives and reconnection logic. fileciteturn0file2

On the client (simplified):

```js
// ActionCable automatically tries to reconnect on close.
// You can add logging:
cable.connection.monitor.reconnectAttempts = 0;

const originalDisconnected = cable.connection.disconnected;

cable.connection.disconnected = function(...args) {
  cable.connection.monitor.reconnectAttempts += 1;
  console.warn("WebSocket disconnected – attempt",
               cable.connection.monitor.reconnectAttempts);
  originalDisconnected.apply(this, args);
};
```

---

### 6.2 Backpressure & Rate Limiting

The articles emphasize **backpressure** and throttling “greedy clients”. fileciteturn0file2

Rails doesn’t do this automatically; you can add simple rate limiting per connection.

```ruby
# app/channels/application_cable/channel.rb
module ApplicationCable
  class Channel < ActionCable::Channel::Base
    RATE_LIMIT_WINDOW = 5.seconds
    RATE_LIMIT_MAX    = 20 # messages per window

    def rate_limited?
      key   = "ws:rate_limit:#{current_user.id}:#{self.class.name}"
      data  = Rails.cache.read(key) || { count: 0, started_at: Time.current }

      if Time.current - data[:started_at] > RATE_LIMIT_WINDOW
        data = { count: 0, started_at: Time.current }
      end

      data[:count] += 1
      Rails.cache.write(key, data, expires_in: RATE_LIMIT_WINDOW * 2)

      data[:count] > RATE_LIMIT_MAX
    end
  end
end
```

Use inside a channel:

```ruby
class ChatChannel < ApplicationCable::Channel
  def receive(data)
    if rate_limited?
      Rails.logger.warn("Rate limit exceeded by user #{current_user.id}")
      return
    end

    # ...create message and broadcast
  end
end
```

---

### 6.3 Message Ordering & Deduplication

One article stresses that WebSockets don’t guarantee message ordering or delivery. fileciteturn0file1turn0file2

A simple pattern:

1. Add a **monotonic sequence** per room or stream.
2. Include `sequence` in the payload.
3. Clients discard old or duplicate sequence numbers.

Migration:

```ruby
class AddSequenceToMessages < ActiveRecord::Migration[7.1]
  def change
    add_column :messages, :sequence, :bigint, null: false, default: 0
    add_index :messages, [:room_id, :sequence], unique: true
  end
end
```

Assign sequence:

```ruby
# app/models/message.rb
class Message < ApplicationRecord
  belongs_to :room
  belongs_to :user

  before_create :assign_sequence

  private

  def assign_sequence
    self.sequence = (room.messages.maximum(:sequence) || 0) + 1
  end
end
```

Broadcast:

```ruby
ChatChannel.broadcast_to(
  @room,
  {
    id: message.id,
    sequence: message.sequence,
    content: message.content,
    user_id: current_user.id
  }
)
```

Client side, you can store `lastSequence` per room and ignore messages with `sequence <= lastSequence`.

---

### 6.4 Horizontal Scaling with Redis & Sticky Sessions

The articles talk about scaling using **pub/sub**, **sticky sessions**, and **load balancing**. fileciteturn0file2

#### `config/cable.yml`

```yaml
production:
  adapter: redis
  url: <%= ENV.fetch("REDIS_URL") %>
  channel_prefix: myapp_production
```

This uses Redis to propagate messages across all Rails instances, matching the pub/sub architectural pattern recommended in the best-practices article. fileciteturn0file2

At the load balancer:

- Make sure **WebSocket upgrade** is supported.
- Enable **stickiness** so a given client reconnects to the same instance (or at least for the duration of a session), following the sticky-session pattern described in the article. fileciteturn0file2

Example snippet for Nginx (simplified):

```nginx
location /cable {
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "Upgrade";
  proxy_set_header Host $host;

  proxy_pass http://rails_upstream;
}
```

Stickiness is usually configured at the **reverse proxy / load balancer** level (NGINX upstream hash, AWS ALB target group stickiness, etc.).

---

### 6.5 Monitoring & Metrics

Operational best practices in the articles include **monitoring, autoscaling, and alerts**. fileciteturn0file2

In Rails you can log:

- Connected users
- Active subscriptions
- Broadcast frequency
- Error rates / disconnect reasons

Example:

```ruby
# app/channels/application_cable/connection.rb
def connect
  super
  Rails.logger.info("[ActionCable] Connect user=#{current_user.id}")
end

def disconnect(reason)
  Rails.logger.info("[ActionCable] Disconnect user=#{current_user&.id} reason=#{reason}")
end
```

Hook these logs into something like Loki, Datadog, New Relic, etc., and build dashboards like **“active connections”**, **“messages per second”**, etc., as suggested by the reliability article. fileciteturn0file1turn0file2

---

## 7. Sharding & Scalability Patterns (with Rails Examples)

The best-practices article goes deep into **sharding**, **sticky sessions**, and **pub/sub** as ways to scale. fileciteturn0file2  Here are some concrete patterns for Rails.

### 7.1 Simple Horizontal Scaling (Single Region)

For many apps you can start with:

- Multiple Rails web instances (Puma/Unicorn)
- Shared Redis for ActionCable
- One regional load balancer with stickiness

Diagram in words:

> Browser → Load Balancer → [Rails + ActionCable + Redis]

All channels are available from all instances because they share Redis.

This can take you surprisingly far before you need more exotic sharding.

---

### 7.2 Tenant / Region Sharding

Once you serve users in multiple regions (e.g. EU + US), latency becomes a concern. The article describes this kind of challenge as WebSocket connections are stateful and global distribution is hard. fileciteturn0file2

You can shard by **region or tenant**:

- `wss://eu.example.com/cable` → EU cluster (Rails + Redis in EU)
- `wss://us.example.com/cable` → US cluster (Rails + Redis in US)

Routing strategy (very simplified JS):

```js
function websocketHostForUser(user) {
  if (user.region === "eu") return "wss://eu.example.com/cable";
  return "wss://us.example.com/cable";
}
```

Each cluster only holds WebSockets for its tenants. Cross-region communication can then happen via:

- Async jobs / message bus
- Periodic synchronization of data

This matches the **“shard by namespace”** idea in the article: each shard owns part of the client namespace. fileciteturn0file2

---

### 7.3 Channel / Topic Sharding

Another approach is to shard by **channel/topic type**.

Example:

- Cluster A: all **chat** channels
- Cluster B: all **analytics/metrics** channels
- Cluster C: all **IoT/device** channels

Routing example (pseudocode):

```js
function cableUrlForChannel(channelName) {
  if (channelName.endsWith("ChatChannel")) {
    return "wss://chat.example.com/cable";
  } else if (channelName.endsWith("MetricsChannel")) {
    return "wss://metrics.example.com/cable";
  }
  return "wss://realtime.example.com/cable";
}
```

This reduces the **N² problem** for some workloads because each cluster sees a smaller subset of traffic.

---

### 7.4 N² Problem in Plain Numbers

From the article: as client count grows, potential interactions grow roughly with **N²**. fileciteturn0file2

- 100 users in a room → up to ~10,000 directed message paths
- 1,000 users → up to 1,000,000 paths

If every message potentially fans out to many clients, traffic explodes.

Mitigation techniques:

- **Aggregation**: instead of sending 1000 individual “👍” reactions, send one `{ emoji: "👍", count: 1000 }`. fileciteturn0file2
- **Batching**: send updates in periodic batches (every 100 ms) instead of instantly one-by-one.
- **Scoped rooms**: split giant rooms into smaller subrooms (e.g., per topic, per segment).

Rails implementation example for **batched updates** (pseudo):

```ruby
# app/services/metrics_buffer.rb
class MetricsBuffer
  def self.buffer(metric)
    redis.lpush("metrics_buffer", metric.to_json)
  end

  def self.flush!
    items = redis.lrange("metrics_buffer", 0, -1)
    redis.del("metrics_buffer")
    data = items.map { |j| JSON.parse(j) }

    ActionCable.server.broadcast("admin_metrics", { type: "batch", data: data })
  end

  def self.redis
    @redis ||= Redis.new(url: ENV["REDIS_URL"])
  end
end
```

Run `MetricsBuffer.flush!` every 200ms in a background process or job.

---

## 8. Beyond Chat: WebSocket Use Cases in Rails

The first article lists typical WebSocket use cases, many of which are **perfect fits for Rails**. fileciteturn0file0  Let’s expand the list with practical examples.

### 8.1 Realtime Notifications

Channel:

```ruby
# app/channels/notifications_channel.rb
class NotificationsChannel < ApplicationCable::Channel
  def subscribed
    stream_for current_user
  end
end
```

Broadcast from anywhere:

```ruby
NotificationsChannel.broadcast_to(
  user,
  { type: "notification", text: "Your report is ready." }
)
```

Use this for:

- In-app alerts
- “Toast” messages
- System announcements

---

### 8.2 Realtime Dashboards (Admin / Ops)

Channel:

```ruby
# app/channels/admin_metrics_channel.rb
class AdminMetricsChannel < ApplicationCable::Channel
  def subscribed
    reject_unauthorized unless current_user.admin?
    stream_from "admin_metrics"
  end

  private

  def reject_unauthorized
    reject
  end
end
```

Periodic job:

```ruby
# app/jobs/broadcast_metrics_job.rb
class BroadcastMetricsJob < ApplicationJob
  queue_as :default

  def perform
    stats = {
      users_online: User.online.count,
      jobs_pending: JobQueue.pending.count,
      # ...
    }

    ActionCable.server.broadcast("admin_metrics", stats)
  end
end
```

Schedule every N seconds with Sidekiq/GoodJob/solid queue.

---

### 8.3 Collaborative Editing / Presence

Channel:

```ruby
# app/channels/document_channel.rb
class DocumentChannel < ApplicationCable::Channel
  def subscribed
    @document = Document.find(params[:id])
    stream_for @document

    # Presence event (join)
    DocumentChannel.broadcast_to(@document,
      { type: "presence", user_id: current_user.id, event: "joined" }
    )
  end

  def receive(data)
    case data["type"]
    when "cursor"
      DocumentChannel.broadcast_to(@document,
        {
          type: "cursor",
          user_id: current_user.id,
          position: data["position"]
        }
      )
    when "patch"
      # Apply patch, persist, broadcast diff, etc.
    end
  end

  def unsubscribed
    DocumentChannel.broadcast_to(@document,
      { type: "presence", user_id: current_user.id, event: "left" }
    )
  end
end
```

Clients can show:

- Who’s editing
- Cursor positions
- Live edits

---

### 8.4 IoT / Device Streaming

Rails can be the backend that:

- Accepts device data via HTTP or MQTT → writes to Redis/Postgres
- Streams the latest values to dashboards via WebSockets

Channel:

```ruby
class DeviceChannel < ApplicationCable::Channel
  def subscribed
    @device = Device.find_by!(public_id: params[:device_id])
    authorize! :read, @device

    stream_for @device
  end
end
```

When device data comes in:

```ruby
DeviceChannel.broadcast_to(
  device,
  { type: "reading", temperature: 21.5, humidity: 0.6 }
)
```

Matches the IoT / telemetry use case mentioned in the article. fileciteturn0file0

---

### 8.5 Long-running Jobs / Progress Bars

Instead of polling an endpoint every 2 seconds:

1. Client submits job via HTTP → gets `job_id`
2. Subscribes to `JobChannel` with that ID
3. Job broadcasts progress updates

Channel:

```ruby
class JobChannel < ApplicationCable::Channel
  def subscribed
    @job_id = params[:job_id]
    stream_from "job_#{@job_id}"
  end
end
```

Job:

```ruby
class ExportReportJob < ApplicationJob
  def perform(user_id, job_id)
    10.times do |i|
      # Some work...
      ActionCable.server.broadcast(
        "job_#{job_id}",
        { status: "progress", step: i + 1, total: 10 }
      )
    end

    ActionCable.server.broadcast(
      "job_#{job_id}",
      { status: "done", download_url: "/reports/#{job_id}.csv" }
    )
  end
end
```

---

### 8.6 Live Sports & Market Feeds

- Live match scores, game clock, and commentary
- Betting odds updates
- Stock price and order book updates

Rails can ingest upstream feeds (Kafka, external APIs) and push to clients via ActionCable channels, applying the reliability patterns above to prevent overload. fileciteturn0file0turn0file1

---

### 8.7 Live Auctions & Bidding

- Users see bids appear in realtime.
- Auction countdown timers synchronize across all clients.
- Anti-sniping strategies can be applied server-side and updates pushed instantly.

Channel example:

```ruby
class AuctionChannel < ApplicationCable::Channel
  def subscribed
    @auction = Auction.find(params[:id])
    stream_for @auction
  end

  def place_bid(data)
    amount = data["amount"].to_d
    @auction.place_bid!(current_user, amount)
    AuctionChannel.broadcast_to(@auction, {
      type: "bid_placed",
      user_id: current_user.id,
      amount: amount.to_s
    })
  end
end
```

---

### 8.8 Realtime Education & Collaboration

- Live quizzes (questions & answers in realtime)
- Shared whiteboards (drawing events over WebSockets)
- Pair programming or coding interviews

You can model each classroom/session as a channel where:

- Teacher broadcasts questions, slides, or code snippets.
- Students send answers or reactions.
- “Raise hand” events show up for the instructor instantly.

---

## 9. When to Build vs When to Use a Managed WebSocket Service

The articles make a good point: **running your own WebSocket infra at scale is expensive and complex** (time, cost, global distribution, reliability). fileciteturn0file1turn0file2

Rails + ActionCable is great when:

- You control your user count / traffic
- You’re okay operating your own Redis + WebSocket infra
- Most traffic is within a few regions

If you need:

- Millions of concurrent connections
- Global edge presence
- Stronger delivery guarantees (exactly-once, ordering, persistence)
- Built-in fallbacks across protocols

…then a **managed realtime platform** (like Ably, Pusher, etc.) sitting beside your Rails API becomes attractive, as the articles argue. fileciteturn0file1turn0file2

---

## 10. Conclusion

Bringing it all together:

1. **WebSockets** give us low-latency, bidirectional realtime communication — perfect for far more than just chat. fileciteturn0file0
2. **The articles** remind us that reliability, message guarantees, and scaling are _not_ solved by the protocol alone. fileciteturn0file1turn0file2
3. **Rails + ActionCable + Redis + Devise + JWT** provide a strong foundation:
   - JWT auth at the WebSocket handshake
   - Redis-based pub/sub for horizontal scaling
   - Channels for modeling realtime domains (chat, notifications, dashboards, IoT, collaboration, auctions, education, and more)
4. By layering:
   - Rate limiting / backpressure
   - Sequence numbers and dedup
   - Monitoring and metrics
   - Sticky sessions or sharding strategies in the load balancer

…you can build **production-grade realtime APIs** in Rails that align with the WebSocket best practices described in the articles.

Drop this file into your Jekyll blog’s `_posts` (renaming it with the proper date + slug), tweak the title/metadata, and you’ve got a comprehensive, code-heavy guide to WebSockets with Rails ready to publish.
