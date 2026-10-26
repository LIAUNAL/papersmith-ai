---
name: remote-parallelism
description: "Trigger: decide whether a proof of concept or an experiment campaign is worth spreading over several remote GPU accounts, and how to keep the split reproducible. Turns measured inputs (a pilot's per-unit duration, a rehearsal's setup overhead, each account's concurrent sessions, session wall-time limit and weekly GPU quota) into serial and parallel makespans, speed-up, quota per account and a verdict with its threshold stated, plus the reproducibility checklist a split must satisfy before any job is generated, and estimates a stage's processing time from a timing probe before the pilot and before the full run. Reuses remote-execution's placement and launch gate; never places, generates or launches anything. Stdlib-only CLI, no network, no credentials."
---

# Remote parallelism

Whether spreading one campaign over several remote GPU accounts is worth it,
and what keeps the result one experiment rather than several.

Splitting is not free. Every session pays a setup (clone, environment install,
data mount) before its first unit runs, every account has a weekly GPU quota
and a wall-time limit per session, and every extra machine is one more place
where the numerics can drift. So the question is asked with numbers that were
**measured**, never guessed, and answered with a verdict whose threshold is
written beside it. When the verdict is to split, the split is held to a
checklist that keeps it reproducible.

This skill decides and records. It does **not** place units — `distribute`
(`skills/remote-execution/SKILL.md`) still decides which unit goes to which
healthy account under the capacity clamp — and it does not build or start
anything: `generate-job` builds the job folders and `submit` launches them,
behind the operator's consent. A verdict here is never launch authorization.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and
in `OBJECTIVE_FLOW` (`scripts/parallelism_cli.py`), held equal by a test. Every
refusal prints the flow, so a blocked session knows which stage it is behind.

| Stage | Establishes | Behind when |
|---|---|---|
| `measured` | per-unit duration comes from a pilot and setup overhead from a rehearsal, and the accounts' limits and quota are recorded with their date | an input to assess has no pilot, rehearsal or quota reading behind it |
| `assessed` | assess turned those measurements into a verdict with its threshold stated, recorded in the tree it concerns | no .remote-parallelism/assessment-*.json exists in the product or experiments tree |
| `planned` | every reproducibility checklist item holds for the split the verdict calls for | a checklist item is unmet: no declared axis, stamp fields missing from identicalAcrossShards, accelerator not pinned, or an account without a passing rehearsal |

**Arrival:** a recorded verdict — parallelize over N accounts or stay on one — with its reproducibility checklist satisfied, before any job is generated.

**Two stops are a person's:**

1. **The launch.** Nothing here submits. The launch stays behind
   `remote-execution`'s consent token and the implementation skills' `gate`;
   a `parallelize` verdict authorizes nothing.
2. **Which owners take part.** One account per person per service: each
   participating account is owned and operated by a distinct team member
   registered with `smith team add --attest`, and only distinct owners count
   toward `--owners`. Kaggle accounts are also validated through the
   `kaggle-accounts` skill; Colab owners sign in with `smith colab login`.

## Measured inputs

Every input to `assess` is a measurement or a recorded limit, and the CLI
refuses (`missing-input`) rather than assume one:

| Input | Where it comes from |
|---|---|
| `--unit-minutes` | the pilot: the `step` command's `lastRun` for one unit, or the remote ledger's measured duration for a rehearsal — never an estimate |
| `--units` / `--units-file` | the unit list along the declared axis (one seed, fold or subject block per unit); `--units-file` is a JSON list of ids or `{id, minutes}` objects when units differ in length |
| `--owners` | the number of distinct team owners taking part (`smith team list`), each holding one validated account on the campaign's service — parallelism counts owners, never accounts |
| `--accounts` | optional: the accounts those owners hold; any beyond one per owner never add parallelism, and fewer than `--owners` is refused |
| `--service` | optional: the campaign's service (`kaggle` or `colab`); a comma list means mixed services, which the verdict refuses unless `--stamps-identical` |
| `--tiers` | required with `colab`: one compute tier per Colab owner (`free`, `pro`, `payg`, `enterprise`), as `smith team list` records it; `free` owners are excluded from the split |
| `--stamps-identical` | optional: the shards of a mixed-service campaign declare identical environment stamps (accelerator model, CUDA, torch); `verify --shards` still has to confirm them |
| `--sessions-per-account` | concurrent GPU sessions one account may run (the `capacity` the adapter reports) |
| `--session-limit-hours` | one session's wall-time limit |
| `--quota-hours` | one account's weekly GPU quota, operator-supplied or read from the remote service's official MCP accelerator-quota tool; record where with `--quota-source` and when with `--quota-date` |
| `--setup-minutes` | per-session overhead measured by a rehearsal: clone, environment install, data mount |
| `--axis` | the declared distribution axis; `arm` or `comparison` is refused |

