# F16 · Models from configured providers

**Mockup:** none (post-mockup feature) · **Depends on:** F03, F07, F15

The dashboard can be given OpenAI-compatible providers (Mistral first) in its web
Settings. Every chat model a configured provider serves is offered on the phone,
next to local services and OpenRouter models.

The backend shipped in PR #315 and the web side in PR #316; this feature is
client-only. Server design: `../../docs/plans/chat-providers.md`.

---

## F16-R1 · Provider model references (Must)

A provider model is addressed as `<provider-id>:<model-id>` in `main_service` /
`model_service` (`mistral:mistral-large-latest`). It parses to its own
`ModelRef` variant rather than to `ModelRef.Local`, once, at the wire↔domain seam
(`parseModelRef`), exactly like `openrouter:<id>`.

The grammar is the server's (`chat/providers.py:parse_service`), syntax only:

- the provider id is `^[a-z][a-z0-9-]{1,31}$`;
- `openrouter` is not a provider id — `openrouter:<id>` stays `ModelRef.OpenRouter`;
- only the first `:` splits, so `acme:org/model:tag` has model id `org/model:tag`;
- an empty model id, or a string without `:`, is `ModelRef.Local` — Docker
  container names cannot contain `:`, which is what makes the colon a safe
  discriminator.

**Acceptance criteria**

- [x] `parseModelRef` and `wireValue` round-trip `mistral:mistral-large-latest`,
      `acme:org/model:tag`, `openrouter:vendor/m` and `llamacpp-gemma` unchanged.
- [x] `Bad:x`, `mistral:` and `openrouter:` do not parse as provider refs.
- [x] A provider ref displays as its model id; its engine chip says which provider
      (the provider id is the fallback when the provider's display name is unknown).

## F16-R2 · Provider models in every picker (Must)

From `GET /api/chat/providers/models`:

```json
{"providers": [{"id": "mistral", "name": "Mistral", "configured": true,
                "models": [{"id": "mistral-large-latest", "label": "mistral-large-latest",
                            "aliases": [], "vision": true, "tools": true,
                            "context_length": 262144}],
                "stale": false, "error": null}]}
```

One group per provider, headed by its `name`, after the OpenRouter group. A
provider with `configured: false`, an `error`, or no models contributes no group —
the same rule as OpenRouter's `configured`. A failing call hides only the provider
groups, never the local or OpenRouter ones. The endpoint lists **all** served
models; the phone shows them all, in server order, adding and removing nothing.

The same list feeds every place that offers a model: New chat, the thread's
model switch, and Summarize (share-into-app).

**Acceptance criteria**

- [x] With Mistral configured, its models appear under a "Mistral" group in the
      New chat picker and the thread model switch, and choosing one sends
      `main_service: "mistral:<model-id>"`.
- [x] A provider whose row is unconfigured, errored or empty shows no group.
- [x] The endpoint failing (5xx, timeout) leaves local and OpenRouter options intact.
- [x] Summarize offers the provider models too.
- [x] On device: a new chat on a Mistral model streams a reply.

## F16-R3 · A provider model that is no longer offered (Should)

A thread whose `main_service` names a provider model that is no longer listed
(provider deleted, disabled, key removed) still opens, shows the model id on its
chip, and surfaces the server's error on send ("Provider 'mistral' is not
configured…"); it is not rewritten to another model. A remembered model
(`RememberedModelResolver`) that is no longer offered is not silently replaced.

**Acceptance criteria**

- [x] Such a thread opens and its chip shows the model id.
- [x] Sending a turn shows the server's error frame, as for a stopped local service.

## F16-R4 · Read-only, keyless (Must)

The phone never calls the provider settings endpoints
(`/api/chat/settings/providers…`) and never sees an API key; it only reads
`GET /api/chat/providers/models`. Provider models carry no reasoning ladder today,
so the F15 control stays hidden on them.

**Acceptance criteria**

- [x] No PUT/POST/DELETE to any provider endpoint exists in the app.
- [x] The reasoning-level control is absent on a provider-model thread.

---

## Verification notes

JVM suite (`:app:testDebugUnitTest`) green; `assembleDebug` builds.

**Device (reviewer, emulator-5554, live dashboard with Mistral configured; screenshots in
`/tmp/llm-dock-android/`):**

- **R2 New chat** — `f16-03-newchat-picker-092345.png` / `f16-04-picker-scrolled-092355.png`:
  a "Mistral" section after OpenRouter with all 14 models in the server's order (UI dump
  compared to `GET /api/chat/providers/models`). Picking `mistral-small-latest` and Start
  created the conversation with `main_service: "mistral:mistral-small-latest"` (read back
  from the API); `f16-07-mistral-small-reply-092426.png` shows the streamed reply.
