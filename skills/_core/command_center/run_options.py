"""Where a proof of concept or a full experiment can run, and how long it may take.

``run_options(root, view)`` reads only what ``get_experiments_view`` already
gathered: each product's ``Results/timing.json`` (parsed by ``parse_timing``),
the local environment (``local_env``) and the remote-services rows
(``remote_services``). It answers one row per stage (``poc``, ``full``) and
host family (``remote_services.RUN_HOSTS``) with ``available``, an estimate
and a one-line reason, plus one recommendation per stage. Host ids and labels
come from ``remote_services``, so this module names no service.

The estimate is the ONE formula of the shared timing convention, for a stage
``s`` and a host ``h`` with measurements::

    seconds = mean(secondsPerUnit over h's measurements, per arm when available
                   else overall) * epochs_s * folds_s * seeds_s * arms_s
              + setupSeconds_h * folds_s * seeds_s

"Per arm when available" means: when every measurement of ``h`` names its
arm, the mean is the mean of each arm's own mean (an arm probed twice does not
weigh double); otherwise it is the plain mean of all of them. ``setupSeconds_h``
is the mean of the measurements that state one, 0 when none does. The result
is reported as a ±20% range, never as a point claim. A host without its own
measurement reads "sin medir": a remote host is never estimated from local
timings scaled by a guessed factor. Never raises.

A schema 2 record (``remote-parallelism``'s timing probe) names a candidate
per measurement -- ``local-cpu-<N>``, ``local-mps``, ``<host>:<owner>/<machine>``
-- with its settings. Each candidate is estimated from its own rows at its
fastest measured setting, each host family's row reads its fastest candidate
(a CPU and an accelerator are never pooled), and ``candidates`` lists one row
per candidate, measured or not. ``plan_picks`` is the latest recorded
``plan``'s recommendation per stage (``<product>/.remote-parallelism/plan-*.json``),
with its reason; the estimate per candidate is serial work, and only ``plan``
counts processes and accounts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .remote_services import HOST_LABELS, RUN_HOSTS, remote_host_readiness

STAGES = ("poc", "full")
STAGE_LABELS = {"poc": "Prueba de concepto", "full": "Experimento completo"}
SCALE_KEYS = ("arms", "folds", "seeds", "epochs")
RANGE = 0.20
NOTE = "±20%, single-probe extrapolation"
UNMEASURED = "sin medir"
#: Placement rules, read on the estimate's upper bound (the same ones
#: `remote-parallelism estimate` states): a stage over this many seconds locally
#: runs on a cloud host, and a proof of concept fits this budget where it runs.
LOCAL_LIMIT = 20 * 60
POC_BUDGET = 5 * 60 * 60
MAX_MEASUREMENTS = 500
MAX_TEXT = 120
MAX_REASON = 400
MAX_PLAN_ROWS = 40
SETTING_KEYS = ("threads", "batchSize", "numWorkers", "pinMemory", "prefetch", "dtype", "dataSource")
HOST_INFO_KEYS = ("cpuCount", "ramGB", "mps", "cuda")
PLAN_HINT = ("Sin plan registrado: corre /remote-parallelism plan --timing <Nombre>/Results/timing.json "
             "--record <Nombre> para comparar CPU y GPU, local y nube, con las cuentas del equipo.")
EMPTY_HINT = ("Sin Results/timing.json: corre antes del piloto la sonda de tiempo corta (una época de un fold "
              "por brazo) que describe /remote-parallelism en «Estimate before you scale»; escribe "
              "<objetivo>/<Nombre>/Results/timing.json con sus mediciones y las escalas poc y full del protocolo.")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _text(value: Any) -> str | None:
    return value.strip()[:MAX_TEXT] or None if isinstance(value, str) else None


def parse_timing(data: Any) -> dict[str, Any] | None:
    """A ``timing.json`` document reduced to valid measurements and scales; None when unusable."""
    schema = data.get("schema") if isinstance(data, dict) else None
    if isinstance(schema, bool) or schema not in (1, 2):
        return None
    v2 = schema == 2
    if v2 and not isinstance(data.get("hosts"), dict):
        return None
    measurements: list[dict[str, Any]] = []
    raw = data.get("measurements") if isinstance(data.get("measurements"), list) else []
    for entry in raw[:MAX_MEASUREMENTS]:
        if not isinstance(entry, dict) or entry.get("unit") != "epoch":
            continue
        host, seconds = _text(entry.get("host")), _number(entry.get("secondsPerUnit"))
        if host is None or seconds is None or seconds <= 0:
            continue
        setup = _number(entry.get("setupSeconds"))
        item = {"host": host, "family": host.split(":", 1)[0], "arm": _text(entry.get("arm")),
                "device": _text(entry.get("device")), "measuredAt": _text(entry.get("measuredAt")),
                "secondsPerUnit": seconds,
                "setupSeconds": setup if setup is not None and setup >= 0 else None}
        if v2:
            processes = entry.get("processes")
            item.update({
                "candidate": _text(entry.get("candidate")) or host,
                "processes": processes if isinstance(processes, int) and not isinstance(processes, bool)
                and processes > 0 else None,
                "settings": {key: entry[key] for key in SETTING_KEYS
                             if isinstance(entry.get(key), (int, float, str, bool))},
                "loadSeconds": _number(entry.get("loadSeconds")),
                "computeSeconds": _number(entry.get("computeSeconds"))})
        measurements.append(item)
    scales: dict[str, dict[str, int]] = {}
    raw_scales = data.get("scales") if isinstance(data.get("scales"), dict) else {}
    for stage in STAGES:
        scale = raw_scales.get(stage)
        if not isinstance(scale, dict):
            continue
        values = {key: scale.get(key) for key in SCALE_KEYS}
        if all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in values.values()):
            scales[stage] = values
    result: dict[str, Any] = {"measurements": measurements, "scales": scales}
    if v2:
        hosts = {}
        for name, info in list(data["hosts"].items())[:20]:
            if isinstance(name, str) and isinstance(info, dict):
                hosts[name[:MAX_TEXT]] = {key: info.get(key) for key in HOST_INFO_KEYS
                                          if isinstance(info.get(key), (int, float, bool))}
        result.update({"schema": 2, "hosts": hosts})
    return result


def _settings_key(m: dict[str, Any]) -> str:
    return repr(sorted((m.get("settings") or {}).items()))


def fastest_setting(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A candidate's rows at its fastest measured setting; settings are never pooled."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in measurements:
        groups.setdefault(_settings_key(m), []).append(m)
    scale = {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}
    return min(groups.values(), key=lambda rows: estimate_seconds(
        [dict(m, setupSeconds=None) for m in rows], scale) or math.inf)


def _by_candidate(measurements: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in measurements:
        groups.setdefault(m.get("candidate") or m["host"], []).append(m)
    return groups


def parse_plan(data: Any) -> dict[str, Any] | None:
    """A recorded ``plan`` output reduced to what the tab shows; None when unusable."""
    plans = data.get("plans") if isinstance(data, dict) else None
    if not isinstance(plans, dict):
        return None

    def reason(value: Any) -> str:
        return value.strip()[:MAX_REASON] if isinstance(value, str) else ""

    parsed: dict[str, Any] = {}
    for stage in STAGES:
        plan = plans.get(stage)
        if not isinstance(plan, dict):
            continue
        rec = plan.get("recommended") if isinstance(plan.get("recommended"), dict) else None
        span = (rec or {}).get("makespanSeconds") if isinstance((rec or {}).get("makespanSeconds"), dict) else {}
        parsed[stage] = {
            "recommended": None if rec is None else {
                "option": _text(rec.get("option")), "device": _text(rec.get("device")),
                "kind": _text(rec.get("kind")), "reason": reason(rec.get("reason")),
                "processes": rec.get("processes") if isinstance(rec.get("processes"), int) else None,
                "accounts": [a[:MAX_TEXT] for a in rec.get("accounts") or [] if isinstance(a, str)][:10],
                "settings": {k: v for k, v in (rec.get("settings") or {}).items()
                             if k in SETTING_KEYS and isinstance(v, (int, float, str, bool))},
                "low": _number(span.get("low")), "high": _number(span.get("high"))},
            "lost": [{"option": _text(i.get("option")), "reason": reason(i.get("reason"))}
                     for i in plan.get("lost") or [] if isinstance(i, dict)][:MAX_PLAN_ROWS],
            "unmeasured": [{"candidate": _text(i.get("candidate")), "reason": reason(i.get("measureWith"))}
                           for i in plan.get("unmeasured") or [] if isinstance(i, dict)][:MAX_PLAN_ROWS]}
    return {"plans": parsed, "recordedOn": _text(data.get("recordedOn"))}


def estimate_seconds(measurements: list[dict[str, Any]], scale: dict[str, int]) -> float | None:
    """The shared formula for one host's measurements and one stage's scale."""
    if not measurements:
        return None
    if all(m.get("arm") for m in measurements):
        per_arm: dict[str, list[float]] = {}
        for m in measurements:
            per_arm.setdefault(m["arm"], []).append(m["secondsPerUnit"])
        unit = sum(sum(v) / len(v) for v in per_arm.values()) / len(per_arm)
    else:
        unit = sum(m["secondsPerUnit"] for m in measurements) / len(measurements)
    setups = [m["setupSeconds"] for m in measurements if m.get("setupSeconds") is not None]
    setup = sum(setups) / len(setups) if setups else 0.0
    runs = scale["folds"] * scale["seeds"]
    return unit * scale["epochs"] * runs * scale["arms"] + setup * runs


#: (upper bound in seconds, unit divisor, unit name, decimals), first match wins.
_UNITS = ((90, 1, "s", 0), (90 * 60, 60, "min", 1), (48 * 3600, 3600, "h", 1), (math.inf, 86400, "d", 1))


def _unit_for(seconds: float) -> tuple[float, str, int]:
    return next((div, name, dec) for limit, div, name, dec in _UNITS if seconds < limit)


def _amount(seconds: float, div: float, decimals: int) -> str:
    # Spanish UI: decimal comma.
    return f"{seconds / div:.{decimals}f}".replace(".", ",")


def duration_label(seconds: float) -> str:
    div, name, decimals = _unit_for(seconds)
    return f"{_amount(seconds, div, decimals)} {name}"


def range_label(low: float, high: float) -> str:
    """``low – high`` in one unit, the one ``low`` reads best in."""
    div, name, decimals = _unit_for(low)
    return f"{_amount(low, div, decimals)} {name} – {_amount(high, div, decimals)} {name}"


def _product_for(stage: str, products: list[Any]) -> dict[str, Any] | None:
    """The product whose timing record serves ``stage``: one of that kind first, else any with that scale."""
    usable = [p for p in products if isinstance(p, dict) and isinstance(p.get("timing"), dict)
              and stage in (p["timing"].get("scales") or {})]
    usable.sort(key=lambda p: p.get("kind") != stage)
    return usable[0] if usable else None


def _timing_for(stage: str, products: list[Any]) -> dict[str, Any] | None:
    """The timing record for ``stage``: a product of that kind first, else any with that scale."""
    product = _product_for(stage, products)
    return product["timing"] if product else None


def _estimate(rows: list[dict[str, Any]], scale: dict[str, int]) -> dict[str, Any] | None:
    seconds = estimate_seconds(rows, scale)
    if seconds is None:
        return None
    return {"seconds": round(seconds, 6), "low": round(seconds * (1 - RANGE), 6),
            "high": round(seconds * (1 + RANGE), 6)}


def _candidate_rows(stage: str, timing: dict[str, Any] | None, plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One row per candidate for ``stage``: every measured one, then every unmeasured one."""
    scale = (timing or {}).get("scales", {}).get(stage)
    stage_plan = ((plan or {}).get("plans") or {}).get(stage) or {}
    pick = (stage_plan.get("recommended") or {}).get("option")
    lost = {item["option"]: item["reason"] for item in stage_plan.get("lost") or []}
    rows: list[dict[str, Any]] = []
    measured = _by_candidate((timing or {}).get("measurements") or [])
    for name, items in sorted(measured.items()):
        best = fastest_setting(items) if timing.get("schema") == 2 else items
        estimate = _estimate(best, scale) if scale else None
        load = [m for m in best if m.get("loadSeconds") is not None and m.get("computeSeconds") is not None]
        total = sum(m["loadSeconds"] + m["computeSeconds"] for m in load)
        device = best[0].get("device") or "—"
        rows.append({"stage": stage, "candidate": name, "host": best[0]["host"], "family": best[0]["family"],
                     "device": device, "kind": "cpu" if device == "cpu" else "acelerador",
                     "processes": best[0].get("processes") or (int(name.rsplit("-", 1)[1])
                                                               if name.startswith("local-cpu-") else 1),
                     "settings": best[0].get("settings") or {},
                     "load_share": round(sum(m["loadSeconds"] for m in load) / total, 2) if load and total else None,
                     "status": "medido", "estimate": estimate,
                     "estimate_label": f"{range_label(estimate['low'], estimate['high'])} ±20%" if estimate
                     else UNMEASURED,
                     "reason": f"{len(items)} medición(es) propia(s)",
                     "plan": "recomendado" if name == pick else lost.get(name, "")})
    names = set(measured)
    unmeasured: list[tuple[str, str]] = [(i["candidate"], i["reason"]) for i in stage_plan.get("unmeasured") or []
                                         if i.get("candidate")]
    local_info = ((timing or {}).get("hosts") or {}).get("local") or {}
    if not any(n == "local" or n.startswith("local-cpu-") for n in names):
        unmeasured.append(("local-cpu-1", "Corre la sonda de tiempo con el intérprete del objetivo."))
    for name, key in (("local-mps", "mps"), ("local-cuda", "cuda")):
        if local_info.get(key):
            unmeasured.append((name, "El equipo lo tiene: mídelo con la sonda de tiempo antes de elegirlo."))
    families = {m["family"] for items in measured.values() for m in items}
    for family in RUN_HOSTS:
        if family != "local" and family not in families:
            unmeasured.append((family, "Sin medición en este servicio: un ensayo con la sonda la añade."))
    seen = set(names)
    for name, reason in unmeasured:
        if name in seen:
            continue
        seen.add(name)
        rows.append({"stage": stage, "candidate": name, "host": name.split("/", 1)[0],
                     "family": "local" if name.startswith("local") else name.split(":", 1)[0].split("/", 1)[0],
                     "device": "—", "kind": "cpu" if name.endswith("cpu") or name.startswith("local-cpu") else "—",
                     "processes": None, "settings": {}, "load_share": None, "status": UNMEASURED,
                     "estimate": None, "estimate_label": UNMEASURED, "reason": reason, "plan": ""})
    return rows