## The worth-it rule

`assess` packs the units onto sessions, longest first, each session paying
the setup once and never running past its wall-time limit, and reports three
makespans: `serialMinutes` (one account, one session at a time),
`singleAccountMinutes` (one account using all its concurrent sessions) and
`parallelMinutes` (every account). `speedup` is `singleAccountMinutes /
parallelMinutes` and `savedMinutes` their difference, because the alternative
to splitting is staying on one account, not running one session. Each
account's `gpuHours` counts its setups too, since a session spends quota from
its first minute.

| Verdict | When |
|---|---|
| `split-first` | a unit plus the setup exceeds one session's limit: split it along the declared axis (more units, never by arm) and assess again |
| `do-not-mix` | `--service` names more than one service and `--stamps-identical` is not declared: run the campaign on one service |
| `parallelize` | more than one eligible owner, `speedup >= 1.5`, `savedMinutes >= 30`, and no account exceeds its quota |
| `single-account` | anything else; every unmet condition is named in `reasons` |

The thresholds travel in every output (`thresholds`), so a verdict is read
against them rather than trusted. A campaign that exceeds the quota on every
plan says so in `reasons`: it spans more than one quota week.

## The reproducibility checklist

`checklist` prints it and `assess` carries it as `reproducibilityChecklist`.
A split that misses any item is several experiments that share a table:

- **Split along the declared axis only, never by arm** or by comparison. This
  is `proposal-implementation`'s distribution declaration ("The axis may be
  anything except a comparison"), reused rather than restated.
- **Seed from the unit id.** `int(sha256(unit_id).hexdigest()[:8], 16) %
  2**31`, never from the account, the shard index or the launch order;
  `assess --units-file` prints `unitSeeds` so the job code and the record
  agree.
- **Pin the commit and the environment** identically for every account: one
  published commit, one pinned requirements file.
- **Pin the accelerator.** Request the same accelerator model
  (`machine_shape`) on every account. Different GPU models produce different
  floating-point results, so a campaign whose shards ran on different
  accelerators is stamped and refused at merge.
- **Stamp the environment per shard** — python, torch, CUDA, cuDNN,
  accelerator name, commit, requirements digest, and the data checksum and
  preparation version from the `datasets` skill — and declare those fields
  `identicalAcrossShards` (`stamp-fields` prints them). `verify --shards`
  then refuses a merge over shards that disagree, and `currentWhen` /
  `shardsRoot` keep working as declared.
- **Deterministic flags:** `torch.manual_seed(seed)` per unit,
  `torch.use_deterministic_algorithms(True)`, `CUBLAS_WORKSPACE_CONFIG=:4096:8`
  and `torch.backends.cudnn.benchmark=False`. They cost speed, and some
  operations raise instead of running: measure the pilot with them on.
- **Same dataset version** mounted by every notebook, read through the one
  official preparation.
- **Rehearse once per account.** `readiness` is per worker and never carries
  over from another account; `smoke` each one before the campaign.
- **Never pool timing across machines.** Wall time and memory are
  `perEnvironment`; accuracy pools, seconds do not.
- **One account per person per service** (`one-account-per-person`): see
  "Accounts and terms" below.
- **One service per campaign** (`one-service-per-campaign`): Kaggle and
  Colab shards do not share a campaign unless their environment stamps are
  declared identical and `verify --shards` confirms them.

## Accounts and terms

