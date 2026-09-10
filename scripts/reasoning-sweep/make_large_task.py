#!/usr/bin/env python3
"""Generate tasks/large.txt deterministically (fixed seed).

The task embeds a 1500-integer list and asks for three aggregates over the
primes in it. Answers are written to tasks/large.expected.json so the sweep
results can be graded mechanically.
"""

import json
import random
from pathlib import Path

SEED = 20260909
COUNT = 1500


def is_prime(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def main():
    rng = random.Random(SEED)
    numbers = [rng.randint(1000, 99999) for _ in range(COUNT)]
    primes = [n for n in numbers if is_prime(n)]
    expected = {
        "count": len(primes),
        "sum": sum(primes),
        "largest": max(primes),
        "seed": SEED,
        "count_total": COUNT,
    }

    listing = "\n".join(str(n) for n in numbers)
    prompt = (
        f"Below is a list of {COUNT} integers, one per line.\n\n"
        f"{listing}\n\n"
        "Consider only the numbers in the list that are prime. Report:\n"
        "(a) how many there are,\n"
        "(b) their sum,\n"
        "(c) the largest one.\n"
        "Give the three numbers in your final answer.\n"
    )

    here = Path(__file__).resolve().parent
    (here / "tasks" / "large.txt").write_text(prompt, encoding="utf-8")
    (here / "tasks" / "large.expected.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(expected, indent=2))
    print(f"prompt chars: {len(prompt)}")


if __name__ == "__main__":
    main()
