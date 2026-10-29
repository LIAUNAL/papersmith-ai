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
| `--account` | instead of the uniform limits: one account with its own limits, `<owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>]`, repeated once per account; `quota_hours` may be `unknown`, and a `colab` account carries its tier |
| `--accounts-file` | the same accounts as a JSON list of `{owner, service, sessions, sessionHours, quotaHours, tier?, quotaSource?, quotaDate?}` |

With `--account` or `--accounts-file`, each account brings its own concurrent
sessions, session wall time and weekly quota, and the uniform flags
(`--owners`, `--accounts`, `--sessions-per-account`, `--session-limit-hours`,
`--quota-hours`, `--tiers`) are refused beside them. Owners are counted from
the accounts: a second account of one owner on one service is left out, and a
free-tier Colab account is excluded exactly as `--tiers` excludes it.
`--service` then filters the accounts to the campaign's service. Without
either flag, `assess` reads the uniform flags and prints exactly what it
always printed.

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
| `split-first` | a unit plus the setup exceeds 80% of one session's limit (the session-fit margin): split it along the declared axis (more units, never by arm) and assess again, or declare its step resumable in a `schedule` plan |
| `do-not-mix` | `--service` names more than one service and `--stamps-identical` is not declared: run the campaign on one service |
| `parallelize` | more than one eligible owner, `speedup >= 1.5`, `savedMinutes >= 30`, and no account exceeds its quota |
| `single-account` | anything else; every unmet condition is named in `reasons` |

The thresholds travel in every output (`thresholds`), so a verdict is read
against them rather than trusted. A campaign that exceeds the quota on every
plan says so in `reasons`: it spans more than one quota week.

Under per-account limits a unit only goes to an account whose session can
hold it with its setup inside the margin, `split-first` reads the longest session among the
eligible accounts, the single-account baseline is the eligible account that
finishes the campaign soonest alone (`baselineAccount`), and each
`perAccount` entry carries its own `owner`, `service`, `sessions`,
`sessionLimitHours` and `quotaHours`. An account whose quota is `unknown` is
reported `overQuota: null` and named in `reasons`: it is not checked, and it
has to be recorded before the launch.

## Every unit fits one session with margin, or resumes

A service stops a session at its continuous-run limit, and a reclaimed or
timed-out session loses every minute since the last thing it wrote. So the
rule for every agent that plans, builds or walks a remote campaign:

- **One unit, one session, with margin.** A unit's upper-bound duration plus
  its setup must end inside **80%** of its account's session limit
  (`SESSION_MARGIN_PERCENT`). The remaining 20% absorbs a slower node, a
  queue, a late checkpoint and the result upload. `assess` reports such units
  in `unitsOverSessionLimit` with the verdict `split-first`, and its reason
  names the margin; `schedule` refuses the plan with
  `unit-over-session-margin`, naming the step, the unit's duration, its setup
  and the limit (`unit-over-session-limit` when the unit does not fit even the
  whole session).
- **A long unit is split** along the declared axis — by fold, seed or subject
  block, never by arm — so each piece fits one session with margin, and the
  campaign is assessed or scheduled again.
- **Or it checkpoints and resumes.** A step whose units write a checkpoint and
  resume from it declares `"resumable": true` with `"checkpointMinutes": <the
  minutes of work between two checkpoints>`. `schedule` then plans each unit
  as `ceil(unitMinutes / (80% of the session limit − setup))` chained sessions
  on the **same account**, one after another, and each chained session pays
  the setup again. The step reports `resumable`, `checkpointMinutes` and
  `sessionsPerUnit` per service, its shares count every chained session, and
  `reasons` names the chain. A checkpoint interval longer than one session's
  usable work is refused with `unit-over-session-margin`: the session would
  end before its first checkpoint. A resumable step whose units already fit
  one session plans exactly as an undeclared one.

The declaration is a promise about the target's code, not about this CLI: the
unit really writes its checkpoint at least every `checkpointMinutes`, stops
starting new work before the session's deadline, and resumes from the last
checkpoint in the next session.

## Planning a project's remote steps

`assess` answers for one campaign. `schedule` answers for the project: given
its remote steps, it puts each step on **one** service and its units on that
service's accounts so the whole project ends as early as possible. It is
read-only — no record, no job, no launch — and its plan is never launch
authorization; each step still goes through its own `distribute`, rehearsal,
`gate` and `submit` behind the operator's consent.

The plan (`--plan plan.json`, schema 1):