def _plan_pick(stage: str, plan: dict[str, Any] | None) -> dict[str, Any] | None:
    rec = ((((plan or {}).get("plans") or {}).get(stage)) or {}).get("recommended")
    if not rec or not rec.get("option"):
        return None
    low, high = rec.get("low"), rec.get("high")
    label = f"{range_label(low, high)} ±20%" if low is not None and high is not None else "—"
    return dict(rec, label=label, source=(plan or {}).get("file"), recorded_on=(plan or {}).get("recordedOn"))


def _local_readiness(local: Any) -> dict[str, Any]:
    local = local if isinstance(local, dict) else {}
    workspace = local.get("workspace") if isinstance(local.get("workspace"), dict) else {}
    targets = [t for t in local.get("targets") or [] if isinstance(t, dict)]
    ready = [t for t in targets if t.get("state") == "ready"]
    if ready:
        names = ", ".join(str(t.get("repo")) for t in ready[:6])
        return {"available": True, "reason": f".venv listo con sus librerías: {names}."}
    present = [t for t in targets if t.get("present")]
    if present:
        missing = sorted({str(n) for t in present for n in t.get("missing") or []})
        if missing:
            return {"available": False, "reason": f"Faltan librerías en el .venv: {', '.join(missing[:12])}."}
        return {"available": False, "reason": "Librerías del .venv sin verificar."}
    if not targets and workspace.get("present"):
        return {"available": True, "reason": "Sin objetivo todavía: corre con el entorno micromamba del workspace."}
    if targets:
        return {"available": False, "reason": "Ningún objetivo tiene .venv: la implementación lo crea."}
    return {"available": False, "reason": "Sin entorno micromamba ni .venv de un objetivo."}


