## A diagram that compiles, or says why: `render` and `place` (the whole-paper review)

**Reviewing the whole paper as a main-track reviewer delegates to the `paper-reviewer` agent.**
Once every section is written and `paper/main.tex` compiles, it fills the
main-track review form — summary, contribution type, strengths
and weaknesses, the four 1-4 ratings, questions, limitations, overall,
confidence, ethics and formatting — and backs pertinence, novelty, coherence,
and adjusted novelty concordance (ensuring the problem, title, abstract, and introduction
claim no more than the verified findings and the verdicts in `Results/discussion.json` support)
with quotes from the paper, the accepted proposal, the experiments'
results and the SOTA pool. It never edits the paper and never claims a lack of
novelty without naming the reference that holds the idea.

**Record each review round.** The agent returns the review as a `round` JSON
object and writes nothing; save it to a scratch file and run
`python skills/paper-writing/scripts/paper_cli.py review --input <file>`
(`-` reads stdin). The verb numbers and dates the round and appends it to
`.papersmith/paper_review.json`, which the dashboard's final-judge panel in the
PDF preview tab reads. From the second round on, the round must judge every
revision the previous one raised (`items`, one verdict per `rank`):
`REVIEW_ITEMS_MISSING` names the ranks without a verdict and
`REVIEW_ITEM_UNKNOWN` the ranks the previous round never raised.
`REVIEW_ROUND_INVALID` lists every out-of-range or missing field, and
`REVIEW_FILE_INVALID` reports an existing file that cannot be read or holds a
round that is not an object (never overwritten), or a history that would grow
past the dashboard's 2 MB cap with this round. A refused round leaves the file unchanged: send the agent's
round back with the refusal detail rather than editing it yourself.

**A review paper is judged on its own rubric.** A round declares the form it
was judged on in `rubric`: absent (or `ml-conference`) it is the main-track
form above, validated and stored exactly as always. In a review workspace
(`paper_kind: review` in `.papersmith/config.json`) the `paper-reviewer`
returns a `"rubric": "systematic-review"` round instead: no `overall`,
`confidence` or `ratings`, but `amstar2`, one `{"item", "answer",
"justification"}` per AMSTAR 2 item 1-16 (Shea et al., 2017, BMJ 358:j4008),
`answer` one of `yes`, `partial yes` (items 2, 4, 7, 8, 9 only), `no` or `not
applicable` (items 11, 12, 15 only, without a meta-analysis; items 9 and 13
too when `review/protocol.json` declares a `review_type` containing `scoping`
or `bibliometric`, any case, a review that appraises no risk of bias); and
`prisma_gaps`, `{"item": 1-27, "gap"}` per PRISMA 2020 item the manuscript
does not fully report (Page et al., 2021, BMJ 372:n71). The verb marks the
seven critical domains (items 2, 4, 7, 9, 11, 13, 15) and derives the
`overall_confidence` by the AMSTAR 2 rule from the `no` answers, storing
`critical_flaws` and `non_critical_weaknesses` beside it: no or one
non-critical weakness is `high`, more than one `moderate`, one critical flaw
`low`, more than one `critically low` (`partial yes` and `not applicable`
count as neither). The round also stores `amstar2_basis`, `{"protocol":
"review/protocol.json", "review_type", "risk_of_bias_not_applicable"}`: the
review type the verb read (null when the protocol, the key or a text value is
missing) and whether items 9 and 13 could be `not applicable`; any other review
type, or no readable protocol, keeps both applicable. A round may state `overall_confidence`, but one that
disagrees with the rule is refused (`REVIEW_ROUND_INVALID`), as are a missing
or repeated item, an answer outside the scale or where AMSTAR 2 does not offer
it, an empty justification and a gap without an item 1-27. `recommendation`,
`items`, `revisions`, `excluded` and `report` keep their rules on both
rubrics, so a review round from the second on still judges every revision the
previous round raised. The PDF tab's final-judge panel shows the confidence,
the flaws and weaknesses, the sixteen answers and the PRISMA gaps of such a
round.

