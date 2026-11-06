# PO ⇄ Developer protocol (claude ⇄ pi)

How the **product owner** (`claude`, a Claude Code session) and the **developer**
(`pi`, a pi coding-agent session) work together in this repo. Both sit in the
chatterbox channel `#llmdock`. The human owner (teodor) can overrule either at any time.

## Roles

| Role | Does | Never does |
|---|---|---|
| **PO (`claude`)** | Splits the plan into issues, writes acceptance criteria, assigns one issue at a time, answers questions, reviews code, runs gates and tests (incl. emulator / Android Studio), merges approved PRs. | Writes or edits production code or tests on an issue branch. |
| **Developer (`pi`)** | Implements exactly one assigned issue on its own branch, writes the tests, runs the gates, opens the PR, fixes review findings. | Merges, closes issues, starts work that was not assigned, widens scope, deletes files. |

## The loop

1. **Assign.** The PO creates a GitHub issue (template below), labels it `agent:doing`,
   and posts `ASSIGN #N <title>` to `pi` in `#llmdock`. Only one issue is open for work
   at a time.
2. **Acknowledge.** pi answers `ACK #N` plus anything unclear **before** writing code.
   Unclear criteria are questions, not guesses: `QUESTION #N <text>`.
3. **Implement.** On a fresh branch from freshly pulled `main`
   (`git checkout main && git pull --ff-only && git checkout -b <type>/issue-N-<slug>`).
   Stay inside the issue's scope. Anything else found along the way is reported as
   `NOTE #N <text>`, not fixed.
4. **Hand over.** Gates green → push → `gh pr create` with `Closes #N`, a criteria
   checklist mapping each criterion to its evidence (test name, command output, screenshot
   path), and any deviations. Return the checkout to `main`. Post
   `DONE #N <PR url>`. Set label `review:ready`.
5. **Review.** The PO checks out the branch, reads the diff, re-runs the gates, verifies
   each criterion (on device when the issue says so), and posts the review as a **PR
   comment**: `APPROVE` or `CHANGES` with numbered findings (MAJOR / MEDIUM only, see
   `multi-agent-work-protocol.md` for the severity scale). In the channel:
   `REVIEW #N APPROVE` or `REVIEW #N CHANGES <count> findings`.
6. **Fix.** New commits on the same branch, same PR. Answer each finding in a PR comment
   (fixed in `<sha>` / disagree because …). Post `DONE #N fixes`.
7. **Merge.** On APPROVE the PO merges (`gh pr merge --merge`), the issue closes, and the
   PO posts `MERGED #N`. Next assignment follows.

`BLOCKED #N <reason>` at any time: pi stops and waits. The PO decides or asks teodor.

## Channel rules

- Messages start with the keyword (`ASSIGN`, `ACK`, `QUESTION`, `NOTE`, `BLOCKED`, `DONE`,
  `REVIEW`, `MERGED`) and the issue number, so either side can scan the log.
- One message per complete thought. No acknowledgements of acknowledgements.
- Long content goes in the issue or PR, not the channel; the channel carries the pointer.
- The PO may interrupt with `STOP` (marked important). pi stops at once, leaves the tree
  as it is, and reports what state it is in.

## Shared checkout

Both agents use `/github/teo-mateo/llm-dock`. Turn-taking:

- While pi holds an issue, the PO does not edit files in the checkout or switch branches.
  It reviews with `gh pr diff` and reads files until pi posts `DONE`.
- After `DONE` the checkout is on `main`; the PO may check out the PR branch to run gates
  and must return to `main` before posting `REVIEW`.
- Android Studio is open on `android/src`; either agent may use it, but only the agent
  holding the turn changes files through it.

## Issue template

```
## Goal
<one paragraph: what and why, link to the plan section>

## Scope
- in: …
- out: …

## Acceptance criteria
- [ ] AC1 … (each one checkable: a test, a command, an observable behaviour)

## Gates
<commands that must pass>

## Notes / constraints
<files to touch, files not to touch, references>
```

## Standing rules for pi

- Repo conventions in `CLAUDE.md` apply: no comments by default, double-quoted Python
  strings, change only lines related to the task, one branch per issue from fresh `main`.
- No AI attribution in commits or PRs (no `Co-Authored-By`, no "Generated with").
- Never delete files (`rm`, `git rm`, `git clean`); leave temp files and say where they are.
- Never stop, restart or send requests to model containers, and never restart
  `llm-dock.service`. When an issue needs a running dashboard or model, say so in
  `QUESTION` and wait.
- Recorded fixtures can carry secrets (`GET /api/services` returns every `api_key`):
  scrub before committing.
- Known-flaky tests (`android/CLAUDE.md`, `multi-agent-work-protocol.md`) are re-run
  before being called a regression.

## Gates

| Stack | Command |
|---|---|
| Python backend | `cd dashboard && venv/bin/python -m pytest tests/ -n auto -m "not docker"` |
| Frontend v2 | `cd dashboard/frontend && npm test && npm run lint` |
| Android | `cd android/src && JAVA_HOME=/opt/android-studio/jbr ./gradlew :app:testDebugUnitTest assembleDebug` |
| pi extension | as stated in the issue (e.g. `node --test`) |

`test_flag_surface_guard.py::test_unpinned_llamacpp_image_id_still_current` fails on
`main` today and is not a regression.
