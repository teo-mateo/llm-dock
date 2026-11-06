---
name: android-development
description: Implement Android features in LLM-Dock using the existing architecture and reusable test tools. Use when assigned Kotlin/Compose work, Android Pi screens, mobile UI fixes, or an Android issue.
---
# Android development

Own the Android implementation; the PO supplies product outcomes and reviews acceptance.
Read `../../../android/CLAUDE.md` and `../../../android/docs/Plan_TOC.md`, then only the
feature requirements and source relevant to the issue. Do not copy their rules here.

## Route the work

- Build, JVM tests, SDK setup, known test flakes: read `../android-testing/SKILL.md`.
- Device interaction and screenshot evidence: read `../android-emulator/SKILL.md`.
- Before starting a fixture server OR changing the app's backend URL for a test,
  read `../android-fixtures/SKILL.md` completely. This is a prerequisite, not optional context.
- Branch/PR hand-back: follow `../../../docs/pi-dev-protocol.md`.

## Example: choose the skill before the action

Task: photograph a pending-question indicator, but the deployed backend lacks prompts.
Correct sequence: read `android-fixtures/SKILL.md` → start its server → run its setup helper
(which checks readiness and forwarding) → connect with dummy credentials → change scenario.
Do not start the server after reading only this entry skill, then troubleshoot login by guessing
URLs, trying TOTP, or writing another parser. The fixture skill carries those prerequisites.

Task: adjust row spacing against the live session list without changing servers.
Use the emulator skill; no fixture skill is needed unless deterministic data becomes necessary.

## Working agreement

Use your assigned isolated worktree. Keep changes scoped to the issue; implementation design
is yours. Ask when product behaviour is ambiguous or the API cannot support it.
Reuse the helpers below instead of inventing a server, coordinate parser, or build sequence.
If a helper cannot cover the task, identify the missing capability before expanding tooling.

Reserve the emulator with the PO before device work; separate worktrees do not isolate devices.
Never install on the owner's phone without an explicit request. Do not restart the dashboard,
touch model containers, or read credentials into chat.

## Hand-back

Report acceptance evidence, exact test results, known failures and remaining live checks.
Label fixture screenshots as fixtures, not live end-to-end verification. Return the emulator
to its previous configuration and release its reservation. Leave your checkout in the agreed
idle state and post DONE with the PR and head SHA. Include `Closes #N` in the PR body.
Wait for review/fix rounds and then PO-triggered `/compact` before the next task.
