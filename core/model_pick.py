"""Shared helpers for choosing models by name and series."""

import re

MODELS_PER_SERIES = 3


def name_tokens(name):
    return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]


def is_experimental(name):
    return bool({"preview", "exp"} & set(name_tokens(name)))


def latest_per_series(items, series_of, cap=MODELS_PER_SERIES):
    counts = {}
    result = []
    for item in items:
        series = series_of(item)
        if series is None or cap is None:
            result.append(item)
            continue
        counts[series] = counts.get(series, 0) + 1
        if counts[series] <= cap:
            result.append(item)
    return result
