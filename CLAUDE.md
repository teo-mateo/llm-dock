# LLM-Dock — Claude operational notes

Tactical playbook for adding / running models in this llm-dock instance.
The general developer guide is in `AGENTS.md`; this file holds gotchas
that don't fit there.

## Adding a new vLLM service from the CLI

Workflow when the dashboard isn't open or you want a scripted change:

1. **Download the model into the HF cache.** Containers run with
   `HF_HUB_OFFLINE=1` (set in `dashboard/templates/vllm.j2`), so anything
   the model needs must already be on disk before the container starts.
   ```
   /home/teodor/.local/bin/hf download <org>/<model>
   ```
2. **Append a service entry to `services.json`.** Keys: `alias`, `port`,
   `api_key`, `model_name`, `params` (dict of CLI flags), `template_type:
   "vllm"`. Pick a free port in 3300–3399 (used ports are visible in
   `services.json` itself).
3. **Rebuild `docker-compose.yml` from `services.json`.** Don't edit the
   generated section directly — it's between `BEGIN DYNAMIC` /
   `END DYNAMIC` markers and gets clobbered. Instead:
   ```
   cd /github/teo-mateo/llm-dock/dashboard && venv/bin/python -c "
   from compose_manager import ComposeManager
   mgr = ComposeManager('/github/teo-mateo/llm-dock/docker-compose.yml',
                        '/github/teo-mateo/llm-dock/services.json')
   mgr.rebuild_compose_file()"
   ```
4. **Bring the container up.** `cd /github/teo-mateo/llm-dock && docker
   compose up -d <service-name>`. Use `--force-recreate` after editing
   params on an existing service.
5. **Tail logs to verify.** `docker logs -f <service-name>` — wait for
   `Application startup complete` or `Uvicorn running on http://0.0.0.0:8000`.

## Gotchas

### vLLM ≥0.20 removed `--task`

In vLLM 0.20.x (the version in `llm-dock-vllm`), the old `--task embed`
flag is gone. Use:

- `--runner pooling` — instead of `--task embed` (also `auto`, `draft`,
  `generate`)
- `--convert embed` — picks the embed pooler when the model could be used
  for multiple pooling tasks (also `auto`, `classify`, `none`)

To explore the current arg surface inside the image:

```
docker run --rm --gpus all --entrypoint vllm llm-dock-vllm serve --help=all 2>&1 | grep -- '--<flag>'
```

(Without `--gpus all`, `vllm serve --help` aborts in pydantic device
validation before printing the parser.)

### Custom-arch models need both their repos cached

Models with `trust_remote_code` often reference Python modules in a
*different* HF repo via `auto_map`. Example: `nomic-ai/nomic-embed-text-v1.5`'s
config.json points to `nomic-ai/nomic-bert-2048--modeling_hf_nomic_bert`,
so you must download **both**:

```
hf download nomic-ai/nomic-embed-text-v1.5
hf download nomic-ai/nomic-bert-2048
```

Symptom if you forget: container exits with
`OSError: We couldn't connect to 'https://huggingface.co' to load the
files, and couldn't find them in the cached files.`

### Embedding services should keep `--gpu-memory-utilization` low

The big chat models commonly take 0.55–0.94. An embedding service running
alongside them only needs a sliver — set it to ~0.10 or less so it
doesn't try to grab KV cache that's already reserved.

### Unknown flag names are silently dropped

`render_cli_flag()` in `flag_metadata.py` is permissive: any string
starting with `-` passes through to the rendered command unchanged.
That's why arbitrary vLLM flags work in `params` without metadata
entries — but it also means a **typo** in the flag name (e.g. `--gpu-mem`)
ships to the container as-is and fails at startup, not at config time.
Verify with `mgr.preview_service(name)` before bringing the container up.

## Reference: working embedding service

`vllm-nomic-embed-text-v1.5` (port 3320) — see `services.json`. Smoke
test:

```
curl -s -X POST http://localhost:3320/v1/embeddings \
  -H "Authorization: Bearer llmd-3379c4e668fe175d2a279d64e3f664112833" \
  -H "Content-Type: application/json" \
  -d '{"model":"vllm-nomic-embed-text-v1.5","input":"search_document: hello"}'
```

Returns 768-dim float vectors. Use `search_document:` prefix on stored
text and `search_query:` prefix on queries (Nomic's matryoshka task
prefixes).
