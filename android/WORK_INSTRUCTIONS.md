# Working instructions — Android client

How the Android app gets built. This is the protocol; `docs/Plan_TOC.md`
is the spec and `docs/Architecture.md` is the technical foundation.

Written for an autonomous run: the project owner is not available, so
nothing here waits on a human except the stop conditions in §8.

---

## 1. Role — orchestrator, not author

The main session **orchestrates**. It does not write feature code.

It owns: branching, committing, PRs, merging, marking `[DONE]`, choosing
models, judging whether a feature is really done, and deciding when to
stop.

**The one exception.** A trivial mechanical fix where spawning an agent
costs more than the edit — a typo breaking the build, a missing import,
a version bump. Anything with design judgment in it goes to an agent,
even if it looks small.

---

## 2. Two agents per feature

| Agent | Job |
|---|---|
| **Implementation** | Build the feature's Must requirements against its spec file |
| **Review & testing** | Independently verify every Must acceptance criterion, and review the diff |

The reviewer must be a **fresh agent**, never the implementer continued.
An implementer is the worst possible judge of whether its own work meets
the criteria.

This matters more here than on most projects: there is no codex pass and
no human reviewer on Android work. **These two agents are the entire
quality gate.**

Run them serially. The emulator is one shared device and two agents
installing the same package will stomp each other.

---

## 3. The loop, per feature

```
1.  git checkout main && git pull && git checkout -b android-f0X-<slug>
2.  spawn the implementation agent          (model per §5)
3.  spawn the review & testing agent        (fresh agent, model per §5)
4.  fix-up round if the reviewer found real problems — back to 2 with a
    narrowed brief, not a fresh start
5.  orchestrator confirms: every Must criterion has evidence
6.  mark [DONE] in docs/Plan_TOC.md §6
7.  commit — one commit per feature
8.  open a PR, merge it
9.  notify on Telegram
10. next feature, from a fresh main
```

Merging per feature is structural, not bookkeeping. The features are a
dependency chain — F01 needs F00's code, F05 needs F04's — and the rule
is to branch from a fresh `main`. An unmerged PR forces the next branch
to stack on it, which breaks the rule and guarantees conflicts.

---

## 4. What every agent brief must contain

Agents do **not** share the orchestrator's context. Every brief is
self-contained or the agent guesses. Include all of:

- **Read first**, by path:
  - `android/CLAUDE.md` — toolchain, `scripts/dev.sh`, emulator, dashboard auth
  - `android/docs/Architecture.md` — the decisions it must not violate
  - `android/docs/F0X-<feature>.md` — the requirements it is building
  - `docs/android/chat-app-mockups.html` — **name the screens**, and point at
    the `:root` CSS block (~line 36) for the design tokens. The file is
    ~1700 lines; an agent told to "read the mockups" will waste its context.
- **Read also**, when relevant: the feature files it depends on, and the
  dashboard source for any endpoint it consumes. The backend is the
  authority on the wire format, not the docs.
- **Scope**: which requirement IDs are in, which are explicitly out.
- **Build and verify**: `android/scripts/dev.sh`, and `JAVA_HOME=/opt/android-studio/jbr`.
- **Report back**: what was built, which criteria are verified and how,
  which are not and why, and any deviation found in the spec.

### Hard constraints for every agent

State these in the brief; do not assume they are inferred:

- **Never** `git commit`, `push`, `merge`, or create a PR. The
  orchestrator commits.