**Each line has one rubric, and the verb checks it.** The verb reads the
workspace's line (`paper_kind` in `.papersmith/config.json`, `experimental`
when unset) and judges a round without `rubric` on that line's rubric:
`ml-conference` for `experimental`, `systematic-review` for `review`,
`empirical-study` for the empirical lines (`observational-measurement`,
`experiment-intervention`), `measurement-science` for `hardware` and
`lab-simulation`, `data-descriptor` for `data-resource`, `qualitative-study`
for `qualitative-participatory`. A round whose rubric does not serve the
line is refused with `RUBRIC_KIND_MISMATCH`, whose detail names the line's
rubric, and a line no rubric serves with `RUBRIC_LINE_UNKNOWN`; an unknown
rubric id stays `REVIEW_ROUND_INVALID`. The mapping is data
(`paper_review.RUBRICS`): a new line joins a rubric by adding its id there.

**An empirical paper is judged on the empirical-study rubric.** The
`paper-reviewer` returns a `"rubric": "empirical-study"` round: no `overall`,
`confidence` or `ratings`, but `protocol_adherence` (`primary_outcome` and
`analysis_plan`, each `followed`, `deviated` or `no protocol` against the
locked study protocol; `deviations`, `{"deviation", "declared": true|false}`,
required when either is `deviated`; a `justification`), `design_validity`
(`rating` one of `adequate`, `limited`, `inadequate`, and a `justification`),
`risk_of_bias` (one `{"domain", "rating", "justification"}` per domain
`selection`, `measurement`, `confounding`, `missing data`, `reporting`,
`rating` one of `low`, `some concerns`, `high`), and `checklist` with
`checklist_gaps`, `{"item", "gap"}` per item of the line's reporting
checklist the manuscript does not fully report, the item by its number (`12`
or `12b`). The verb counts the `undeclared_deviations` and derives
`overall_risk_of_bias`: any `high` domain is `high`, else any `some concerns`
is `some concerns`, else `low`. A round may state it, but one that disagrees
with the rule is refused (`REVIEW_ROUND_INVALID`), as are a missing or
repeated domain, a rating outside the scale, an empty justification, a
`deviated` answer with no deviation listed, a gap without an item number and
gaps without a named checklist. The shared fields keep their rules. The PDF
tab's final-judge panel shows the overall risk of bias, the adherence and its
deviations, the design validity, the domains and the checklist gaps.

**A hardware or lab-simulation paper is judged on the measurement-science
rubric.** The `paper-reviewer` returns a `"rubric": "measurement-science"`
round: no `overall`, `confidence` or `ratings`, but five criteria, each
`{"rating", "justification"}` with `rating` one of `adequate`, `limited`,
`inadequate`: `design_validity`, `calibration_traceability` (instruments
calibrated and traceable, reference values used), `uncertainty` (a budget per
reported quantity with type A and type B components, combined and expanded
with its coverage factor), `reproducibility` (design files, data, code and
protocol available under a licence) and `agreement` (for hardware, agreement
with a reference device with its bias and limits of agreement; for
lab-simulation, calibration against known values), which alone may also be
`not applicable`, its justification giving the reason; plus `checklist_gaps`,
`{"item", "gap"}`, by item number (`7` or `7b`) in the line's checklist. The
verb fills `checklist` with that checklist (`hardwarex` for hardware,
`gum-reporting` for lab-simulation) and refuses a round that names another, and
derives `overall_rating`: any `inadequate` criterion is `major concerns`, else
any `limited` is `minor concerns`, else `sound` (`not applicable` counts as
neither). A round may state it, but one that disagrees with the rule is refused
(`REVIEW_ROUND_INVALID`), as are a missing criterion, a rating outside its
scale, an empty justification and a gap without an item number. The shared
fields keep their rules. The PDF tab's final-judge panel shows the overall
rating, the five criteria and the checklist gaps.

