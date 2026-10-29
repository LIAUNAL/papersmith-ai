### `nextStep: "pilot-decisions"` — every step ran, and each one owes its own decision

**What a finished pilot unlocks is not permission to launch.** The flow runs as
it stands, which proves that it runs; its notebooks run, which proves that it
shows what was agreed; and only then does the flow return to its first step and
go one step at a time, deciding for each one how the full run carries it — sent
to a worker for the steps that need one, kept local for the steps that do not.
This rung is the start of that pass, and the offer of the declared scale waits
behind it.

**One question per step, each retiring on its own.** `toDiscuss` carries the
rung's own question first — what state the flow is in, and where its outputs are
— and then one entry per step that has not been decided yet. Every entry is a
runnable `discuss` command, and `discuss` buckets by exact question text, so
answering one retires one. Nothing new records the answers: `discuss` already
does, and building a second approval surface beside it would give two places to
look for the same decision.

**Never-asked is not decided.** A step whose question nobody has asked appears in
no open bucket either, so the pass reads which texts were ANSWERED rather than
which are open. Reading the absence as agreement is silence taken for consent.

**A report in drift is named here, and holds the pass until it is
acknowledged.** These decisions are taken over the artefacts a human reads, so
a pass that stays silent about the state of those artefacts is telling the
operator the document is fine. `report.liveFindings` names the findings that are
about this code — a finding stamped `fromStaleNotebook` describes a run the
repository has already moved past and is not one — and while any of them stands
unacknowledged this rung keeps the answer, publishing the acknowledgement
BEFORE the per-step questions. Measured: on a real repository the report was in
drift with five kinds of finding about the notebooks the pilot had just
produced, and the ladder walked into this pass anyway; `report-first` sits below
it and would have said the same thing after the decisions were already taken.

It is an acknowledgement and **not a wall**. A report at pilot is legitimately in
drift — a section whose run has not happened renders an absence — and for some
findings the repair *is* the full run, so a hard gate would refuse the pass that
authorizes the run in order to fix the report the run is what fixes. The exit is
the operator's own and is the one the question already offers: repair the report
now, or record why the decisions are taken over it as it stands. Nothing new
records that answer either — `discuss` buckets it by exact text like every other
question in this pass, and a finding appearing or clearing re-opens it, because
that is a change of state and not a moving count.

**And which steps the pilot opened no notebook for is named in the same
sentence.** Naming where the outputs are and staying silent about the steps that
rendered none tells an operator they are looking at the whole flow when they are
looking at part of it — six paths named out of ten declared steps, on the
repository this was measured on — and this is the last rung before the decisions
that put a step on a remote worker, whose own artefact may be one of the notebooks
nothing ever executed. The sentence names them and the pass carries on; nothing is
refused, and a target that deliberately computes in a library reads its own design
back rather than a finding.

**Which steps need a worker is not answered here.** `remoteExecution.necessity`
classifies job folders — must-remote, local-sufficient, or optional with the
missing fact named — and a job folder is not a step: nothing declared ties one to
the other, and inventing the link would be the forge deciding a repository's own
layout for it. Read that classification beside this pass; it informs the
decisions and never makes them.
