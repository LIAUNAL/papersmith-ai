"""Pure statistics of consensus rounds and MICMAC: no file, no state, standard library only.

Consensus rounds (decision K4 of ``odd/tasks/paper-type-lines.md``). For one
item of one round, with the plan's scale, agreement cut-off and threshold:

    n                    the ratings the item received
    agree                the ratings >= agree_from
    agreement_percent    100 * agree / n
    consensus            agreement_percent >= threshold (compared exactly, as fractions)
    median, q1, q3       quantiles of the ratings, Hyndman and Fan (1996) type 7
    iqr                  q3 - q1

MICMAC (Godet's structural analysis). M is the operator's direct influence
matrix: M[i][j] says how strongly variable i influences variable j (0 none, 1
weak, 2 moderate, 3 strong, P potential, counted as the declared ``p_value``).

    influence_i   = sum_j M[i][j]    (row sum)
    dependence_j  = sum_i M[i][j]    (column sum)

Indirect influence and dependence are the row and column sums of M^k. The
ranking of a power is the competition ranking of the sums (largest first,
ties share the best rank, "1224"); a power k >= 2 is stable when both
rankings equal those of power k - 1. A variable's quadrant compares its sums
with their mean (total / n, the same for both axes); "high" means strictly
above the mean:

    influential   high influence, low dependence
    relay         high influence, high dependence
    dependent     low influence,  high dependence
    autonomous    low influence,  low dependence
"""

from __future__ import annotations

from fractions import Fraction

QUANTILE_METHOD = ("Hyndman and Fan (1996) type 7: with the ratings sorted x[0] <= ... <= x[n-1] and "
                   "h = (n - 1) p, Q(p) = x[floor(h)] + (h - floor(h)) (x[floor(h) + 1] - x[floor(h)]); "
                   "the default of R quantile(), NumPy and Excel QUARTILE.INC")
#: What a potential influence (P) counts as unless the operator declares another value.
P_DEFAULT = 4
#: The highest power MICMAC raises the matrix to.
MAX_POWER = 10
QUADRANTS = ("influential", "relay", "dependent", "autonomous")


def _number(value: Fraction) -> int | float:
    return int(value) if value.denominator == 1 else round(float(value), 4)


def quantile(values: list[int | float], p: Fraction | float) -> Fraction:
    """Hyndman and Fan type 7 quantile, computed exactly on fractions."""
    if not values:
        raise ValueError("a quantile needs at least one value")
    xs = sorted(Fraction(v) for v in values)
    h = (len(xs) - 1) * Fraction(p)
    low = int(h)  # h >= 0, so int() is the floor
    if low + 1 >= len(xs):
        return xs[low]
    return xs[low] + (h - low) * (xs[low + 1] - xs[low])


def item_summary(ratings: list[int], agree_from: int, threshold: float | int | str) -> dict:
    """n, agree, agreement_percent, median, q1, q3, iqr and consensus of one item's ratings."""
    if not ratings:
        raise ValueError("an item needs at least one rating")
    n = len(ratings)
    agree = sum(1 for rating in ratings if rating >= agree_from)
    percent = Fraction(100 * agree, n)
    q1, median, q3 = (quantile(ratings, Fraction(k, 4)) for k in (1, 2, 3))
    return {"n": n, "agree": agree, "agreement_percent": _number(percent), "median": _number(median),
            "q1": _number(q1), "q3": _number(q3), "iqr": _number(q3 - q1),
            "consensus": percent >= Fraction(str(threshold))}


def round_summary(responses: list[tuple[str, str, int]], agree_from: int,
                  threshold: float | int | str) -> list[dict]:
    """One summary per item of ``(member, item, rating)`` responses, items in first-appearance order."""
    ratings: dict[str, list[int]] = {}
    for _member, item, rating in responses:
        ratings.setdefault(item, []).append(rating)
    return [{"item": item, **item_summary(values, agree_from, threshold)} for item, values in ratings.items()]


