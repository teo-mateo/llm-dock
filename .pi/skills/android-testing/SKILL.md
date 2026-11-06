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

Run long commands with the process tool and exit notifications. Keep full logs in scratch files;
report test counts, failing names and evidence paths. Shell pipelines must not hide Gradle failures.
