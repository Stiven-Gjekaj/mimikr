"""Arithmetic on embedding vectors."""

import math


def cosine(a: list[float], b: list[float]) -> float:
    length = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / length if length else 0.0
