# SGLang long decode benchmark

Run against an already-started service:

```bash
dashboard/venv/bin/python scripts/bench/sglang/bench.py sglang-qwen3-8-flash-next-mixed-nvfp4-fp8
```

Defaults: three serial runs each at 4096, 8192 and 16384 output tokens, after
an excluded 256-token warmup. Override `--lengths`, `--runs`, `--timeout`
(socket timeout in seconds), or `--output` (JSON result path).

This uses native `/generate` with **zero user/history context and one required
BOS seed token**, without chat template overhead. It uses greedy sampling and
`ignore_eos=true` to enforce the requested output length. Cached prompt tokens
must be zero. Speculation remains enabled as configured on the service.
This synthetic workload measures decoding performance, not answer quality;
speculative acceptance depends on the generated content.

Decode throughput measures cumulative output-token growth between the first
and last streamed chunks. Both time and tokens from the first chunk are
excluded. TTFT and end-to-end speed are recorded separately, alongside native
SGLang timing/acceptance metadata. Per-4K output windows show throughput as
the generated sequence grows. Each completed measurement is saved to JSON;
no API key or generated text is saved.
