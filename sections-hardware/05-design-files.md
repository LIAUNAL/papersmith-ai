---
{
  "section": "design-files",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-design-files.md",
      "quote": "The design files section lists every editable source file the hardware needs, where it lives and under which license."
    }
  },
  "blocks": [
    {
      "id": "df-summary-table",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/05-design-files.md",
            "quote": "Every file lives in the repository the repository-url names."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "df-descriptions",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "df-software",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---

# Design Files Summary (hardware line)

The design files section lists every editable source file the hardware needs, where it lives and under which license. HardwareX section 3, items 12 to 15.

**Extent** 150–500 words · the design files table, then one or two sentences per file

## Block `df-summary-table`

Every file lives in the repository the repository-url names. One row per file with four columns: design file name, file type, open source license and location of the file (its URL or DOI). The files are editable sources (CAD, schematic and layout projects, source code), not only exports such as STL, PDF or Gerber; an export is listed beside its source.

## Block `df-descriptions`

One or two sentences per listed file: what it is and which build step uses it. A file the build instructions never use is either removed from the table or explained.

## Block `df-software`

Every software and firmware component needed to build and run the hardware (HardwareX item 15): its repository path, its version or commit, its license, the toolchain that builds it and how it is loaded onto the hardware.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; the template's table has four columns, one row per file.

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

- A design file shared only as an export (STL, PDF, Gerber) without its editable source.
- A file without its license or its location, or a location outside the declared repository.
- Firmware or software the hardware needs that the repository does not hold.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `repository-url` — Every file lives in the repository the repository-url names. | `df-summary-table` |

### Internal chain

None: no block of this section waits on another block.
