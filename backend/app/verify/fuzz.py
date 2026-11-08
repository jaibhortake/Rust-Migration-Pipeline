"""Mutation of test inputs (no LLM) and delta-debugging minimisation of failing inputs."""

import random
import re
from collections.abc import Awaitable, Callable

_NUM = re.compile(r"-?\d+")


def mutations(seed: str, rng: random.Random, n: int = 6) -> list[str]:
    """Structure-preserving mutants: numbers are replaced by boundary values, lines duplicated or dropped."""
    out: list[str] = []
    nums = list(_NUM.finditer(seed))
    lines = seed.splitlines()
    ops = ["boundary", "negate", "grow", "shrink", "dup_line", "drop_line", "swap_lines"]
    for _ in range(n * 3):
        if len(out) >= n:
            break
        op = rng.choice(ops)
        m = seed
        if op in ("boundary", "negate", "grow", "shrink") and nums:
            tok = rng.choice(nums)
            v = int(tok.group())
            new = {
                "boundary": rng.choice([0, 1, -1, 2, 10, 100]),
                "negate": -v,
                "grow": v * rng.choice([2, 10]) + 1,
                "shrink": v // 2,
            }[op]
            m = seed[: tok.start()] + str(new) + seed[tok.end() :]
        elif op == "dup_line" and len(lines) > 1:
            i = rng.randrange(1, len(lines))
            m = "\n".join(lines[: i + 1] + [lines[i]] + lines[i + 1 :]) + "\n"
        elif op == "drop_line" and len(lines) > 2:
            i = rng.randrange(1, len(lines))
            m = "\n".join(lines[:i] + lines[i + 1 :]) + "\n"
        elif op == "swap_lines" and len(lines) > 2:
            i, j = rng.sample(range(1, len(lines)), 2)
            ls = lines[:]
            ls[i], ls[j] = ls[j], ls[i]
            m = "\n".join(ls) + "\n"
        if m != seed and m not in out:
            out.append(m)
    return out


async def minimize(failing: str, still_fails: Callable[[str], Awaitable[bool]], budget: int = 40) -> str:
    """ddmin over lines, then over whitespace-separated tokens. still_fails(input) must re-run BOTH programs and
    return True only when the original accepts the input and the outputs still differ."""
    best = failing
    calls = 0

    async def reduce(parts: list[str], join: str) -> list[str]:
        nonlocal calls
        n = 2
        while len(parts) >= 2 and calls < budget:
            chunk = max(1, len(parts) // n)
            reduced = False
            for i in range(0, len(parts), chunk):
                cand = parts[:i] + parts[i + chunk :]
                if not cand:
                    continue
                calls += 1
                if await still_fails(join.join(cand) + ("\n" if join == "\n" else "")):
                    parts, n, reduced = cand, max(n - 1, 2), True
                    break
                if calls >= budget:
                    break
            if not reduced:
                if chunk == 1:
                    break
                n = min(len(parts), n * 2)
        return parts

    lines = best.splitlines()
    if len(lines) > 1:
        best = "\n".join(await reduce(lines, "\n")) + "\n"
    # shrink numbers toward zero one at a time
    for tok in list(_NUM.finditer(best))[:10]:
        if calls >= budget:
            break
        v = int(tok.group())
        for smaller in (0, 1, v // 2):
            if smaller == v:
                continue
            cand = best[: tok.start()] + str(smaller) + best[tok.end() :]
            calls += 1
            if await still_fails(cand):
                best = cand
                break
    return best
