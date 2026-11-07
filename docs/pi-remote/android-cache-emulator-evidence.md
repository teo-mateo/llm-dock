# Pi cache — reserved-emulator fixture evidence

Verification for #422, 2026-11-07. **Fixture-driven emulator evidence, not a live Pi/model
session, physical-phone benchmark or Android system-death/navigation-restoration test.**
Production application code was unchanged from `ef4b6aa16f23c5b544d86b1652841f524fe8a306`.

## Environment and preservation

- Reserved `emulator-5554`, AVD `Medium_Phone_API_36.1`, 1080×2400 screenshots.
- The normal host-GPU launch segfaulted before an app/configuration change. The coordinator
  made one managed fallback launch with `-gpu swiftshader_indirect -no-window
  -no-snapshot-load -no-snapshot-save -no-audio`; no AVD config edit, wipe or emulator reboot.
  These results therefore describe a **software-rendered, headless emulator on this host**.
- The prior target app was stopped, debuggable and run-as-readable, with three private files,
  no pending share, no Pi cache and no adb reverse mapping. The original APK and complete
  private-data tar were preserved outside the repository (0700 directory, 0600 files).
  Tar membership matched the device file listing; original/candidate/test signing
  certificates matched. `install -r` preserved target UID and Keystore.
- Only the new test package was temporarily installed, with explicit coordinator permission.
  `PiCacheEmulatorSetupTest` recorded prior local URL and secret-decryption presence without
  launching an Activity or printing values, then staged the verified loopback fixture before
  any UI launch. Login used only the existing connect helper and dummy password `fixture`.
  No dashboard/model endpoint or physical phone was used.
- After testing, the original APK hash and all three original private-file hashes matched;
  the original URL and Keystore token/credential presence checks passed without Activity
  launch. The target app was stopped again, the new test package and only the newly created
  reverse mapping were removed, and original network/font values were unchanged. No existing
  cache was manually deleted. The coordinator stopped its fixture/emulator processes and
  released the reservation. [Restoration receipt](evidence/issue-422/observations.json).
  Local backend credential validity was not tested against a real dashboard.

## Representative fixture

The shared fixture kit now has a `cache` scenario, rather than a separate server framework:

- 1,000 deterministic review turns, **16,000 events / 8,347,855 event-JSON bytes**.
- Text/thinking deltas, a notice during an open assistant, final messages, read/bash starts,
  partial updates and long source/test outputs, run ends and state transitions.
- By event type: assistant messages 1,276,860 bytes, deltas 1,155,372, tool results 3,770,618,
  tool updates 1,224,399, plus user/args/state/notice/run metadata. This is not merely a large
  number of empty events. Content is synthetic and deliberately repetitive/compressible.
- Initial production checkpoint: **7,000 items / 2,000 distinct tool calls**, 5,461,852 bytes
  of decompressed JSON and about 583 KB gzip, below the 8 MiB entry bound.
- Replay pages contain at most 500 ordered events. An append adds exactly 16 events / seven
  items. `after` filtering, summary boundaries, gates, 503 detail-stream outage, end/delete
  and request/batch counters are controlled by the shared kit.

Counters describe frames the fixture wrote, not independently proof of client consumption.
Consumption was checked separately in the real app's committed checkpoint: cursor, cardinality,
unique item/tool IDs and exactly one occurrence of each final text marker.

## Observation method and timings

`measure_cache.py` uses host monotonic time around the **existing UI helper**: start before
invoking the row-tap command, detect the first `pi_assistant_text` node, then the visible
`Connected` label. This includes Python startup, tag lookup, adb input and UI hierarchy-dump
latency. Content may have rendered before the observation. These are **automation-observed
bounds, not pure first-pixel/app CPU latency**; there is no arbitrary CI speed threshold.

For a hit, replay is held before any event or summary. Cached text and `Cached · checking…`
must be visible while the new request has sent zero events and no summary. For a nonempty
suffix, the event gate is released while the post-replay summary remains held: UI must say
`Catching up…` and remain read-only. Only releasing summary permits `Connected`.

