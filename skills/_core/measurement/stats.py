"""Pure statistics of the measurement core: no file, no state, standard library only.

Formulas and their sources are listed in this folder's README.md. Every
function takes numbers and returns numbers or plain dicts; ``None`` stands
for infinite degrees of freedom (JSON has no infinity).
"""

from __future__ import annotations

import math
from statistics import NormalDist

#: Bland & Altman (1986): the 95 % limits of agreement are bias +/- 1.96 sd.
LOA_MULTIPLIER = 1.96
_TINY = 1e-300


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Continued fraction of the incomplete beta function, modified Lentz method
    (Press et al., Numerical Recipes, 3rd ed., section 6.4)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        for numerator in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                          -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > _TINY else _TINY)
            c = 1.0 + numerator / c
            c = c if abs(c) > _TINY else _TINY
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def regularized_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b), the regularized incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def t_cdf(t: float, dof: float | None) -> float:
    """Student t distribution function: P(T <= t) = 1 - I_{nu/(nu+t^2)}(nu/2, 1/2) / 2 for t > 0
    (Abramowitz and Stegun 26.7.1 with 26.5.27); the normal one when ``dof`` is ``None``."""
    if dof is None or math.isinf(dof):
        return NormalDist().cdf(t)
    tail = 0.5 * regularized_beta(dof / (dof + t * t), dof / 2.0, 0.5)
    return 1.0 - tail if t > 0 else tail


def t_quantile(p: float, dof: float | None) -> float:
    """The p-quantile of Student's t with ``dof`` degrees of freedom (``None``: the normal
    quantile). Inverted by bisection on ``t_cdf`` to a relative width of 1e-13."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"p={p} is not inside (0, 1)")
    if dof is None or math.isinf(dof):
        return NormalDist().inv_cdf(p)
    if dof <= 0:
        raise ValueError(f"dof={dof} is not positive")
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_quantile(1.0 - p, dof)
    lo, hi = 0.0, 1.0
    while t_cdf(hi, dof) < p:
        lo, hi = hi, hi * 2.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, dof) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-13 * max(1.0, hi):
            break
    return (lo + hi) / 2.0


def mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def sample_sd(values: list[float]) -> float:
    """Experimental standard deviation, n - 1 in the denominator (GUM 4.2.2, eq. 4)."""
    centre = mean(values)
    return math.sqrt(math.fsum((v - centre) ** 2 for v in values) / (len(values) - 1))


def type_a(values: list[float]) -> dict:
    """GUM 4.2: mean (eq. 3), s (eq. 4), u = s / sqrt(n) (eq. 5), nu = n - 1 (4.2.6)."""
    n = len(values)
    sd = sample_sd(values)
    return {"n": n, "mean": mean(values), "sd": sd, "u": sd / math.sqrt(n), "dof": n - 1}


def combine(components: list[dict]) -> dict:
    """Combined standard uncertainty of uncorrelated inputs, u_c = sqrt(sum (c_i u_i)^2) (GUM 5.1.2,
    eq. 10), and the Welch-Satterthwaite effective degrees of freedom
    nu_eff = u_c^4 / sum((c_i u_i)^4 / nu_i) (GUM G.4.1, eq. G.2b); a component with ``dof`` None
    (infinite) adds nothing to the denominator, and nu_eff is None when every one is infinite."""
    contributions = [abs(c["sensitivity"]) * c["u"] for c in components]
    u_c = math.sqrt(math.fsum(x * x for x in contributions))
    denominator = math.fsum(x ** 4 / c["dof"] for x, c in zip(contributions, components) if c["dof"] is not None)
    return {"u_c": u_c, "effective_dof": (u_c ** 4 / denominator) if denominator > 0 else None}


def coverage(effective_dof: float | None, level: float | None, declared_k: float | None) -> dict:
    """The coverage factor: ``declared_k`` as given; otherwise t_{(1+level)/2}(nu) with nu_eff
    truncated to the next lower integer (GUM G.4.1, note to step 3), or the normal quantile
    when nu_eff is infinite (GUM G.3.3, 6.3)."""
    if declared_k is not None:
        return {"method": "declared", "k": declared_k, "level": None, "dof_used": None}
    p = (1.0 + level) / 2.0
    if effective_dof is None:
        return {"method": "normal", "k": t_quantile(p, None), "level": level, "dof_used": None}
    dof_used = max(1, math.floor(effective_dof + 1e-9))
    return {"method": "student-t", "k": t_quantile(p, dof_used), "level": level, "dof_used": dof_used}


def bland_altman(device: list[float], reference: list[float]) -> dict:
    """Bland & Altman (1986): d_i = device_i - reference_i, bias = mean(d), sd of d (n - 1),
    95 % limits of agreement bias -/+ 1.96 sd."""
    differences = [d - r for d, r in zip(device, reference)]
    bias = mean(differences)
    sd = sample_sd(differences)
    return {"n": len(differences), "bias": bias, "sd_differences": sd, "multiplier": LOA_MULTIPLIER,
            "loa_lower": bias - LOA_MULTIPLIER * sd, "loa_upper": bias + LOA_MULTIPLIER * sd}


def icc_2_1(rows: list[list[float]]) -> dict:
    """ICC(2,1): two-way random effects, absolute agreement, single measures (Shrout & Fleiss 1979;
    ICC(A,1) of McGraw & Wong 1996; the form Koo & Li 2016 report). ``rows`` holds n subjects by
    k raters. From the two-way ANOVA mean squares,
    ICC = (MSR - MSE) / (MSR + (k - 1) MSE + k (MSC - MSE) / n); ``value`` is None when the
    denominator is not positive (no variance to apportion)."""
    n, k = len(rows), len(rows[0])
    grand = math.fsum(x for row in rows for x in row) / (n * k)
    row_means = [math.fsum(row) / k for row in rows]
    col_means = [math.fsum(row[j] for row in rows) / n for j in range(k)]
    ss_rows = k * math.fsum((m - grand) ** 2 for m in row_means)
    ss_cols = n * math.fsum((m - grand) ** 2 for m in col_means)
    ss_total = math.fsum((x - grand) ** 2 for row in rows for x in row)
    ss_error = max(0.0, ss_total - ss_rows - ss_cols)
    ms_rows, ms_cols = ss_rows / (n - 1), ss_cols / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))
    denominator = ms_rows + (k - 1) * ms_error + k * (ms_cols - ms_error) / n
    return {"form": "ICC(2,1)", "n": n, "k": k, "ms_rows": ms_rows, "ms_columns": ms_cols, "ms_error": ms_error,
            "value": (ms_rows - ms_error) / denominator if denominator > 0 else None}
