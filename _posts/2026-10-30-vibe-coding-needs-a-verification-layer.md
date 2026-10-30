---
layout: post
title: "Vibe Coding Needs a Verification Layer"
date: 2026-10-30
author: Max Lukin
tags: [ai, software-engineering, verification, testing, swift, macos, rails]
categories: [engineering, AI, testing]
description: "What actually happened while building Deep Work with AI: a prototype in about an hour, corrected requirements, SQLite recovery, native UI bugs, 361 tests and a verified Mac preview."
---

**TL;DR:** I went from an idea to an interactive prototype in about an hour with AI. The useful part was combining that speed with **validation**—checking that the product behaved as intended—and **verification**—testing that the implementation met its contracts. By the second native Mac preview, we had **361 passing Swift tests on each of two macOS CI environments** and **127 of 137 accepted product items, with 10 still blocked**. The prototype took an hour; building and verifying the native app took additional work.

After reading *Deep Work* by Cal Newport, I wanted to try longer focus sessions: around 60–90 minutes, followed by a deliberate break. I also wanted a journal showing when I actually managed to concentrate. Eventually, that could help me understand the relationship between meeting-heavy days and uninterrupted work.

That was enough to start: a timer, a journal and a small settings screen. About an hour later, I had an interactive prototype I could use to judge the idea.

The native implementation and verification came afterward. **The hour describes the prototype, not the total engineering effort or a production-ready release.**

**Turning the prototype into a contract**

Once the interaction felt right, I wanted a real macOS application using Swift, SwiftUI and AppKit. This was my first Mac app, so I brought the engineering habits I already use on Rails projects.

We kept the approved HTML reference unchanged and turned its behavior into a specification with stable requirement IDs. The handoff defined **137 implementation items** across Focus, Journal, Settings and the work-schedule editor inside Journal.

Those IDs gave later conversations something concrete to refer to. A chart needed correct date boundaries, keyboard navigation and readable labels. A Save button needed persistence and failure handling. Looking finished was only one part of the requirement.

We also kept one progress checklist. The initial JSON export stayed a snapshot; it did not become another tracker to reconcile. That small decision helped keep the process manageable as the code grew.

**One correction changed the app's lifecycle**

Early in the work, closing the window was treated as a reason to pause the timer. I corrected that: closing a utility window should let the work continue.

The intended behavior became explicit:

- Red close or **Command-W** hides the window; the timer continues in the menu bar.
- Clicking the menu-bar timer brings the existing Focus window back.
- **Command-Q** pauses, saves and waits for pending writes before exiting.
- Relaunch restores an unfinished cycle paused, waiting for Resume.

That correction reached beyond a button handler. The timer had to belong to the application rather than the window. Hiding, reopening, quitting and recovering needed different paths. The tests had to change with the requirement.

This was validation in practice: deciding the intended behavior and noticing a plausible but wrong interpretation. Regression tests then helped verify that the correction survived later changes.

**A timer quickly becomes a data problem**

I made SQLite persistence an explicit requirement for settings, schedules and journal records. Feedback kept its deliberate Save Draft behavior. The database lives in the user's Application Support directory, outside the app bundle.

Then came the less visible questions. What happens if a save fails? If the app crashes halfway through a cycle? If a write is still running when I quit? If a new version changes the schema?

We used serialized writes and transactions, retained recoverable edits on failure, and tested migrations against real SQLite. The timer saves checkpoints; after a crash, recovery uses the last committed checkpoint and excludes time when the process was not running.

Timing itself needed separation from the screen refresh. Tests used injected clocks to exercise pauses, delayed updates and phase boundaries. Journal tests covered partial sessions, date ranges, daylight-saving changes and reporting cutoffs. A new reporting setting should reinterpret history without rewriting the original timestamps.

The visible product was still a small timer. Its useful behavior depended on these details.

**The Rails connection was practical**

On a Rails application, I want RSpec model and request specs that protect observable behavior: authorization, validation, API responses, database changes and failure paths. That gives me a way to refactor or fix a bug and check whether the expected contract still holds. Scaling or performance work also needs measurements under an appropriate workload.

