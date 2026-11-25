---
{
  "section": "abstract",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-abstract.md",
      "quote": "Every number in the abstract is copied from the validation and characterization section; the abstract adds nothing."
    }
  },
  "blocks": [
    {
      "id": "abs-hardware",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/01-abstract.md",
            "quote": "The hardware and its purpose come from the contributions the hardware description states."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "hardware-description.hd-overview",
          "source": {
            "file": "sections/01-abstract.md",
            "quote": "The hardware and its purpose come from the contributions the hardware description states."
          }
        }
      ]
    },
    {
      "id": "abs-performance",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "validation-characterization",
          "source": {
            "file": "sections/01-abstract.md",
            "quote": "The performance sentences follow the validation and characterization section: the measured quantities with their expanded uncertainty and the agreement with the reference device."
          }
        }
      ]
    }
  ]
}
---

# Abstract (hardware line)

Every number in the abstract is copied from the validation and characterization section; the abstract adds nothing. HardwareX item 2: one paragraph, at most 200 words, that cites the research the hardware serves.

**Extent** 120–200 words · one paragraph

## Block `abs-hardware`

The hardware and its purpose come from the contributions the hardware description states. Two or three sentences: what the hardware is, the research it serves, with the citation of that research, and what sets it apart from the equipment it replaces (cost, openness, a capability), in the words of the hardware description.

## Block `abs-performance`

The performance sentences follow the validation and characterization section: the measured quantities with their expanded uncertainty and the agreement with the reference device. Every value carries its unit and its expanded uncertainty with the coverage factor, or its limits of agreement, exactly as the uncertainty and agreement records hold them. A quantity whose budget is stale or missing is not mentioned.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; the template caps the abstract at 200 words.

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

- A number that the validation and characterization section does not hold.
- More than 200 words, or no citation of the research the hardware serves.
- A performance claim without its uncertainty or its limits of agreement.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The hardware and its purpose come from the contributions the hardware description states. | `abs-hardware` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-hardware` — The hardware and its purpose come from the contributions the hardware description states. | `hardware-description.hd-overview` |
