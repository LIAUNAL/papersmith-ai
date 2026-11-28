---
{
  "section": "hardware-description",
  "position": 4,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/04-hardware-description.md",
      "quote": "The hardware description says what is new in this hardware and why another researcher would build it."
    }
  },
  "blocks": [
    {
      "id": "hd-overview",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/04-hardware-description.md",
            "quote": "The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "hardware-in-context.hic-comparable",
          "source": {
            "file": "sections/04-hardware-description.md",
            "quote": "The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/04-hardware-description.md",
            "quote": "The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings."
          }
        }
      ]
    },
    {
      "id": "hd-architecture",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "hd-uses",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Hardware Description (hardware line)

The hardware description says what is new in this hardware and why another researcher would build it. HardwareX section 2, items 10 and 11. It describes the customization, not the general concept the context already covered.

**Extent** 300–700 words · prose, a block diagram, then three to five bullet points · at least as many figures as tables

## Block `hd-overview`

The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings. Each contribution answers the gap the context left: a lower cost, an open design, a range or a resolution, a capability, each stated as the comparison it wins and checked later by the validation.

## Block `hd-architecture`

The subsystems (sensing, conditioning, acquisition, processing, power, enclosure) and how they connect, with a block diagram drawn from the design files. Name each key component and the reason it was chosen; the datasheet values of a component are cited as datasheet values, never as measurements of this hardware.

## Block `hd-uses`

Three to five bullet points (HardwareX item 11) on how other researchers, in the field and outside it, could use or adapt the hardware, each one concrete: the measurement, the setting and what they would change.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; HardwareX descriptions run one page with a block diagram and the template's bullet list.

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
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Readings from the registered raw files, uncertainties from the budgets, agreement from the agreement record, costs from the bill of materials, planned values from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A contribution the validation section does not test.
- A datasheet value presented as a measured performance of this hardware.
- [block: hd-uses] Fewer than three or more than five bullet points on uses for other researchers.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `gap` — The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings. | `hd-overview` |

### Internal chain

| Block | Depends on |
|---|---|
| `hardware-description.hd-overview` — The contributions are what the hardware does that the comparable equipment does not, and the advantage each one brings. | `hardware-in-context.hic-comparable` |