```json
{"schema": 1,
 "setupMinutes": <number or {service: number}, optional default>,
 "steps": [{"id": "<step id>", "units": <int>, "services": ["<service>", ...],
            "unitMinutes": {"<service>": <minutes>},
            "timing": {"<service>": {"path": "Results/timing.json", "host": "<service>:<owner>", "stage": "poc" | "full", "candidate": "<optional>"}},
            "requires": ["<step id>", ...], "setupMinutes": <number or {service: number}>,
            "stampsIdentical": false, "axis": "<seed | fold | subject block>",
            "resumable": false, "checkpointMinutes": <minutes, only with "resumable": true>}],
 "accounts": [{"owner": "<slug>", "service": "<service>", "sessions": <int>,
               "sessionHours": <hours>, "quotaHours": <hours> | "unknown", "tier": "<colab tier>"}]}
```

- **Durations are per service and measured.** Each allowed service needs its
  own per-unit duration, either explicit (`unitMinutes`) or from that
  service's own host in a schema-1 timing record (`timing`): the stage's work
  at the estimate's upper bound (+20%) divided over the step's units, setup
  excluded. A timing host of another service, or an unmeasured one, is
  refused: timing is never pooled across machines. On a schema 2 record a
  host holding several candidates needs `candidate` named, and the
  candidate's fastest measured setting is the one read. A setup is required
  (`setupMinutes`, per step or for the plan).
- **One service per step.** Every step runs on one of its `services`; it runs
  on several only when it declares `stampsIdentical`, and then `reasons` says
  `verify --shards` still has to confirm them. Parallelism across services
  therefore happens between steps, and within a step across the accounts of
  its service.
- **Session fit.** A unit goes only to a session whose limit holds it plus its
  setup inside the 80% margin; past it the plan is refused unless the step
  declares `resumable`, and then the unit is chained over sessions of one
  account (see "Every unit fits one session with margin, or resumes").
- **Dependencies.** A step starts only when every step it `requires` has
  ended; an unknown step or a cycle is refused.
