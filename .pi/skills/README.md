# Project skill map

Skills live in this repository so procedures and their helpers travel with every worktree.
Pi discovers `.pi/skills/*/SKILL.md`; use `/reload` after merging or start a new session.
Only skill names/descriptions load initially. The entry skill routes to the relevant child;
do not paste the whole tree into every developer's context.

```text
android-development/          entry: ownership, code/docs, hand-back
android-testing/              SDK/JDK + targeted/full JVM gates
  scripts/check.sh
android-emulator/             reserved-device interaction + screenshots
  scripts/ui.py               exact Compose tag wait/tap/bounds/absence/tags
  scripts/connect.py          tag-driven Connect-screen switch (password from env)
android-fixtures/             deterministic Pi session-list + SSE evidence
  scripts/server.py           loopback-only mock dashboard
  scripts/scenarios.py        absent/empty/waiting/offline data
  scripts/scenario.py         change state explicitly, no timed transitions
  scripts/setup.py            readiness + emulator authorization/forwarding preflight
  tests/test_helpers.py       real HTTP/SSE and UI parsing/target-safety checks
```

This is a logical skill tree, not an instruction to load all children. The existing
`android/CLAUDE.md` owns Android toolchain/architecture/safety facts; `android/scripts/dev.sh`
remains the owner of existing build/device commands. These helpers fill demonstrated gaps,
not replace that developer guide or introduce an agent orchestration framework.

## Why these helpers

Observed in pi-dev2's #392 session: missing SDK configuration in its fresh worktree; repeated
full Gradle runs around documented flakes; a one-off ~5 KB fixture server with timed updates;
two successive tag-tapping scripts; repeated sleep-driven UI navigation.

The kit removes setup rediscovery and the per-task fixture/parser rewrite. It does not waive
acceptance criteria or claim fixture evidence proves the deployed backend works. There is no
physical-phone automation, credential copying, production API proxy, or automatic sign-out.
Emulator connection/restoration remains an explicit, observable step.

## Audit of the #394 run (2026-11-07, PO)

Read: `android-development`, `android-testing`, then `android-fixtures` only after a failed login.
Used: `ui.py` 21×, `check.sh` 12×, `scenario.py` 6×, `setup.py` 3× (once it existed).
Gaps the run exposed, now fixed: a nonexistent example tag (`pi_sessions_screen`); no way to list
real tags, so seven inline XML-regex blocks re-derived them; no helper for the Connect screen, so
sign-out → URL → password → submit was hand-written four times; fixture timestamps read
`20763 d ago` in screenshots. Noncompliance rather than a gap: three standalone `sleep` turns
(covered by the examples in `android-testing`) — the checkout predated that merge.

## Validate

```bash
cd .pi/skills/android-fixtures
python3 -m unittest discover -s tests -v
```

From any directory, `bash <repo>/.pi/skills/android-testing/scripts/check.sh doctor` checks the
local prerequisites without changing the device. Reserve the emulator before any live smoke
check and do not interrupt another developer's installed build.