**A data-resource paper is judged on the data-descriptor rubric.** The
`paper-reviewer` returns a `"rubric": "data-descriptor"` round: no `overall`,
`confidence` or `ratings`, but five criteria, each `{"rating",
"justification"}` with `rating` one of `adequate`, `limited`, `inadequate`
(none may be `not applicable`): `documentation_completeness` (data records,
data dictionary and datasheet describe every file, variable and unit),
`collection_consent` (the collection protocol, and the ethics approval,
consent or own-data statement and the source licences), `technical_validation`
(the quality checks and technical validation, baselines labelled),
`access_licence` (deposited under a licence with a persistent identifier, the
access conditions stated) and `reuse_potential` (usage notes, code
availability, the uses the data supports); plus `checklist_gaps`, `{"item",
"gap"}`, by item number (`4` or `4b`) in `datasheets`. The verb fills
`checklist` with `datasheets` and refuses a round that names another, and
derives `overall_rating` by the measurement-science rule: any `inadequate`
criterion is `major concerns`, else any `limited` is `minor concerns`, else
`sound`. A round may state it, but one that disagrees with the rule is refused
(`REVIEW_ROUND_INVALID`), as are a missing criterion, a rating outside the
scale, an empty justification and a gap without an item number. The shared
fields keep their rules. The PDF tab's final-judge panel shows the overall
rating, the five criteria and the datasheets gaps.

**A qualitative-participatory paper is judged on the qualitative-study
rubric.** The `paper-reviewer` returns a `"rubric": "qualitative-study"` round:
no `overall`, `confidence` or `ratings`, but a `variant`
(`qualitative-mixed`, `consensus-foresight` or `experience-report`) and the
criteria that variant rates, each `{"rating", "justification"}` with `rating`
one of `adequate`, `limited`, `inadequate`. Every variant rates
`reflexivity` (the researchers' position and influence), `sampling_sufficiency`
(who, why, and when sampling stopped), `analytic_rigour` (codebook, how the
themes were derived, who signed them off), `quote_claim_fit` (every claim
supported by verbatim data) and `transferability` (the context described so
readers can judge); `consensus-foresight` adds `panel_composition`,
`consensus_threshold` (pre-specified), `rounds_feedback` and
`dissent_reported`; `experience-report` adds `context`, `what_was_done`,
`what_it_taught` and `honest_limits` (no effect claimed without an
evaluation). Only an experience report may rate `sampling_sufficiency` or
`quote_claim_fit` `not applicable` (no participant data), the justification
then the reason; a criterion of another variant is refused. The variant must
be the one the operator agreed (`agreed_variant` in
`.papersmith/paper_type.json`); a round that names none takes it, and is
refused when none is agreed. The verb fills `checklist` with the variant's
checklist (`srqr` for `qualitative-mixed`, which may name `coreq` instead;
`accord` for `consensus-foresight`) and refuses any other; an experience
report has no checklist (stored null) and lists no `checklist_gaps`. It
derives `overall_rating` by the measurement-science rule (`not applicable`
counts as neither); a round that states a different one is refused
(`REVIEW_ROUND_INVALID`), as are a missing criterion, a rating outside the
scale, an empty justification and a gap without an item number. The shared
fields keep their rules. The PDF tab's final-judge panel shows the variant,
the overall rating, the criteria and the checklist gaps.

**Measure this before delegating (paper-reviewer):** confirm `paper/main.tex`
exists and no section under `sections/` is empty, and note whether
`paper/main.pdf` and `sota-pool/candidates.json` exist; a reviewer asked to
judge an unfinished paper or novelty without a pool cannot tell a weak paper
from a missing input. In a review workspace note instead whether
`review/protocol.lock.json` and `review/prisma.json` exist: AMSTAR 2 judges
the protocol and the flow the paper reports against those records. On an
empirical line note whether a locked study protocol exists under `protocol/`:
without it the reviewer answers `no protocol` on adherence. On a hardware or
lab-simulation line note whether `study/instruments.json` and the registered
raw measurement files exist: calibration, uncertainty and agreement are judged
against them. On a data-resource line note whether the data dictionary, the
quality-check results and the deposit record (`datasets_cli.py deposit`) exist
under `datasets/`: documentation, validation and access are judged against
them. On a qualitative-participatory line note the agreed variant
(`.papersmith/paper_type.json`) and whether the qualitative records exist
(`skills/_core/qualitative/qual_cli.py`: the registered transcripts, the
codebook versions and the theme sign-off, or the consensus rounds): the audit
trail and the fit between quotes and claims are judged against them.
