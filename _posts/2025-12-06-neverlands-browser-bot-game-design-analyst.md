---
layout: post
title: "Turning Neverlands Into Design Fuel: A Browser Bot + GPT-5.1 Game Analyst"
date: 2025-12-06
author: Max Lukin
tags: [ai, game-design, bots, playwright, openai, mmorpg, analysis]
categories: [engineering, game-design, AI]
description: "How we built a Playwright + GPT-5.1 pipeline that logs into neverlands.ru, captures real game screens, and turns them into structured design insights for your own MMORPG."
---

> **TL;DR**
>
> - We built a **browser bot + GPT-5.1 analyst** that logs into neverlands.ru, captures real game screens, and turns them into structured JSON.
> - The goal is **game design research**, not automation: extract systems, loops, and UX patterns to feed your own GDD.
> - Everything runs locally: credentials live in `.env`, GPT only ever sees **HTML snapshots**, not your password.
> - The stack is small and explicit: **Node 18 + Playwright + dotenv + OpenAI API**, wired through a few focused TypeScript scripts.

---

## Why build a bot for Neverlands?

Neverlands is a long-running browser MMORPG with **mature systems**: inventory, combat, economy, events, social layers. Instead of cloning it, we want to **study** it:

- What progression and compulsion loops does it use?
- How are shops, currencies, and sinks structured?
- Which UI patterns make the game readable (or confusing)?

Doing this manually is slow. Screenshots pile up, notes get messy, and you miss subtle connections. The solution: a **repeatable pipeline** that:

1. Logs into your account.
2. Visits interesting screens (home, character, inventory, shop, PvP…).
3. Saves HTML + screenshots.
4. Asks GPT-5.1 to extract features and player needs into machine-readable JSON.

Those JSON files become the raw material for your **game design document**, where you remix Neverlands-inspired ideas into your own world.

---

## Architecture at a glance

The repo is intentionally small:

```text
bot/        # Playwright automation
  login.ts  # log in + save session
  crawl.ts  # visit screens + save HTML/PNG

analyzer/
  analyzeScreens.ts  # send HTML to GPT-5.1 using promt.md

data/
  session/   # Playwright storage state
  raw/       # captured HTML + screenshots
  analysis/  # GPT JSON outputs

promt.md     # "game design analyst" prompt template
doc/         # human docs (setup, usage, dev)
```

The heart of the system is **promt.md**: a prompt that tells GPT-5.1 to behave like a **game design analyst**. For each HTML snapshot it:

- Identifies visible systems/features (e.g., daily quests, energy, shop widgets).
- Describes how they seem to work from the UI.
- Classifies the player need they target (progression, social, mastery, etc.).
- Suggests how you might adapt the idea for your own MMORPG.

Outputs are strict JSON, so you can script on top of them later.

---

## Technical implementation

### 1. Login with Playwright

`bot/login.ts` uses **Playwright** to open `http://www.neverlands.ru/`, fill the login form, and save a session:

- Credentials come from `.env` via `dotenv`:
  - `NEVERLANDS_USERNAME`, `NEVERLANDS_PASSWORD`.
- Form selectors are configurable:
  - `NEVERLANDS_USERNAME_SELECTOR`, `NEVERLANDS_PASSWORD_SELECTOR`, `NEVERLANDS_SUBMIT_SELECTOR`.
- The URL is normalized so any `https://neverlands.ru` is rewritten to `http://www.neverlands.ru/`.
- On success, storage state is written to `data/session/neverlands.json`.

You run it with:

```bash
npm run login
```

### 2. Crawling key game screens

`bot/crawl.ts` reuses the saved session to open specific URLs and capture HTML + PNG:

- Screens are defined as a small list of `{ id, url }`.
- For each screen, we:
  - `page.goto(url, { waitUntil: 'networkidle' })`.
  - Save DOM: `data/raw/<id>.html`.
  - Save screenshot: `data/raw/<id>.png`.

You can start with `home`, then add pages like `inventory`, `character`, `shop`, or any internal route Neverlands exposes.

Run the crawl:

```bash
npm run crawl
```

### 3. GPT-5.1 analysis

`analyzer/analyzeScreens.ts` reads every `*.html` file in `data/raw/`, then calls the OpenAI Chat Completions API:

- Uses `OPENAI_API_KEY` from `.env`.
- Defaults to `OPENAI_MODEL=gpt-5.1` (configurable).
- Loads `promt.md` as the **system** message.
- Sends the HTML as the **user** message.
- Requests `response_format: json_object` to keep outputs parseable.

Each result is saved as `data/analysis/<screen>-<hash>.json`, giving you versioned feature maps per screen.

Run analysis:

```bash
npm run analyze
```

---

## From JSON to a game design document

Once you have JSON outputs, you’re holding a **Neverlands feature index**. Typical next steps:

- Group features by system: combat, economy, social, events, meta.
- Identify loops: daily quests → currencies → shops → upgrades.
- Tag ideas as **keep / adapt / avoid** for your own game.

Because the analysis is structured, it’s easy to:

- Generate Markdown “inspiration cards” per feature.
- Build tables comparing Neverlands to other games you crawl later.
- Feed the JSON back into another GPT-5.1 pass to draft full sections of your GDD.

The bot doesn’t design the game for you—but it **amplifies your research** so you can spend time on synthesis, not screenshot wrangling.

---

## Safety, ToS, and scope

Even though neverlands.ru allows bots, we built this stack with a conservative mindset:

- Credentials live only in `.env` on your machine.
- GPT never sees your password or cookies, only HTML.
- The intended use is **analysis**, not auto-play or farming.
- Screen lists are small and intentional, not full-site crawlers.

If you adapt this to other games, always re-check each game’s ToS and keep your rate of requests reasonable.

---

## Where to go next

With the core pipeline in place, the most interesting work is ahead:

- Add more screens and flows (e.g., onboarding, high-level PvP, events).
- Enrich `promt.md` with new fields (risk flags, UX pain points, monetization patterns).
- Build a small UI or static site to browse the analyzed features.
- Compare Neverlands against other browser MMORPGs using the same pipeline.

The end goal: a **living game design document** for your own project, grounded in real, battle-tested systems—but with your own take on what makes them fun.

