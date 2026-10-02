# Multi-Agent Work Protocol

Defines the two-agent Android issue pipeline used from this repo: a persistent
**IMPLEMENTER** and a persistent **REVIEWER-TESTER**, driven by an **Orchestrator**
(the parent session agent). It exists so every issue cycle follows the same
turn-taking rules over one shared checkout, and so a future orchestrator session
can run the loop without re-deriving it.

## Roles

| Role | Contract |
|---|---|
| **Orchestrator** | Owns the queue. Verifies the shared checkout is on a freshly pulled `main` before every assignment (see step 1), feeds one issue at a time to the Implementer, wakes the Reviewer-Tester on completion, reads the review posted on the GitHub issue, drives fix rounds, and on acceptance merges the PR into `main` and pushes. Never spawns additional agents during the loop. |
| **IMPLEMENTER** | Implements one issue per task on a fresh branch, following the issue's design doc in `docs/plans/`, commits, pushes, opens a PR against `main`. Writes code and the tests the plan specifies. |
| **REVIEWER-TESTER** | Independently reviews the branch and re-runs the gates. Never edits production code. Reports **MAJOR and MEDIUM findings only** — LOW and nits are suppressed entirely. Verdict is `APPROVE` or `REQUEST-CHANGES`. The full review is **posted as a comment on the GitHub issue** under review and mirrored to the orchestrator. |

Both agents are long-lived subagents of the orchestrator session: they finish
their turn, go idle, and are woken by message. No worktree, no parallel agents.

## The loop (one issue)

1. **Assign.** Before assigning anything, the Orchestrator verifies the shared
   checkout is on `main`, freshly pulled from `origin` (`git checkout main` →
   `git fetch origin` → `git merge --ff-only origin/main`, clean tree apart from
   permitted untracked artifacts), and states that verification in the
   assignment. The assignment message MUST explicitly instruct the Implementer
   to create a **new branch for this issue** from that fresh `main` — never to
   continue an existing or previous issue's branch. Orchestrator sends: issue
   number, design doc path (`docs/plans/issue-NNN-*.md`), branch-name
   suggestion.
2. **Implement.** Implementer: `git checkout main` → `git fetch origin` → fresh
   branch (e.g. `fix/issue-NNN-short-name`) → implement per the plan (deviations
   recorded in the PR body) → run gates → conventional commit → push →
   `gh pr create` with `Closes #NNN`, summary, deviations, test evidence →
   report branch, commit, PR URL, gate outcomes to the orchestrator.
3. **Review.** Orchestrator wakes the Reviewer-Tester with branch + PR URL +
   design doc + the issue's acceptance criteria. Reviewer checks out the branch
   **in the shared workspace**, reviews the diff against plan and conventions,
   re-runs the gates itself, checks each acceptance criterion against a named
   test/evidence, judges any declared deviations, **posts the review as a
   comment on the GitHub issue** (verdict, gates + outcomes, criteria mapping,
   MAJOR/MEDIUM findings only), mirrors the verdict to the orchestrator, then
   `git checkout main` before ending its turn.
4. **Fix round (if REQUEST-CHANGES).** Orchestrator relays the posted defect
   list verbatim to the Implementer, which fixes with new commits on the **same
   branch/PR**, re-runs gates, pushes, reports. Orchestrator re-tasks the
   Reviewer-Tester on the updated head commit. Repeat until the posted review
   says `APPROVE`.
5. **Accept and merge.** On an `APPROVE` review comment with no unresolved
   MAJOR/MEDIUM findings, the orchestrator merges the PR into `main`
   (`gh pr merge <n> --merge`), returns the shared checkout to
   `main`/`origin main`, and assigns the next issue. Neither agent merges,
   closes issues, or deletes branches; merging is the orchestrator's step.

## Shared-checkout discipline

Strictly turn-taking: exactly one agent is active against
`/github/teo-mateo/llm-dock` at any moment.

- The tree rests on clean `main` between turns; every agent hands back to `main`
  before finishing its turn.
- Every issue cycle starts from `main` freshly pulled from `origin`, verified by
  the Orchestrator; each issue gets exactly one new branch created from it.
- No git worktrees, no parallel checkouts — the branch under work is simply
  `git checkout`ed by whoever holds the turn.
- The Implementer keeps its PR branch pushed to `origin` by the end of every
  turn so the reviewer (or the orchestrator) can check it out.
- Untracked planning artifacts (e.g. `docs/plans/issue-*-plan.md`) are never
  added to feature commits or deleted by pipeline agents.

## Gates (run by both agents; Reviewer runs them independently)

| Stack | Commands (from stated dir) |
|---|---|
| Android | `cd android/src` · `JAVA_HOME=/opt/android-studio/jbr ./gradlew testDebugUnitTest assembleDebug` · device pass via `android/scripts/dev.sh` when the plan calls for one |
| Python backend | `cd dashboard` · `venv/bin/python -m pytest tests/ -n auto` |
| Frontend v2 | `cd dashboard/frontend` · `npm test` · `npm run lint` |

Gate notes:

- **Read, don't count.** `ThreadToolsTest` and `ThreadAutoSendTest` are known-flaky
  (tests for the races) in full-suite runs — re-run before calling one a
  regression (`android/CLAUDE.md`).
- Sandbox mounts `~/.gradle` read-only: agent runs add
  `GRADLE_USER_HOME=<workspace>/.gradle` (mirrored cache, gitignored).
- `venv/bin/pytest` entry script is stale against the installed pytest; use
  `venv/bin/python -m pytest`.

## Severity vocabulary (review findings)

- **MAJOR** — acceptance criterion unmet, root cause not actually addressed,
  broken gate, data-loss/concurrency defect, security issue.
- **MEDIUM** — material test-quality gap (criteria not pinned), plan deviation
  not recorded, scope creep beyond the task, convention violation with real
  consequence.
- **LOW / nit** — style, wording, taste, redundant guards: **never reported**.

## Failure/edge handling

- Implementer blocker (plan contradicts code): stop, report the contradiction
  to the orchestrator; do not improvise a different fix silently.
- Reviewer environment failure (emulator down, gate unrunnable): report honestly
  as a gap in the verdict; never skip a gate silently.
- Gate red only on a known-flaky test after re-run: note it, not a finding.
- The orchestrator is the only agent-to-agent message channel; agents never
  wake each other. The review comment on GitHub is the durable record; the
  mirror message to the orchestrator is the wake signal.