def change(current: dict, previous: dict) -> dict:
    """How an item moved since the previous round: differences of agreement, median and IQR
    (current minus previous) and whether it had reached consensus before."""
    def exact(summary: dict, key: str) -> Fraction:
        if key == "agreement_percent":
            return Fraction(100 * summary["agree"], summary["n"])
        return Fraction(str(summary[key]))
    return {key: _number(exact(current, key) - exact(previous, key)) for key in ("agreement_percent", "median", "iqr")} \
        | {"consensus_previous": previous["consensus"]}


# --------------------------------------------------------------------------- MICMAC


def matmul(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    size = len(a)
    return [[sum(a[i][k] * b[k][j] for k in range(size)) for j in range(size)] for i in range(size)]


def row_sums(matrix: list[list[int]]) -> list[int]:
    return [sum(row) for row in matrix]


def column_sums(matrix: list[list[int]]) -> list[int]:
    return [sum(row[j] for row in matrix) for j in range(len(matrix))]


def competition_ranks(values: list[int]) -> list[int]:
    """1 for the largest; equal values share the best rank and the next rank skips ("1224")."""
    return [1 + sum(1 for other in values if other > value) for value in values]


def quadrant(influence: int, dependence: int, total: int, size: int) -> str:
    """The MICMAC quadrant by the means: ``high`` is strictly above total / size."""
    high_influence, high_dependence = influence * size > total, dependence * size > total
    if high_influence:
        return "relay" if high_dependence else "influential"
    return "dependent" if high_dependence else "autonomous"


def _layer(names: list[str], matrix: list[list[int]]) -> dict:
    influence, dependence = row_sums(matrix), column_sums(matrix)
    total, size = sum(influence), len(names)
    influence_rank, dependence_rank = competition_ranks(influence), competition_ranks(dependence)
    return {"total": total, "mean": _number(Fraction(total, size)),
            "variables": [{"name": name, "influence": influence[i], "dependence": dependence[i],
                           "influence_rank": influence_rank[i], "dependence_rank": dependence_rank[i],
                           "quadrant": quadrant(influence[i], dependence[i], total, size)}
                          for i, name in enumerate(names)]}


def micmac(names: list[str], matrix: list[list[int]], power: int | None = None, max_power: int = MAX_POWER) -> dict:
    """Direct and indirect influence and dependence of a square matrix of non-negative integers.

    ``power`` fixes k; ``None`` raises M until the ranking is stable (the first k >= 2 whose
    influence and dependence rankings equal those of k - 1), at most ``max_power``."""
    size = len(matrix)
    if size < 2 or len(names) != size or any(len(row) != size for row in matrix):
        raise ValueError("MICMAC needs a square matrix of at least two variables, one name each")
    if any(not isinstance(value, int) or value < 0 for row in matrix for value in row):
        raise ValueError("MICMAC needs non-negative integer entries")
    if power is not None and not 2 <= power <= max_power:
        raise ValueError(f"the power is between 2 and {max_power}")
    limit = power if power is not None else max_power
    current = [list(row) for row in matrix]
    ranks = (competition_ranks(row_sums(current)), competition_ranks(column_sums(current)))
    stability = []
    k = 1
    while k < limit:
        k += 1
        current = matmul(current, matrix)
        new = (competition_ranks(row_sums(current)), competition_ranks(column_sums(current)))
        stability.append({"power": k, "influence_stable": new[0] == ranks[0], "dependence_stable": new[1] == ranks[1]})
        ranks = new
        if power is None and stability[-1]["influence_stable"] and stability[-1]["dependence_stable"]:
            break
    stable = bool(stability) and stability[-1]["influence_stable"] and stability[-1]["dependence_stable"]
    return {"power": k, "power_mode": "fixed" if power is not None else "until-stable", "stable": stable,
            "stability": stability, "direct": _layer(names, matrix), "indirect": _layer(names, current)}
