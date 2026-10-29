### `nextStep: "benchmark"` — propose the wiring, then train both and measure

Only reachable once `backend.trainable` is true and a baseline exists.

`probe` returns a `wiring` draft assembled from each module's `__provenance__` and
from the baseline's own code — the modules with their sections and equations, the
baseline package, what it trains on and how it loads it.

That is raw material for you, not output for the user. **Open a conversation with it**
— see [Design — a conversation](#design--a-conversation-and-one-question-at-the-end-of-it).
Say what you found in their repository and what you would wire to what: which modules
carry the trainable terms, where the backbone's features enter, what the head predicts
over. Mark what you read, what you inferred and what you assumed, and raise whatever
you could not settle. Then work it out with them.

The harness knows how to train and measure; it cannot know what makes *this* method
trainable, and that is the one part worth the user's attention. Handing them the three
questions unanswered wastes the context this skill is already holding.

The draft's `offer` is `fromBaseline` and nothing else: the backbones, task names,
trained weights, **data entry points** and notebooks the prior work actually uses,
read from its own code. That environment is where its published results were
obtained, so it is the one a comparison means something in.

The entry points matter more than the names. A task name says what was measured; a
loader says how to measure it again, and the wiring needs the second. Notebooks
outside the proposal are read too — that is usually where the prior experiments
actually ran.

**Read `acquisition` before saying anything is unavailable.** A package can resolve a
directory it never creates; what creates it usually lives in a notebook, and a reading
that stopped at the package would conclude the material is unobtainable while the
thing that obtains it sits one file away. `acquisition` reports what was found about
how each side gets hold of what it trains on — a download, a clone, an archive, a
mounted directory. Material that is absent until something runs is not material that
cannot be had, and treating the two alike discards most of a user's experimental
ground for no reason.

**Read `foundNothingFor` before concluding anything.** The reading is a heuristic over
English word-stems and structure, so it misses a plausible variant and misses a
repository named in another language entirely. Where it reports finding nothing for a
kind, `readBy` says how it looked: put that to the user and ask them to point, rather
than telling them their baseline has no data layer. An empty list is a miss, and
presenting it as an absence would be the flow concluding something it never
established.

Nothing is suggested from a list. This is a forge for papers, not for one field: it
cannot know which models or datasets are reasonable for mathematics it has not read,
and offering a catalogue of well-known benchmarks would push both implementations
into a setting neither has been measured in. If the baseline's own environment is too
heavy to screen with, say so and let the user name a lighter one.

Write the completed wiring as `src/<Package>_Benchmark/wiring.py`, exposing
`build_new`, `build_baseline` and **`build_data`**. `build_baseline` may be `None`
when the prior work cannot run under the common reduction as it stands: that is a
`not applicable` with its reason, and the baseline is never edited to make a
comparison possible.

The harness owns training and measuring and nothing else: it names no dataset and no
architecture, because a catalogue there would dictate the experiment — the wiring
would be forced to pick whichever well-known set the baseline happens to touch, and
the reported common environment would be an intersection with that list rather than
the environment the prior results came from. `build_data` belongs to the wiring for
the same reason the builders do.

Materialize these four, fill in the reduction, and execute the notebook. Run
`materialize --stage harness --plan <path to the approved plan>` — no `--seed`: none
of the four carries a `{{SEED}}` token (`probe.ipynb` carries `{{SEEDS}}` instead,
answered later, at probe time). Unlike `objects`, this stage needs no step-8
precondition and its three `.py` destinations parse cleanly the moment they land:

| Written into | Written from |
| --- | --- |
| `src/<Package>_Benchmark/__init__.py` | `assets/kit/src_benchmark/__init__.py`, copied verbatim and never populated — see [The benchmark declaration, and its five blocks](#the-benchmark-declaration-and-its-five-blocks) |
| `src/<Package>_Benchmark/benchmark.py` | `assets/kit/nb/benchmark.py` |
| `src/<Package>_Benchmark/verdict.py` | `assets/kit/nb/verdict.py` |
| `<Name>/Notebooks/probe.ipynb` | `assets/kit/nb/probe.ipynb` |

The agent never copies these four by hand — the same `materialize` discipline step 5
and step 9 use, and `wiring.py` above stays the one bespoke-authored exception: it is
never a kit destination and this command never touches it. This is also the one and
only stage that ever writes `src/<Package>_Benchmark/` into a target at all — see
[`nextStep: "declare-first"`](#nextstep-declare-first--the-benchmark-package-exists-and-says-nothing-yet)
for why the scaffold stage no longer does.

`assets/kit/nb/` stages what the notebooks need; it does not mirror where any of it
ends up. Python that lives beside a notebook is a
stray module the moment it is committed; see [Target layout](#target-layout). The
notebook therefore addresses the harness by repository-relative path from `src/`, and
runs it from the harness's own directory so that its `verdict.py` and `wiring.py`
siblings resolve. Without
`wiring.py` the harness refuses and says what is missing. It trains each
implementation over every seed, measures accuracy, wall time, peak memory and
parameter count, and writes `<Name>/Results/Probe_results.json`.

**[GATE]** ask before running: it is quick by design, but it is still the user's
machine, and it downloads a dataset.

Execute the notebook with the target repository's own interpreter, as with the suite —
and with that venv's `bin` on `PATH`, for the reason the isolation section gives:
the kernel resolves its own interpreter off `PATH`, never off whatever launched
jupyter. `benchmark.py` refuses under any other and says which one to use — for this file that
is not a hygiene rule but the measurement itself: wall time and peak memory describe
whichever environment ran them, so a foreign interpreter produces a correct
measurement of the wrong thing and the summary would attribute it to this repository.
Where there is no interpreter of its own to compare against — a hosted runtime with no
virtualenv in the checkout — it stamps interpreter, platform and device into the
summary instead of refusing, so a table produced elsewhere is labelled as produced
elsewhere rather than attributed to this machine.
