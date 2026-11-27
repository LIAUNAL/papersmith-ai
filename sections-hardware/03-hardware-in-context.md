---
{
  "section": "hardware-in-context",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-hardware-in-context.md",
      "quote": "Hardware in context argues why researchers need this hardware, against the open and proprietary equipment that exists."
    }
  },
  "blocks": [
    {
      "id": "hic-need",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-hardware-in-context.md",
            "quote": "The problem-statement says which measurement or task researchers cannot do, or cannot afford, with the equipment they have."
          }
        }
      ]
    },
    {
      "id": "hic-comparable",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-hardware-in-context.md",
            "quote": "The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "hardware-in-context.hic-need",
          "source": {
            "file": "sections/03-hardware-in-context.md",
            "quote": "The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-hardware-in-context.md",
            "quote": "The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task."
          }
        }
      ]
    }
  ]
}
---

# Hardware in Context (hardware line)

Hardware in context argues why researchers need this hardware, against the open and proprietary equipment that exists. HardwareX section 1, item 9.

**Extent** 250–600 words · 2 to 4 paragraphs

## Block `hic-need`

The problem-statement says which measurement or task researchers cannot do, or cannot afford, with the equipment they have. Name the measurement or task, the researchers who need it and the setting where it matters, each with its citation. A need is a measurement someone has to make, never the absence of this hardware.

## Block `hic-comparable`

The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task. Set the hardware among the comparable devices, open and proprietary, each cited, on the criteria a buyer compares: price, openness of the design, range, resolution, stated uncertainty, size and power. A comparison table needs at least three devices and three criteria; a figure of a competitor is taken from its published source, never from a guess.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; HardwareX articles state the context in two to four paragraphs with one comparison table at most.

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

- A comparable device described without its citation, or a price or a specification nobody published.
- A need stated as the lack of this hardware (*there is no low-cost device*) instead of the measurement it blocks.
- A paragraph that describes the new hardware itself; that belongs to the hardware description.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task. | `hic-comparable` |

### Internal chain

| Block | Depends on |
|---|---|
| `hardware-in-context.hic-comparable` — The gap is what the comparable open and proprietary equipment leaves unsolved for that measurement or task. | `hardware-in-context.hic-need` |
