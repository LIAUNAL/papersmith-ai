---
{
  "section": "title-and-keywords",
  "position": 0,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/00-title-and-keywords.md",
      "quote": "The title names the hardware and what it measures or does, in words a reader outside the field understands."
    }
  },
  "blocks": [
    {
      "id": "title",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/00-title-and-keywords.md",
            "quote": "The contributions of the hardware, what it is and what it is for, decide the title."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "hardware-description.hd-overview",
          "source": {
            "file": "sections/00-title-and-keywords.md",
            "quote": "The contributions of the hardware, what it is and what it is for, decide the title."
          }
        }
      ]
    },
    {
      "id": "keywords",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "keyword-bounds",
          "source": {
            "file": "sections/00-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        },
        {
          "value": "classification-line",
          "source": {
            "file": "sections/00-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Title and Keywords (hardware line)

The title names the hardware and what it measures or does, in words a reader outside the field understands. HardwareX items 1 and 3.

**Extent** 8–20 words · keywords 3–6

## Block `title`

The contributions of the hardware, what it is and what it is for, decide the title. The title names the device or instrument, the quantity it measures or the task it performs and, when it matters, its setting or its cost class, in this order: "<what the hardware is> for <what it measures or does> [in <setting>]". No acronym or abbreviation unless it is the hardware's own name and the abstract expands it, no claim of novelty, no question form, and no performance figure the validation section does not hold.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Three to six keywords (HardwareX item 3), none repeating a word of the title, the measured quantity or the field of application among them.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; HardwareX titles of comparable open instruments run 10 to 18 words.

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

- A title that does not say what the hardware is for.
- An acronym or abbreviation in the title that is not the hardware's own name expanded in the abstract.
- A promotional or evaluative word in the title (*Novel*, *Revolutionary*, *Smart* used as praise).
- Fewer than three or more than six keywords, or a keyword that repeats a word of the title.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the hardware, what it is and what it is for, decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the hardware, what it is and what it is for, decide the title. | `hardware-description.hd-overview` |