def _row(stage: str, host: str, readiness: dict[str, Any], timing: dict[str, Any] | None) -> dict[str, Any]:
    estimate = None
    label = UNMEASURED
    scale = (timing or {}).get("scales", {}).get(stage)
    own = [m for m in (timing or {}).get("measurements") or [] if m.get("family") == host]
    candidate = None
    if scale and own and timing.get("schema") == 2:
        # Each candidate at its fastest setting; the family reads its fastest candidate.
        best = min(((name, fastest_setting(rows)) for name, rows in sorted(_by_candidate(own).items())),
                   key=lambda pair: estimate_seconds(pair[1], scale) or math.inf)
        candidate, own = best
    if scale and own:
        seconds = estimate_seconds(own, scale)
        if seconds is not None:
            low, high = seconds * (1 - RANGE), seconds * (1 + RANGE)
            estimate = {"seconds": round(seconds, 6), "low": round(low, 6), "high": round(high, 6),
                        "measurements": len(own), "source": timing.get("file"),
                        "devices": sorted({m["device"] for m in own if m.get("device")})}
            if candidate is not None:
                estimate["candidate"] = candidate
            label = f"{range_label(low, high)} ±20%"
    return {"stage": stage, "stage_label": STAGE_LABELS[stage], "host": host,
            "host_label": HOST_LABELS.get(host, host), "available": bool(readiness.get("available")),
            "reason": str(readiness.get("reason") or "—"), "estimate": estimate, "estimate_label": label}


