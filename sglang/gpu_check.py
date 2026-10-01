#!/opt/pennyroyal/.venv/bin/python
"""Small container-only GPU checks; no model load or persistent host writes."""
import os
import runpy
import sys

if "--configured" not in sys.argv:
    launcher = runpy.run_path("/usr/local/bin/llm-dock-sglang")
    env = os.environ.copy()
    launcher["configure_cuda_compat"](env)
    os.execve(sys.executable, [sys.executable, __file__, "--configured"], env)

import torch
import triton
import triton.language as tl
import flashinfer


@triton.jit
def add_kernel(X, Y, Z, N: tl.constexpr, BLOCK: tl.constexpr):
    offsets = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    x = tl.load(X + offsets, offsets < N, other=0)
    y = tl.load(Y + offsets, offsets < N, other=0)
    tl.store(Z + offsets, x + y, offsets < N)


print("GPU:", torch.cuda.get_device_name(0), flush=True)
x = torch.ones(256, device="cuda")
y = torch.full_like(x, 2)
z = torch.empty_like(x)
add_kernel[(1,)](x, y, z, N=256, BLOCK=256)
assert bool(torch.all(z == 3))
print("Triton JIT: passed", flush=True)
q = torch.randn(32, 128, device="cuda", dtype=torch.bfloat16)
k = torch.randn(128, 8, 128, device="cuda", dtype=torch.bfloat16)
v = torch.randn_like(k)
out = flashinfer.single_decode_with_kv_cache(q, k, v)
assert out.shape == q.shape and bool(torch.isfinite(out).all())
print("FlashInfer attention: passed", flush=True)