| Sample | Cursor requested | Events supplied | Tap command → first assistant | Tap command → current | Summary release → current |
|---|---:|---:|---:|---:|---:|
| Initial miss | 0 | 16,000 | 7,370 ms | 9,437 ms | not gated |
| Reopen, one new suffix | 16,000 | 16 | 4,553 ms | 10,865 ms | 2,090 ms |
| Miss after verified deletion/reset | 0 | 16,000 | 4,334 ms | 6,453 ms | not gated |
| Reopen, already-committed suffix | 16,016 | 0 | 4,186 ms | 8,517 ms | 2,142 ms |

The hit totals include deliberate gate/observation pauses and are **not comparable catch-up
speed measurements** against ungated miss totals. Warmup, software rendering and dump overhead
also differ; two samples do not establish a speedup attributable solely to caching. The strong
result is functional: cached content appeared without requiring replay, and requests supplied
only the uncommitted suffix. [Raw measurements](evidence/issue-422/).

### Measurement failures and resolution

- A raw `CACHE_BASELINE_END_1000` text wait timed out because Markdown rendered underscores as
  formatting. Screenshots show the correct module/tail; checkpoint marker checks use raw stored
  text. Timings use the stable assistant tag and phase labels instead of that raw text selector.
- An attempted repeat hit timed out waiting for `Catching up…`. Inspection found `after=16016`,
  `latest_seq=16016`, `sent_events=0`, `summary_sent=false`, gate `summary`, UI correctly checking.
  The old live view had already committed the append before Back finished disposing it. With
  no events, the runtime has no event-triggered catching-up transition before summary. This
  failed sample was excluded; the measurement helper now requires catching-up only for a
  nonempty backlog, with a unit regression. No production defect or code expansion was inferred.

## Acceptance observations

| Criterion | Actual result / evidence |
|---|---|
| Cold miss and back/reopen content | Miss requested 0 and committed 16,000 with 7,000 unique items. Back/reopen painted cached content under a closed replay gate; requested 16,000 and accepted exactly 16 new events, committing 16,016 / 7,007 items. [Miss](evidence/issue-422/miss-1.json), [suffix hit](evidence/issue-422/hit-suffix.json). |
| Offline cached open and suffix recovery | Fixture detail-stream 503 mode terminated the connection; back/reopen remained readable with `Offline / reconnecting…` and read-only footer. After an offline append, online replay requested 16,016 and supplied 16 events. While summary was held, UI said catching-up and the committed cursor remained 16,016. After summary, cursor was 16,032 with 7,014 unique items and each suffix marker once. This was a **controlled session-stream outage**, not global Wi-Fi/airplane-mode testing. |
| Surviving-process background/resume | Home/background retained the same PID and existing stream request count. A further suffix committed 16,048 / 7,021 items while backgrounded; bringing the task forward showed current content. No reload was inferred. |
| Explicit cold process restart | Separately force-stopped only the fixture-configured target app. Relaunch produced a different PID; opening its session restored 16,032 under a closed replay gate, requesting 16,032 with zero events/summary supplied. This is **force-stop/relaunch**, not proof of full Android system-death navigation restoration. |
| Sign-out and reuse | Sign-out reached Connect with no transcript screen/assistant tag. The committed cursor 16,048 file remained byte-identical. Reauthentication to the same dummy server painted it again while replay was blocked, requesting 16,048 and receiving zero events. |
| Deletion/invalidation | Ended the fixture, then used the real UI swipe/undo path. Waited for **both** fixture `deleted=true` and zero committed Pi cache files, not just the empty-state UI. A subsequent reset/open requested 0 again. |
| Configuration restoration | Original APK and three private files restored byte-for-byte, original URL and secret/Keystore presence verified without real-server Activity launch; test package/mapping removed; target stopped; parent-owned processes stopped/reservation released. |

[Machine-readable observations](evidence/issue-422/observations.json) include request cursors,
checkpoint counts, retained-file hash equality, PIDs and restoration booleans. They contain only
fixture data; original preferences, APKs, credential metadata and backups are **not committed**.

### Fixture screenshots