- **Accounts.** From the plan, `--account` or `--accounts-file`, under the
  team rule: one account per owner per service, free-tier Colab excluded.
  Each account offers `sessions` concurrent slots, each opening a new session
  (and paying the step's setup on its service) when it changes step or would
  run past `sessionHours`.
- **The search.** Every assignment of steps to services is simulated (step
  by step above 4096 assignments): ready steps are taken earliest first, each
  unit goes to the slot where it finishes earliest, ties to the lowest slot.
  The plan kept has the smallest makespan, then the fewest accounts over
  quota, then the fewest GPU hours — so the same plan always prints the same
  output. `serialMinutes` is every step one after another on one session at a
  time of its fastest eligible account; `speedup` is serial over makespan.
- **Quota.** Each account's `gpuHours` (setups included) is checked against
  its own weekly quota and an overrun is flagged (`overQuota`, `quotaOk`,
  `reasons`); an `unknown` quota is reported unchecked, and a plan longer than
  a week says it spans quota resets.

The output: `{steps[{id, units, requires, services, allowedServices,
unitMinutes, unitMinutesSource, setupMinutes, readyMinutes, startMinutes,
endMinutes, durationMinutes, shares[{account, owner, service, units,
slotsUsed, sessions}], resumable?, checkpointMinutes?, sessionsPerUnit?}],
makespanMinutes, makespanHours, serialMinutes,
serialHours, speedup, savedMinutes, quota[{account, owner, service, units,
gpuHours, quotaHours, overQuota}], quotaOk, accounts, excludedAccounts,
ignoredAccounts, search, doctrineChecks[{id, held, detail}], reasons,
launchAuthorization: false}`. `doctrineChecks` names the rules the plan
applied — `axis-not-arm`, `one-service-per-campaign`,
`one-account-per-person`, `no-pooled-timing`, `launch-is-the-operator-s` —
and `rehearse-each-account` with `held: null`: readiness is per worker and
is checked at each step's gate, never here.

**Worked example: one Colab Pro account and two Kaggle accounts.** One
owner holds Colab Pro (one session, 24-hour sessions, quota `unknown`) and a
Kaggle account; a teammate holds the second Kaggle account (each Kaggle
account two sessions, 12-hour sessions, 30 hours a week). The project has a
hyperparameter search `hpo_search` (25 units: 5 arms x 5 folds, 30 trials
each) and three experiments `e1_run`, `e2_run`, `e3_run` (25 units each)
that require it. Assumed durations, to be replaced by measured ones: a search
unit takes 40 minutes on Colab and 60 on Kaggle, an experiment unit 20 and
30, and a setup 8 and 10.

```
python3 skills/remote-parallelism/scripts/parallelism_cli.py schedule --plan plan.json
```

| Step | Service | Start → end (min) | Units per account |
|---|---|---|---|
| `hpo_search` | kaggle | 0 → 430 | kaggle:amalvarezme 13 (2 slots), kaggle:teammate 12 (2 slots) |
| `e1_run` | colab | 430 → 938 | colab:amalvarezme 25 (1 slot) |
| `e2_run` | kaggle | 430 → 650 | kaggle:amalvarezme 13, kaggle:teammate 12 |
| `e3_run` | kaggle | 620 → 840 | kaggle:amalvarezme 13, kaggle:teammate 12 |

Makespan 938 minutes (15.6 h) against 2532 serial (42.2 h): speed-up 2.7.
Quota: kaggle:amalvarezme 27 of 30 hours, kaggle:teammate 25 of 30,
colab:amalvarezme 8.47 hours against an unknown quota, which `reasons` asks to
record before the launch. The search stays on one service because splitting
it across Colab and Kaggle would mix accelerators inside one campaign; Colab
works while Kaggle runs two experiments, and nothing is launched.

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

**The probe that writes it.** `scripts/timing_probe.py` ships with this
skill and runs under the target's own interpreter against the target's own
epoch function (`--entry <module>:<function>`, called as
`epoch(settings, wrap)` and iterating its loader through `wrap`):

```
<target>/.venv/bin/python skills/remote-parallelism/scripts/timing_probe.py \
    --path <target>/src --entry <package>.<module>:<function> --arm <arm id> \
    --out <target>/<Name>/Results/timing.json [--candidates local-cpu-1,local-cpu-4,local-mps] \
    [--batch-sizes 32,128] [--num-workers 0,4] [--pin-memory false,true] [--prefetch 2] \
    [--threads 4] [--dtype float32] [--data-source raw,cached] [--cap-seconds 300] [--scales '<json>']
```

It times one epoch per candidate and setting, `local-cpu-<N>` as N
concurrent processes each timed under the others' contention, and splits
every epoch into the wait for batches and the compute. Each candidate's sweep
stops at its time cap (300 s by default; the first setting always runs, and
every setting past the cap is listed under `skipped`). An accelerator the
machine lacks is skipped, never run on the CPU under its name. Without
`--candidates` it measures the local CPU (one process and half the cores)
and every accelerator the machine has. It writes only `Results/timing.json`,
appending to it (a schema 1 record is upgraded and keeps its rows), and
takes `--scales` only for a new record. It never picks a device: a target
reads its device from `plan`'s measured recommendation
(`timing_probe.device_from_plan`), and with no plan there is no choice. A
target may vendor the file to run it on a remote machine with `--host
<host>:<owner>` and a `<host>:<owner>/<machine>` candidate.

**Schema 2: one row per candidate.** The probe writes schema 2, and schema 1
records keep loading with unchanged outputs. Schema 2 adds
`hosts` (`{"<host>": {"cpuCount", "ramGB", "mps", "cuda"}}`) and, per
measurement, optional keys: `candidate` (`local-cpu-<processes>`,
`local-mps`, `local-cuda` or `<host>:<owner>/<machine>`, where a machine
named `cpu` is a CPU-only session), `threads`, `processes`, `batchSize`,
`numWorkers`, `pinMemory`, `prefetch`, `dtype`, `dataSource` (`raw` or
`cached`), and `loadSeconds` + `computeSeconds`, the epoch split into time
spent waiting on data and time spent computing. A candidate must agree with
its host and device: `local-cpu-*` records `cpu`, a remote `/cpu` machine
records `cpu`, and an accelerator machine records the accelerator that
arrived. `estimate` then adds `candidateEstimates: {stage: {candidate:
{…, candidate, processes, settings, settingsMeasured, loadShare}}}`, each
from the candidate's own rows at its fastest measured setting (settings are
never pooled), and each host's row in `estimates` is its fastest candidate.
The estimate stays serial work; `plan` counts processes and accounts.

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
pools across machines. On schema 2 the refusal is keyed by candidate: one
host may hold `local-cpu-4` and `local-mps` rows, and one candidate timed on
two devices is refused.

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
| `assess` | `--units N --unit-minutes M --owners N --sessions-per-account S --session-limit-hours H --quota-hours Q --setup-minutes O` or, with each account's own limits, `--units N --unit-minutes M --setup-minutes O --account <owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>] ...` (or `--accounts-file accounts.json`), then `[--accounts A] [--service kaggle\|colab[,...]] [--tiers free,pro,...] [--stamps-identical] [--units-file units.json] [--axis <name>] [--quota-source <text>] [--quota-date YYYY-MM-DD] [--record <dir>]`: JSON `{inputs, thresholds, serialMinutes, singleAccountMinutes, parallelMinutes, speedup, savedMinutes, accountsUsed, recommendedAccounts, perAccount[{account, units, gpuHours, overQuota}], quotaOk, unitsOverSessionLimit, eligibleOwners, excludedOwners[{owner, tier}], verdict, reasons, unitSeeds?, reproducibilityChecklist, stampFields, launchAuthorization: false}`; each `perAccount` entry is one eligible owner's account. `--record <dir>` writes `<dir>/.remote-parallelism/assessment-<date>.json` (a second one the same day gets `-2`, never an overwrite); `<dir>` must resolve inside the workspace, through no symlink that leaves it |
| `estimate` | `--timing <path to timing.json> [--stage poc\|full\|both] [--host <host>:<owner> ...] [--record <dir>] [--json]`: JSON `{estimates: {stage: {host: {seconds, low, high, formula, measurements, device, secondsPerUnit, perArm, setupSeconds} \| "unmeasured"}}, placement: {stage: {where: "local"\|"cloud"\|null, host, reason, pocBudget?: "within"\|"exceeds"\|"unmeasured"}}, placementRules, timing, range, unmeasuredMeans, launchAuthorization: false}`; `local` and every host the record measured are always reported, and each `--host` named adds a row (`unmeasured` when the record has no measurement of it). `--record <dir>` writes `<dir>/.remote-parallelism/estimate-<date>.json` under the same containment as `assess`, and then `--timing` too must resolve inside the workspace, through no symlink that leaves it |
| `schedule` | `--plan <plan.json> [--account <owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>] ...] [--accounts-file accounts.json]`: places each remote step on one service and its units on that service's accounts, honouring `requires`, for the smallest makespan; JSON `{steps[{id, services, startMinutes, endMinutes, shares[...]}], makespanMinutes, serialMinutes, speedup, savedMinutes, quota[{account, gpuHours, quotaHours, overQuota}], quotaOk, excludedAccounts, search, doctrineChecks, reasons, launchAuthorization: false}` (see "Planning a project's remote steps"); read-only, writes nothing |
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
| `timing-invalid` | the timing record is not schema 1 or 2: wrong schema, a schema 2 record without `hosts`, a candidate that disagrees with its host or device, a missing or unknown key, a non-positive duration, a unit other than `epoch`, a bad host or device, or `scales` without both stages |
| `mixed-devices` | one host (schema 1) or one candidate (schema 2) was timed on more than one device; timing is never pooled across machines |
| `timing-outside-workspace` | with `--record`, `--timing` resolves outside the workspace |
| `accounts-invalid` | an `--account` or accounts-file entry is malformed: a bad owner or service, non-positive sessions or hours, a quota that is neither positive nor `unknown`, a `colab` account without its tier, or a tier on another service |
| `accounts-file-missing` | `--accounts-file` names no file |
| `plan-missing` | `schedule --plan` names no file |
| `plan-invalid` | the plan is not schema 1: an unknown key, a bad step, a `requires` naming an unknown step or forming a cycle, or a timing source on another service's host or unmeasured |
| `no-eligible-account` | a step's services have no eligible account (free-tier Colab and second accounts of one owner never count) |
| `unit-over-session-limit` | one unit plus its setup exceeds every eligible session: split it along the declared axis or declare the step resumable |
| `unit-over-session-margin` | one unit plus its setup exceeds 80% of every eligible session's limit, or a resumable step's checkpoint interval exceeds one session's usable work: split it along the declared axis or declare (or tighten) its checkpoint |

## Compatibility

Runs unchanged under **Claude Code, OpenCode and Pi**: plain `python3`, no
third-party imports, no network and no credentials. The agents of the proof
of concept and the experiments load this file before generating jobs for more
than one unit.

## Output Reporting

For `schedule`, report each step's service, window and per-account units,
the makespan against the serial one, every account's GPU hours against its
quota (overruns and unknown quotas named), each doctrine check, and that the
plan is never launch authorization. For `estimate`, report each stage's range per host with its formula and
device, every host that reads `unmeasured`, and that the range is an estimate
shown before the pilot or the launch, never authorization. For `assess`,
report the verdict, the speed-up and saved minutes against their thresholds,
each account's units and GPU hours, every reason, the checklist items still
unmet, and the recorded path. Speak the user's language; flags, paths and
field names are never translated.