I wanted the same discipline here, using native Swift tests and platform checks.

We put it into `AGENTS.md`: relevant tests accompany feature changes; bug fixes include regression coverage; failures stay visible; documentation follows the implementation. Apple’s [Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/) and platform guidance became part of the development and review process.

Written rules helped keep the agent oriented. Running the checks—and inspecting what they actually proved—was still necessary.

**Using the app found things the tests had not settled**

Native acceptance exposed concrete problems. Tab inserted text instead of moving through the feedback form. Narrow layouts clipped chart labels and weekday controls. Keyboard focus could reach a chart bar without bringing it into view. Live chart updates had to preserve the user's focus.

We fixed those behaviors, added regression coverage and exercised the compiled app again in light and dark appearances, at narrow and normal widths. This made Apple's UI guidance tangible: could someone reach the control, understand it and use it without a mouse?

We also made a mistake in the verification setup. A test app copy relaunched against the normal data directory and paused my personal timer. We restored the session and corrected the fixtures to use distinct executable and bundle identities, an explicit test-data directory on every launch, and a check of the actual storage ownership lock. Renaming an app bundle had not been enough to isolate it.

VoiceOver provided another useful boundary. We could test accessibility labels and announcement dispatch, but the tooling could not reliably verify what was actually spoken. Those acceptance items stayed blocked. Posting an announcement was not evidence that a user heard the right message.

**CI and publication added their own checks**

The work moved through five PRs covering six implementation stages. After each merge, the next branch started from updated `main`. The changes carried tests, documentation and verification results. We kept the changelog simple: one consolidated entry per PR or stage, rather than an entry for every commit.

Local compilation used Command Line Tools. Hosted CI supplied full Xcode builds on Apple Silicon runners for macOS 15 and 26. That distinction mattered: an older CI compiler rejected a test fixture that compiled locally. We made its time-interval type explicit and reran the affected checks.

Publication also had to prove that a usable app was available. The release pipeline produced an optimized app ZIP, checksums and source/build metadata, then verified uploaded and public downloads.

Later, GitHub sent a failed-workflow notification. Both native test jobs and packaging had passed. The failure was a second publication attempt for a tag that already had a release. The overwrite guard refused it; we checked the original successful run and confirmed the public assets were unchanged. The red status needed investigation, not a blind rerun.

**Where that left us**

For [preview 2](https://github.com/lukin-io/deep-work/releases/tag/v0.1.0-preview.2), the recorded results were:

| Evidence | Result |
| --- | --- |
| Native Swift suite | **361 tests passed on each CI platform** |
| Hosted Xcode Release builds | **macOS 15 and 26, Apple Silicon** |
| Release verification | **20 policy tests + 17 downloaded-archive tests passed locally** |
| Product acceptance | **127/137 accepted; 10 blocked** |

These numbers describe the checks we ran, not a claim of complete coverage. The [verification record](https://github.com/lukin-io/deep-work/blob/main/docs/VERIFICATION.md#preview-2--stages-16--october-19-2026) keeps the evidence and its limits separate.

The preview includes the timer, durable journal, reporting, work schedules, CSV export and feedback drafts. Slack service code exists, but new sign-in remains unavailable in the shipped build without configuration. Live Slack, login-cycle and VoiceOver acceptance are still pending; physical sleep/wake is also separately unverified. The app is ad hoc signed and unnotarized; stable distribution needs more work.

I came away with a working preview and a process I can continue using. AI handled implementation work across a platform that was new to me, while I supplied product decisions, engineering constraints and review. Validation and verification gave us specific reasons to accept, correct or leave work unfinished.

For me, that is where vibe coding becomes useful beyond the initial demo: I can keep changing the application, and I have a repeatable way to check what those changes did.

[Source and documentation](https://github.com/lukin-io/deep-work) · [Download the Apple Silicon macOS 15+ preview](https://github.com/lukin-io/deep-work/releases/tag/v0.1.0-preview.2)