| Screenshot | What it shows |
|---|---|
| [Miss connected](evidence/issue-422/miss-connected.png) | Long text, thinking/tool cards and final fixture result, current state. |
| [Offline cached open](evidence/issue-422/offline-cached-open.png) | Cached text remains readable, explicit reconnect status and read-only footer. |
| [Suffix catching up](evidence/issue-422/suffix-catching-up.png) | Events received, summary not yet accepted; still read-only. |
| [Online recovered](evidence/issue-422/online-recovered.png) | Current suffix result after summary. |
| [Force-stop cached checking](evidence/issue-422/force-stop-cached-checking.png) | New process paints cached content while replay is held. |
| [Background resumed](evidence/issue-422/background-resumed.png) | Same process/task after background suffix commit. |
| [Signed out](evidence/issue-422/signed-out.png) | Connect only; fixture URL, no transcript or credential value. |
| [Signed in, reused](evidence/issue-422/signed-in-reused.png) | Retained cache visible only after authentication, checking before replay. |
| [Deleted](evidence/issue-422/deleted.png) | Empty list after actual deletion; separate counters/file checks prove removal. |

## Reproduction and safety

1. Read the four Android skills; reserve the emulator. Use coordinator/process-managed hosting
   for the shared fixture. The normal host-GPU crash is not permission to reset/wipe an AVD.
2. Privately preserve original APK, app-private data and network/reverse configuration. Verify
   run-as backup completeness and signing compatibility before changing auth. This run had no
   original Pi cache. For other initial states, stop and arrange safe isolation/restoration;
   do not clear unrelated data or run these helpers on a phone.
3. Build app/test APKs and run fixture `setup.py --device emulator-5554 --reserved` against the
   managed, ready fixture (this creates the reverse mapping, not an app auth change). Install
   the helper only with permission, and select only
   `PiCacheEmulatorSetupTest#recordOriginalWithoutLaunchingActivity` with
   `-e pi422BackupConfirmed true`. It does not launch an Activity. Then install the candidate
   app with `-r`, run `#prepareFixtureWithoutLaunchingOriginalServer`, and use `connect.py`
   with dummy credentials.
4. Select `scenario.py cache`; from the Pi list run `measure_cache.py miss`. Return to the list
   and wait for its row before appending; run `measure_cache.py hit`. Use explicit gates and
   counters for offline/restart/auth/deletion checks, not assumed delays or guessed UI IDs.
5. Restore the original APK/data while stopped. Run only
   `#verifyRestoredConfigurationWithoutLaunchingActivity`; stop the target again, restore/check
   exact original file hashes, remove only the new test package and own reverse mapping, and
   return prior settings. Do not launch the real dashboard or run the unrelated live-health
   instrumentation suite. Keep private backups available to the owner.

## Gates and remaining limits

- Shared fixture/helper unit tests: **29 passed** (7.544s).
- Selected emulator setup/restore instrumentation: **3 methods passed**, each `OK (1 test)`.
- Focused Android JVM tests: **233 passed**, zero failures/errors/skips (6s).
- Full Android JVM/build command: **962 tests, 2 failures**, zero errors/skips; build tasks not
  reached (42s). Failures were documented `ThreadAutoSendTest` draft-save and `ThreadToolsTest`
  registry timeout cases. Both classes passed isolated: **13 tests** (2s). Aggregate remains red.
- Final standalone app + test APK builds passed (978ms, 67 tasks up-to-date); actual APKs were
  built/installed earlier for the emulator run. No broad rerun or unrelated flake fixes.
- Logs/XML: `/tmp/pi422-fixture-tests-final.log`, `/tmp/pi422-focused.log`,
  `/tmp/pi422-full-gates.log`, `/tmp/pi422-full-results/`, `/tmp/pi422-isolation.log`,
  `/tmp/pi422-isolation-results/`, `/tmp/pi422-final-builds.log`.

No live inference/backend, physical phone, WAN latency, full system-death restoration, cache
retention-expiry policy or broad layout/text-size acceptance is claimed. Open-assistant
checkpoint continuation and adversarial generation races remain JVM evidence from earlier slices;
these emulator snapshots ended at completed fixture turns. Cache/live transcript memory and
same-identity server rollback limits remain unchanged. Independent review is still required.