The team rule: **one account per person per service.** Several accounts take
part only when each one is owned and operated by a distinct team member, who
attests it with `smith team add --owner <slug> --attest` (the registry,
`.papersmith/team.json`, is git-ignored and holds no secret). Parallelism
therefore counts **distinct owners**, never accounts: `--owners` is the
input, and `--accounts` beyond one per owner never add a session.

- **Colab: only paid compute joins a split campaign.** The Colab FAQ
  (https://research.google.com/colaboratory/faq.html, verified 2026-10-25)
  disallows "using multiple accounts to work around access or resource usage
  restrictions" and, on free runtimes without compute units, "running
  distributed computing workers". A `free` account runs interactive or
  proof-of-concept work in one session; it is never a worker of a split. A
  campaign split across owners on Colab needs every participating account on
  `pro`, `payg` (Pay-As-You-Go compute units) or `enterprise`; `assess
  --service colab --tiers ...` excludes the free ones and says why.
- **Kaggle: the same rule until its terms are verified.** Kaggle's terms
  could not be read when this rule was written, so one account per person
  applies there too.
- **Never someone else's account,** and never several of one person's to get
  around per-user limits. If the terms of the service do not allow it, the
  verdict does not matter.

## Estimate before you scale

The pilot and the full run are each preceded by an **estimate shown to the
operator**: before the pilot and before the full run, `estimate` turns a short
timing probe into a processing-time range per stage (`poc`, `full`) and per
host. The range is measurement-derived and never a promise, and it is never
launch authorization.

**The timing probe.** A short run of one epoch of one fold per arm, on the
target's own interpreter (its isolated venv, never the system Python), with the
device it actually ran on recorded. It writes `Results/timing.json` inside the
product folder, declared among the step's produces roots:

```json
{"schema": 1,
 "measurements": [{"measuredAt": "<ISO-8601>", "host": "local" | "<host>:<owner>",
                   "device": "cpu" | "mps" | "cuda:<gpu name>", "arm": "<arm id>",
                   "unit": "epoch", "secondsPerUnit": <float>, "unitsMeasured": <int>,
                   "setupSeconds": <float, optional>}],
 "scales": {"poc":  {"arms": <int>, "folds": <int>, "seeds": <int>, "epochs": <int>},
            "full": {"arms": <int>, "folds": <int>, "seeds": <int>, "epochs": <int>}}}
```

`scales` is copied by the agent from the approved protocol (the experiments
revision) for `full` and from the declared pilot for `poc`; nothing guesses
it. A record with any other shape is refused (`timing-invalid`).

**The one formula.** For a stage `s` and a host `h` with measurements:

```
seconds = mean(secondsPerUnit over h's measurements, per arm)
          × epochs_s × folds_s × seeds_s × arms_s
        + setupSeconds_h × folds_s × seeds_s
```

The mean is taken per arm first and then over the arms, so an arm timed twice
does not outweigh one timed once; `setupSeconds_h` is the mean of the
measurements that record it, 0 when none does. The output is a range, `low`
to `high`, ±20%, single-probe extrapolation — never a point claim.

**Remote hosts are measured, never scaled.** A host with no measurement reads
`unmeasured`; a remote estimate requires a measured rehearsal on that host,
whose timing lands in the same record under its own `host` slug. Local timings
are never multiplied by a guessed factor to stand in for a remote one, and one
host timed on two devices is refused (`mixed-devices`), because timing never
pools across machines.

**Placement rules: twenty minutes, five hours.** Both read each estimate's
upper bound (`high`), so a stage is placed by the conservative end of its
range, and both are stated in every output as `placementRules`
(`{localLimitSeconds: 1200, pocBudgetSeconds: 18000, bound: "high"}`).

- **A stage over 20 minutes locally runs on a cloud host.** When the local
  `high` is at most 1200 s the stage stays local; otherwise `placement` names
  the fastest measured cloud host, or none with a request to time one first.
  Local unmeasured places nothing: the local probe comes first.
- **A proof of concept fits in 5 hours on the host it runs on.** For `poc`,
  `placement.pocBudget` is `within`, `exceeds` or `unmeasured`, judged on the
  host the stage is placed on. `exceeds` means the design is reduced —
  subjects, epochs, folds, seeds or arms — before the proof of concept runs,
  never that it runs longer.

A placement is never launch authorization: the operator still authorizes
every remote run.

## Accepted operations

```
python3 skills/remote-parallelism/scripts/parallelism_cli.py [--root <workspace>] <verb> ...
```

| Verb | What it does |
|---|---|
| `assess` | `--units N --unit-minutes M --owners N --sessions-per-account S --session-limit-hours H --quota-hours Q --setup-minutes O [--accounts A] [--service kaggle\|colab[,...]] [--tiers free,pro,...] [--stamps-identical] [--units-file units.json] [--axis <name>] [--quota-source <text>] [--quota-date YYYY-MM-DD] [--record <dir>]`: JSON `{inputs, thresholds, serialMinutes, singleAccountMinutes, parallelMinutes, speedup, savedMinutes, accountsUsed, recommendedAccounts, perAccount[{account, units, gpuHours, overQuota}], quotaOk, unitsOverSessionLimit, eligibleOwners, excludedOwners[{owner, tier}], verdict, reasons, unitSeeds?, reproducibilityChecklist, stampFields, launchAuthorization: false}`; each `perAccount` entry is one eligible owner's account. `--record <dir>` writes `<dir>/.remote-parallelism/assessment-<date>.json` (a second one the same day gets `-2`, never an overwrite); `<dir>` must resolve inside the workspace, through no symlink that leaves it |
| `estimate` | `--timing <path to timing.json> [--stage poc\|full\|both] [--host <host>:<owner> ...] [--record <dir>] [--json]`: JSON `{estimates: {stage: {host: {seconds, low, high, formula, measurements, device, secondsPerUnit, perArm, setupSeconds} \| "unmeasured"}}, placement: {stage: {where: "local"\|"cloud"\|null, host, reason, pocBudget?: "within"\|"exceeds"\|"unmeasured"}}, placementRules, timing, range, unmeasuredMeans, launchAuthorization: false}`; `local` and every host the record measured are always reported, and each `--host` named adds a row (`unmeasured` when the record has no measurement of it). `--record <dir>` writes `<dir>/.remote-parallelism/estimate-<date>.json` under the same containment as `assess`, and then `--timing` too must resolve inside the workspace, through no symlink that leaves it |
| `checklist` | the reproducibility checklist as JSON |
| `stamp-fields` | the shard stamp fields to declare `identicalAcrossShards` |

Success prints one JSON object on stdout. A refusal prints
`{"error", "message", "objective"}` on stderr and exits 2.

### Error codes

| Error code | Meaning |
|---|---|
| `missing-input` | a measured input was not given; it is never guessed |
| `bad-argument` | an input is not a number, or not positive (setup may be zero) |
| `units-file-missing` | `--units-file` names no file |
| `units-file-invalid` | the units file is not a non-empty JSON list of ids or `{id, minutes}` objects |
| `duplicate-unit` | a unit id appears twice in the units file |
| `units-mismatch` | `--units` disagrees with the units file's count |
| `axis-is-comparison` | `--axis` is an arm or a comparison |
| `record-outside-workspace` | `--record` resolves outside the workspace, or its record folder is a link |
| `record-missing` | `--record` is not an existing directory |
| `timing-missing` | `--timing` names no file: run the timing probe first |
| `timing-invalid` | the timing record is not schema 1: wrong schema, a missing or unknown key, a non-positive duration, a unit other than `epoch`, a bad host or device, or `scales` without both stages |
| `mixed-devices` | one host was timed on more than one device; timing is never pooled across machines |
| `timing-outside-workspace` | with `--record`, `--timing` resolves outside the workspace |

## Compatibility

Runs unchanged under **Claude Code, OpenCode and Pi**: plain `python3`, no
third-party imports, no network and no credentials. The agents of the proof
of concept and the experiments load this file before generating jobs for more
than one unit.

## Output Reporting

For `estimate`, report each stage's range per host with its formula and
device, every host that reads `unmeasured`, and that the range is an estimate
shown before the pilot or the launch, never authorization. For `assess`,
report the verdict, the speed-up and saved minutes against their thresholds,
each account's units and GPU hours, every reason, the checklist items still
unmet, and the recorded path. Speak the user's language; flags, paths and
field names are never translated.
