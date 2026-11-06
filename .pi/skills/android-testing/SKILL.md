---
name: android-testing
description: Build and test the LLM-Dock Android app with consistent SDK/JDK settings and bounded handling of known flakes. Use for Android Gradle gates, fresh-worktree setup, or JVM test failures.
---
# Android testing

Use `scripts/check.sh` from any directory; it resolves its own checkout and exports the SDK/JDK
settings missing in fresh worktrees. It does not create local.properties or copy credentials.

```bash
bash scripts/check.sh doctor
bash scripts/check.sh test '*PiSessionMapperTest*'
bash scripts/check.sh build
bash scripts/check.sh test --all
```

Paths above are relative to this skill directory. Start with tests covering the changed behaviour;
run the issue's full gate once before hand-back. Do not add `--rerun-tasks` to chase an unrelated
flake or repeatedly rebuild an unchanged APK. Build once, then install that APK on the reserved
emulator using the emulator skill.

The current known flakes and required JDK are owned by `../../../android/CLAUDE.md`.
If a full-suite failure matches a documented flake, rerun that class alone and report both results.
A new failure requires investigation, not classification by resemblance alone.

## Examples: background tests

Good — one process call, then work independently or end your turn. Completion wakes you:

```json
{"action":"start","name":"issue-394-formatting-tests","cwd":"/github/teo-mateo/llm-dock-wk1","command":"bash .pi/skills/android-testing/scripts/check.sh test '*PiFormattingTest*'","notify":{"onSuccess":"turn","onFailure":"turn"}}
```

After the exit notification, inspect that process's output and real exit code. If it failed,
identify the failing test before rerunning anything. The process tool retains the logs.

Bad — do not follow a process start with a bash call like:

```bash
sleep 40; echo ok
```

That holds the turn without learning whether the test finished or passed. Do not replace it
with repeated process-output polling or a second watcher just to wait for normal process exit.

## Examples: preserve failure status

Good — pass the command directly to the process tool, as above. If a file log is needed:

```bash
bash .pi/skills/android-testing/scripts/check.sh build > /tmp/issue-394-build.log 2>&1
```

The command still exits with Gradle's status; inspect the log after the process finishes.

Bad — this reports tail's status, not Gradle's:

```bash
bash .pi/skills/android-testing/scripts/check.sh build 2>&1 | tail -5
```

If a pipeline is genuinely needed, explicitly enable `set -o pipefail` before it. A printed
`BUILD_EXIT=1` followed by successful `echo` is not a successful gate: report the failure.

Keep full logs in scratch files; report test counts, failing names and evidence paths.