- **Never** start or stop LLM containers, or fire test traffic at them.
- **Never** wipe, factory-reset or kill the emulator. `dev.sh clear`
  (this app's data only) is fine.
- **Target a device explicitly whenever more than one is attached.** The
  owner's physical phone is sometimes plugged in alongside the emulator.
  `./gradlew installDebug` installs to **every** connected device, and
  `dev.sh` and bare `adb` target whatever adb happens to pick — an agent
  hit this and pushed a build to the owner's phone mid-session, under
  another agent that was using it. Use
  `adb -s <serial> install -r app/build/outputs/apk/debug/app-debug.apk`,
  and `adb -s <serial>` for every shell, screencap and dump.
  Check with `adb devices -l` first.
- **The owner's phone is not a test device.** If a brief does not
  explicitly assign it to you, do not install to it, do not clear its app
  data (that destroys their stored credential and signs them out), and do
  not touch their real conversations.
- **One agent per device, and the owner outranks every agent.** A device
  is assigned to exactly one agent at a time; the orchestrator hands it
  over explicitly and never to two at once. The moment the owner starts
  using a device themselves, every agent is off it — a `uiautomator dump`
  or a stray `input tap` while a human is mid-gesture wastes their time
  and corrupts both sets of observations. When a device is withdrawn
  mid-run, do not wait for it: write the device-dependent checks down as
  line items for the owner and carry on with everything else.
- **Prefer the owner for anything about feel.** Scroll behaviour, gesture
  conflicts, keyboard handling and animation are judged far better by a
  thumb than by injected single-pointer events. Hand those over as a
  short list in plain language rather than burning device time on
  synthetic approximations of them.
- **Never** call the dashboard's configuration endpoints — see F00-R10.
- **Never** edit a requirements file except to add to its *Deviations*
  section, and only with a reason.
- **Never delete a file, and never ask permission to delete one.** A
  delete prompts the owner for approval; during an unattended run that
  stalls the agent until someone wakes up. Leftover scratch files cost
  nothing by comparison — the owner clears them at the end.
  - Temporary files go in the session scratchpad, not the repo.
  - If one must live inside `android/src` to compile — a probe test, say —
    name it `Tmp*` or `Probe*`, leave it, and **list it in the report** so
    the orchestrator can deal with it before committing. It must not break
    the build or fail a test run.
  - Still fine, and say so: creating and overwriting files,
    `git checkout -- <path>` to revert an edit, and `dev.sh clear`.
- Test conversations are free to create and delete via the API; prefix
  them so they are identifiable. That is server state, not files.

---

## 5. Choosing a model

Match the model to the difficulty. A weak model on a hard feature
produces a plausible-looking wrong abstraction that thirteen later
features inherit; a strong model on a trivial edit is waste.

| Tier | Use for |
|---|---|
| **Opus** | Cross-cutting infrastructure, concurrency and streaming, auth and security, anything where a wrong abstraction propagates |
| **Sonnet** | A screen or flow implemented against a clear spec, with the foundation already in place |
| **Haiku** | Mechanical, fully-specified edits with no design judgment |

Planned assignment. Revise if a feature turns out harder than it reads —
but never downgrade to save time.

| Feature | Difficulty | Implementation | Review |
|---|---|---|---|
| F00 cross-cutting foundation | high — the spine | Opus | Opus |
| F01 connection and auth | high — silent re-auth, credential storage | Opus | Opus |
| F02 conversation list | medium | Sonnet | Sonnet |
| F03 new conversation | medium | Sonnet | Sonnet |
| F04 chat turn and streaming | **highest** — frame parsing, coalescing, D3 state rule | Opus | Opus |
| F05 message rendering | medium — streaming markdown without flicker | Sonnet | Sonnet |
| F06 message actions | medium | Sonnet | Sonnet |
| F07 model selection | medium | Sonnet | Sonnet |
| F08 conversation tools | medium-low | Sonnet | Sonnet |
| F09 run continuity | high — reattach, replay, backoff | Opus | Opus |
| F10 models list | medium | Sonnet | Sonnet |
| F11 model detail and control | medium | Sonnet | Sonnet |
| F12 container logs | medium-low | Sonnet | Sonnet |
| F13 settings | low | Sonnet | Sonnet |

The reviewer never runs below the implementer's tier.

---

## 6. Calibration — what this app is

State this in every brief, implementation and review alike.

**This is a single-user Android client for a home LLM rig on a LAN.** One
person, one phone, one dashboard. No adversary, no fleet, no uptime
commitment, no compliance bar. Judge every finding and every fix against
that, not against a general-purpose production app.

The line: **a fix is worth making when a real user on this setup would
actually hit it, or when a later feature would inherit the mistake.**
Everything else is noise, and noise has a cost — an hour spent on a flaky
test for already-verified behaviour is an hour F04 does not get.

Worked examples from F00:

- **Worth it.** A blocking disk read on the main thread, because thirteen
  features would have copied the pattern. Unordered preference writes,
  because sign-out would leave a token on disk.
- **Not worth it.** A regression test for cancellation behaviour a probe
  had already verified. It consumed ~30 minutes of retries on a
  timing-dependent assertion and was dropped.

This cuts both ways. Do not gold-plate — and do not quietly lower the bar
on something that genuinely matters. Correctness in the foundation still
counts; polish for its own sake does not.

A flaky test is worse than no test: it fails later for reasons unrelated
to whatever is being worked on then. Prefer a deterministic assertion, or
none plus a note.

---

## 7. What "done" means

Every **Must** requirement implemented, and every acceptance criterion
for it verified **with evidence**:

- logic criteria → a passing JVM test (`docs/Architecture.md` Part IV)
- device criteria → a screenshot or a passing instrumented test

Should-priority items may be skipped; note it in the feature file.

Never mark `[DONE]`, and never report a feature complete, with
unverified criteria. Name the outstanding ones instead. Some of F00's
criteria reference screens that do not exist yet — carry those forward
and verify them in the feature that introduces the screen, recording
where.

If implementation shows a requirement is wrong, edit it in its feature
file and record why under *Deviations*, in the same commit. Never leave
the plan describing something the app does not do.

---

## 8. When to stop

Stop, write up the state, and leave the tree clean. Do not grind.

- An implementation agent makes **two consecutive attempts** at the same
  feature with no material progress.
- A requirement proves impossible against the existing API. That is a
  spec bug — record it and stop rather than inventing a workaround or
  quietly dropping the requirement.
- Infrastructure fails and cannot be fixed: emulator gone and unable to
  start, dashboard down, no chat-capable model running.
- A decision is genuinely the owner's — product scope, or a security
  trade-off not already settled in the requirements.
- Anything that would need a destructive or unauthorized action to
  proceed.

On stopping: report what merged, what is in flight, what is blocked and
why, and what the next step would be. Do not leave a half-merged branch
or a dirty working tree.

Finishing the sequence early is a fine outcome. Reporting a feature done
that is not, is not.