- **R2 thread model switch** — `f16-10-thread-switch-header-092454.png`: the same Mistral
  group with the current model ticked; switching to `mistral-large-4` stored
  `mistral:mistral-large-4`, and a turn on that reasoning model rendered a Reasoning block
  plus the answer (`f16-12-mistral-large-4-reply-092526.png`).
- **R1 chip** — `f16-13-list-chip-092538.png`: list chip `mistral · mistral-large-4` in the
  provider colour.
- **R2 Summarize** — sharing `https://example.com` and tapping "Summarise example.com"
  created the thread on the remembered `mistral:mistral-small-latest`, ran webfetch and
  summarised (`f16-18-summarize-092756.png`).
- **R3** — verified without touching provider config: a conversation created through the
  conversations API on the unconfigured `acme:gone-model` opens with chip
  `acme · gone-model` and header `gone-model`; a turn shows the server's
  "Provider 'acme' is not configured (Settings → Model providers)." frame
  (`f16-21-r3-error-092855.png`). A provider that is configured and then removed was not
  exercised; the server takes the same not-configured path for both.
- **R4** — the Mistral thread's UI dump has no reasoning-level control, while an OpenRouter
  thread on the same build shows `Reasoning level: model default`
  (`f16-14-openrouter-thread-control-092549.png`).

All test conversations were deleted afterwards.

**JVM evidence (implementer):**

- **R1** — `ProviderModelRefTest`: round-trip of all four strings; `Bad:x`, `mistral:`,
  `openrouter:`, one-char, digit-led, 33-char ids are not provider refs (32 chars is);
  first-colon split; `displayName` is the model id; engine is `Engine.PROVIDER`;
  `providerLabel`/`chipLabel` use the name when known, the id otherwise.
- **R2** — `ProviderModelsMapperTest` (unconfigured/errored/empty rows dropped, server
  order kept, a `stale` row still shown, lenient defaults); `ProviderModelsRepositoryTest`
  (one bearer GET of `/api/chat/providers/models`, 5xx is a failed `Result`; a timeout
  takes the same `apiCall` failure path but is not exercised separately);
  `NewChatViewModelTest` — `provider models load as one group per usable provider`,
  `a failing provider endpoint leaves the local and OpenRouter options intact`,
  `choosing a provider model creates the thread with its provider-prefixed main_service`;
  `ThreadProviderModelTest` — `the model switch offers one group per usable provider, in
  server order`, `a failing provider call leaves the local and OpenRouter options of the
  model switch intact`, `switching to a provider model sends its provider-prefixed id as
  main_service`; `SummarizeCoordinatorTest` — `a remembered provider model summarizes on
  that provider model`, `a failing provider endpoint still summarizes on a remembered
  local model` (the Summarize sheet fallback is the New chat sheet, covered above).
- **R3** — `ThreadProviderModelTest` — `a thread on a provider model that is no longer
  listed opens as itself and shows the model id` (and makes no provider call on open),
  `a turn on an unconfigured provider surfaces the server's error frame`;
  `RememberedModelResolverTest` / `NewChatViewModelTest` — a remembered provider model
  that is no longer listed keeps its own ref.
- **R4** — `ProviderModelsRepositoryTest` — `no source file calls a provider settings
  endpoint or writes to a provider endpoint` (scans `src/main/java`: no
  `settings/providers`, the only `/api/chat/providers…` literal is the models path, used
  only by `ProviderModelsRepository`, which only calls `api.get`);
  `ThreadProviderModelTest` — `the reasoning-level control is absent on a provider-model
  thread`.

## Deviations

- **The conversation list never knows provider display names**, so its chip always uses
  the id fallback: `mistral · mistral-large-latest`. Fetching the provider list on the
  list screen just for a name was not worth a request per refresh. The picker header,
  which does have the list, uses the name.
- **Models tab chip label for `Engine.PROVIDER` is `api`.** That chip only ever shows
  local services, so the branch exists for exhaustiveness and is unreachable today.
