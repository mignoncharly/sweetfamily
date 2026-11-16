"""Independent exhaustive reference, exact probabilities, and maximum-group exercise."""

import itertools
import sys
import time
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/vault"))
from vault_core.draw_engine import (  # noqa: E402
    InvalidRules,
    counts,
    graph,
    sample,
    support,
    validate_privacy,
    validate_result,
)


def reference(rows):
    return [
        p
        for p in itertools.permutations(range(len(rows)))
        if all(p[g] in row for g, row in enumerate(rows))
    ]


def reference_support(permutations, n, fixed=None):
    if fixed:
        permutations = [p for p in permutations if p[fixed[0]] == fixed[1]]
    if not permutations:
        return None
    return {g: {p[g] for p in permutations} for g in range(n) if not fixed or g != fixed[0]}


def reference_privacy(permutations, n):
    possible = reference_support(permutations, n)
    return possible is not None and all(
        all(len(choices) >= 2 for choices in reference_support(permutations, n, (g, r)).values())
        for g, recipients in possible.items()
        for r in recipients
    )


def compare(rows):
    n = len(rows)
    permutations = reference(rows)
    assert counts(rows)[1][0] == len(permutations)
    assert support(rows) == reference_support(permutations, n)
    for g, recipients in (support(rows) or {}).items():
        for r in recipients:
            assert support(rows, g, r) == reference_support(permutations, n, (g, r))
    expected = reference_privacy(permutations, n)
    if expected:
        validate_privacy(rows)
    else:
        with pytest.raises(InvalidRules):
            validate_privacy(rows)


def test_every_directed_four_person_graph_against_permutation_reference():
    edges = [(g, r) for g in range(4) for r in range(4) if g != r]
    for mask in range(1 << len(edges)):
        rows = [set() for _ in range(4)]
        for bit, (g, r) in enumerate(edges):
            if mask & (1 << bit):
                rows[g].add(r)
        compare(rows)


@settings(max_examples=35, deadline=None, derandomize=True)
@given(n=st.integers(4, 8), data=st.data())
def test_random_graphs_up_to_eight_against_independent_reference(n, data):
    bits = data.draw(st.lists(st.booleans(), min_size=n * n, max_size=n * n))
    compare([{r for r in range(n) if r != g and bits[g * n + r]} for g in range(n)])


@pytest.mark.parametrize(
    "n,expected", [(4, 9), (5, 44), (6, 265), (7, 1854), (8, 14833), (20, 895014631192902121)]
)
def test_exact_derangement_counts(n, expected):
    _, rows = graph([str(i) for i in range(n)], [])
    assert counts(rows)[1][0] == expected


def test_weighted_paths_have_exactly_equal_probability_and_allow_multiple_cycles():
    ids, rows = graph([str(i) for i in range(5)], [])
    _, table = counts(rows)
    for permutation in reference(rows):
        probability = Fraction(1)
        used = 0
        for r in permutation:
            probability *= Fraction(table[used | (1 << r)], table[used])
            used |= 1 << r
        assert probability == Fraction(1, table[0])
    # Four-person draw can consist of two disjoint reciprocal pairs.
    validate_result(
        ids[:4], [], [(ids[0], ids[1]), (ids[1], ids[0]), (ids[2], ids[3]), (ids[3], ids[2])]
    )
    for first in range(9):
        tickets = iter([first, 0, 0, 0])
        with patch(
            "vault_core.draw_engine.secrets.randbelow",
            side_effect=lambda _, tickets=tickets: next(tickets),
        ):
            result = sample(list(ids[:4]), [])
        validate_result(ids[:4], [], result)
        assert result[0][1] == ids[1 + first // 3]


@pytest.mark.parametrize("n", [0, 1, 2, 3, 21])
def test_invalid_sizes(n):
    with pytest.raises(InvalidRules):
        sample([str(i) for i in range(n)], [])


def test_forced_edge_and_fully_excluded_group_are_rejected():
    ids = list("abcd")
    for exclusions in ([("a", "c"), ("a", "d")], [("a", r) for r in "bcd"]):
        with pytest.raises(InvalidRules):
            sample(ids, exclusions)
    with pytest.raises(InvalidRules):
        sample(ids, [("a", "a")])
    with pytest.raises(InvalidRules):
        sample(ids, [("a", "unknown")])
    with pytest.raises(TimeoutError):
        sample(ids, [], timeout=-1)


def test_maximum_group_finishes_within_worker_budget():
    ids = [str(i) for i in range(20)]
    started = time.monotonic()
    result = sample(ids, [], timeout=60)
    validate_result(ids, [], result)
    assert time.monotonic() - started < 60
