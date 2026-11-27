---
{
  "section": "build-instructions",
  "position": 7,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/07-build-instructions.md",
      "quote": "The build instructions let a reader rebuild the hardware from them alone, step by step."
    }
  },
  "blocks": [
    {
      "id": "bi-steps",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "bi-design-decisions",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "bi-safety",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Build Instructions (hardware line)

The build instructions let a reader rebuild the hardware from them alone, step by step. HardwareX section 5, items 18 to 21. The steps are the ones the operator followed to build the hardware the paper validates.

**Extent** 500–2000 words · numbered steps with figures

## Block `bi-steps`

Numbered, imperative steps in build order, each naming the design files and the bill-of-materials designators it uses, the tools it needs and how to check the step worked. Schematics, photographs or videos support the steps and refer to the same file and designator names (HardwareX item 20).

## Block `bi-design-decisions`

The design decisions a builder could revisit: why this part, this material, this tolerance or this layout, the alternatives considered and, where it was measured, the measurement that supports the choice.

## Block `bi-safety`

The hazards of building the hardware (soldering, mains voltage, lasers, chemicals, sharp edges, lifting) and the protection each step needs (HardwareX item 21); a build without a hazard says so.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; HardwareX build sections run as numbered steps with one figure every few steps.

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
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Readings from the registered raw files, uncertainties from the budgets, agreement from the agreement record, costs from the bill of materials, planned values from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A step that names a part or file the bill of materials or the design files do not list.
- A step a reader could not repeat without asking the authors.
- A hazardous step without its precaution.

## Inputs

### External inputs

None: every block reads the line's records and the operator's own account.

### Internal chain

None: no block of this section waits on another block.