def _recommend(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    advice = _place(stage, rows)
    if stage == "poc":
        chosen = next((r for r in rows if r["host"] == advice["host"] and r["estimate"]), None)
        if chosen is None:
            advice["poc_budget"] = "unmeasured"
        elif chosen["estimate"]["high"] <= POC_BUDGET:
            advice["poc_budget"] = "within"
        else:
            advice["poc_budget"] = "exceeds"
            advice["text"] += (" Excede el presupuesto de 5 h de la prueba de concepto: reduce el diseño "
                               "(sujetos, épocas, folds, semillas o brazos) antes de correrla.")
    return advice


def _place(stage: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [r for r in rows if r["available"]]
    local = next((r for r in available if r["host"] == "local"), None)
    remote = [r for r in available if r["host"] != "local"]
    measured = sorted((r for r in remote if r["estimate"]), key=lambda r: r["estimate"]["high"])
    unmeasured_remote = [r["host_label"] for r in remote if not r["estimate"]]
    rehearse = (f" Los hosts remotos ({', '.join(unmeasured_remote)}) necesitan antes un ensayo con "
                "medición de tiempo." if unmeasured_remote else "")
    if local and local["estimate"]:
        if local["estimate"]["high"] <= LOCAL_LIMIT:
            return {"host": "local", "text": f"Local: estimación {local['estimate_label']}, dentro de 20 min."}
        over = f"Local tardaría más de 20 min ({local['estimate_label']}): corre en la nube."
        if measured:
            best = measured[0]
            confirm = (" Antes de la campaña, un ensayo en ese host confirma su tiempo." if stage == "full" else "")
            return {"host": best["host"], "text": f"{over} {best['host_label']}: el más rápido medido "
                                                  f"({best['estimate_label']}).{confirm}"}
        if remote:
            return {"host": remote[0]["host"], "text": f"{over} Corre antes la sonda de tiempo en "
                                                       f"{remote[0]['host_label']} para estimarla."}
        return {"host": None, "text": f"{over} Ningún host en la nube disponible: activa un servicio remoto."}
    if local:
        return {"host": "local", "text": "Local disponible pero sin medir: corre primero la sonda de tiempo "
                                         "(Results/timing.json)." + rehearse}
    if measured:
        best = measured[0]
        return {"host": best["host"],
                "text": f"{best['host_label']}: el más rápido medido y disponible ({best['estimate_label']})."}
    if available:
        best = available[0]
        return {"host": best["host"], "text": f"{best['host_label']} disponible pero sin medir: corre un ensayo "
                                              "con medición de tiempo antes de la corrida."}
    return {"host": None, "text": "Ningún host disponible: prepara el .venv local o activa un servicio remoto."}


def run_options(root: Path | str, view: Any) -> dict[str, Any]:
    """Rows per stage and host, recommendations and the empty-state hint; never raises."""
    view = view if isinstance(view, dict) else {}
    products = view.get("products") if isinstance(view.get("products"), list) else []
    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    picks: dict[str, dict[str, Any] | None] = {}
    recommendations: dict[str, dict[str, Any]] = {}
    sources: set[str] = set()
    for stage in STAGES:
        try:
            product = _product_for(stage, products)
        except Exception:  # noqa: BLE001
            product = None
        timing = product["timing"] if product else None
        plan = product.get("placement_plan") if product and isinstance(product.get("placement_plan"), dict) else None
        try:
            candidates.extend(_candidate_rows(stage, timing, plan))
            picks[stage] = _plan_pick(stage, plan)
        except Exception:  # noqa: BLE001
            picks[stage] = None
        if timing and timing.get("file"):
            sources.add(str(timing["file"]))
        try:
            remote = remote_host_readiness(view.get("remote_services"), stage)
        except Exception:  # noqa: BLE001
            remote = {}
        try:
            local = _local_readiness(view.get("local_environment"))
        except Exception:  # noqa: BLE001
            local = {"available": False, "reason": "No se pudo leer el entorno local."}
        stage_rows = []
        for host in RUN_HOSTS:
            readiness = local if host == "local" else remote.get(host, {"available": False, "reason": "—"})
            try:
                stage_rows.append(_row(stage, host, readiness, timing))
            except Exception:  # noqa: BLE001
                stage_rows.append(_row(stage, host, readiness, None))
        rows.extend(stage_rows)
        recommendations[stage] = _recommend(stage, stage_rows)
    empty = not any(r["estimate"] for r in rows)
    return {"rows": rows, "recommendations": recommendations, "candidates": candidates, "plan_picks": picks,
            "plan_hint": PLAN_HINT, "note": NOTE, "sources": sorted(sources),
            "empty": empty, "empty_hint": EMPTY_HINT, "local_limit_seconds": LOCAL_LIMIT,
            "poc_budget_seconds": POC_BUDGET}
