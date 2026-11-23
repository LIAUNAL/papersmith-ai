---
{
  "section": "validation-characterization",
  "position": 9,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/09-validation-characterization.md",
      "quote": "The validation and characterization transcribe the measurement records; they never state a value that no record holds."
    }
  },
  "blocks": [
    {
      "id": "vc-protocol",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The protocol is the locked revision that fixed the specifications, the validation design and the primary performance outcome."
          }
        },
        {
          "value": "outcomes",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The outcomes are the primary and secondary performance outcomes of the locked protocol, each with its acceptance criterion."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "vc-calibration",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "vc-uncertainty",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "vc-agreement",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "vc-use-case",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "vc-user-validation",
      "requires_facts": [
        {
          "value": "sample",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The sample is the number of participants or users the locked protocol planned, with its justification."
          }
        }
      ],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded."
          }
        },
        {
          "value": "study-registration",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The study-registration is stated with the registry, the record and its dates, or says that the validation was not registered."
          }
        }
      ],
      "citations": "none",
      "optional": true
    },
    {
      "id": "vc-capabilities-limitations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/09-validation-characterization.md",
            "quote": "The limitations are where the hardware falls short: the ranges, conditions and uses its validation does not cover."
          }
        }
      ]
    }
  ]
}
---

# Validation and Characterization (hardware line)

The validation and characterization transcribe the measurement records; they never state a value that no record holds. HardwareX section 7, items 24 to 26, with every uncertainty reported as GUM clause 7 asks (`python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root .`). Read the whole state first with `python skills/_core/measurement/measure_cli.py status --root .`.

**Extent** 800–2000 words · the use case figure, the uncertainty budget table, the Bland-Altman plot

## Block `vc-protocol`

The protocol is the locked revision that fixed the specifications, the validation design and the primary performance outcome. The outcomes are the primary and secondary performance outcomes of the locked protocol, each with its acceptance criterion. Name the locked revision and every amendment with its reason, as `python skills/_core/empirical/study_cli.py protocol status --root .` prints them. The primary performance outcome is named first, exactly as the protocol names it; the paper never changes it, and an outcome added after the lock is reported as such.

## Block `vc-calibration`

Every instrument used to calibrate or to test the hardware, from `study/instruments.json` (`python skills/_core/measurement/measure_cli.py instrument status --root .`): model, serial number, calibration certificate, calibration and due dates, resolution and stated uncertainty, and the traceability the certificate states. An instrument past its due date when it was used is reported with the reason the operator recorded.

## Block `vc-uncertainty`

One uncertainty budget per measured quantity and condition set, from `study/uncertainty/<quantity>.json` (`python skills/_core/measurement/measure_cli.py uncertainty status --root .`): the result with its unit, each component with its type (A from the replicates, B from the instrument), distribution, standard uncertainty and sensitivity coefficient, the combined standard uncertainty, the effective degrees of freedom, the coverage factor and its coverage probability, and the expanded uncertainty. A budget the status marks stale is recomputed by the operator before it is reported. Performance across the operating parameters (HardwareX item 25: range, resolution, repeatability, drift) is reported from these budgets, one per condition set.

## Block `vc-agreement`

The agreement with the reference device, from `study/agreement.json` (`python skills/_core/measurement/measure_cli.py agreement status --root .`): the reference device, the number of paired readings, the mean bias and its confidence interval, the 95% limits of agreement, the intraclass correlation ICC(2,1) for absolute agreement with its interval, and the Bland-Altman plot drawn from the paired raw files. The verdict compares the limits with the acceptance criterion of the locked protocol, never with one chosen after the analysis.

## Block `vc-use-case`

The hardware working on a specific, relevant application (HardwareX item 24), from the raw files the operator registered (`python skills/_core/measurement/measure_cli.py data status --root .`), with the setting, the conditions and what the measurement showed.

## Block `vc-user-validation` (when people take part, optional)

The sample is the number of participants or users the locked protocol planned, with its justification. The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded. The study-registration is stated with the registry, the record and its dates, or says that the validation was not registered. Written only when people take part in the validation (a field trial with users, a usability study, measurements on participants); a bench-only validation leaves this block unopened. The design comes from the protocol the operator deliberated with `/study-protocol-deliberation` and locked; the ethics and registration records are read with `python skills/_core/empirical/study_cli.py status --root .`, and the participant counts come from the signed-off `study/flow.json`. The assistant never writes that consent was obtained, waived or not needed unless the operator's record says so.

## Block `vc-capabilities-limitations`

The limitations are where the hardware falls short: the ranges, conditions and uses its validation does not cover. Two bulleted lists (HardwareX item 26): what the hardware can do, each item backed by a budget, the agreement or the use case above, and where it falls short, each item naming the range, condition or use and its consequence for a user.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; HardwareX validations run two to four pages with three to six figures.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates measurements or data: every reading, count, cost, uncertainty and agreement value in the paper comes from the operator's records (the raw files the operator registered, the budgets and the agreement computed from them, the operator's purchase records), never from a model, a datasheet value presented as a measurement, or a simulation presented as an observation. A value without a record is left out and reported as missing.
- **Human decisions.** The decisions on ethics, consent, data collection and the choice of primary outcome stay human: the paper reports the specifications the operator signed, the operator's ethics record and consent route when people take part, how the operator built the hardware and took the measurements, and the primary performance outcome of the locked protocol, and never proposes, changes or completes any of them.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what was done (*we built*, *we measured*), past tense for every step that was run, present tense for what the hardware does and what the results show; the build and operation steps are imperatives.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **A measured value carries its unit and its uncertainty.** SI units, the value and its expanded uncertainty with the coverage factor (*(12.31 ± 0.08) mm, k = 2*) or its standard uncertainty named as such, never a bare number and never more digits than the uncertainty supports.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state the cost, the range or the uncertainty instead.
- **A table has at least three columns and three rows**, except the two-column specifications table the template fixes. A smaller grid becomes a chart or a sentence. A chart is drawn by a script from the line's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Readings from the registered raw files, uncertainties from the budgets, agreement from the agreement record, costs from the bill of materials, planned values from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A value, an interval or a plot that no record under `study/` holds, or one copied from a stale budget.
- A measured value without its uncertainty, or an expanded uncertainty without its coverage factor.
- An acceptance criterion for the agreement chosen after the analysis instead of the locked protocol's.
- A validation with people reported without the ethics record and the consent route, or the user validation block written for a bench-only validation.
- A capability that no measurement in this section supports.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `protocol` — The protocol is the locked revision that fixed the specifications, the validation design and the primary performance outcome. | `vc-protocol` |
| `outcomes` — The outcomes are the primary and secondary performance outcomes of the locked protocol, each with its acceptance criterion. | `vc-protocol` |
| `sample` — The sample is the number of participants or users the locked protocol planned, with its justification. | `vc-user-validation` |
| `ethics-approval` — The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded. | `vc-user-validation` |
| `study-registration` — The study-registration is stated with the registry, the record and its dates, or says that the validation was not registered. | `vc-user-validation` |

### Internal chain

None: no block of this section waits on another block.
