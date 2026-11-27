---
{
  "section": "specifications-table",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-specifications-table.md",
      "quote": "The specifications table transcribes the operator's records; it never estimates a cost, a license or a repository."
    }
  },
  "blocks": [
    {
      "id": "spec-table",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/02-specifications-table.md",
            "quote": "The protocol is the locked revision whose requirements and specifications the operator signed at G-SPEC."
          }
        }
      ],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/02-specifications-table.md",
            "quote": "The repository-url is the DOI or URL of the source files in an approved repository."
          }
        }
      ],
      "citations": "none",
      "after": [
        {
          "target": "bill-of-materials.bom-table",
          "source": {
            "file": "sections/02-specifications-table.md",
            "quote": "The cost of hardware is the total of the bill of materials."
          }
        }
      ]
    }
  ]
}
---

# Specifications Table (hardware line)

The specifications table transcribes the operator's records; it never estimates a cost, a license or a repository. HardwareX items 4 to 8: the two-column table the template fixes, placed before section 1. The operator signed the requirements and specifications at G-SPEC, when the hardware's study protocol was approved and locked (`study/protocol.lock.json`); this table reports the hardware as built against them.

**Extent** 60–160 words · the two-column specifications table

## Block `spec-table`

The protocol is the locked revision whose requirements and specifications the operator signed at G-SPEC. The repository-url is the DOI or URL of the source files in an approved repository. The cost of hardware is the total of the bill of materials. One row each, in the template's order: *Hardware name*; *Subject area* and *Hardware type*, each chosen from the template's own lists; *Closest commercial analog*, or "No commercial analog is available."; *Open source license*, as the repository's license file states it; *Cost of hardware*, with its currency; *Source file repository*; and, only when the operator holds one, the *OSHWA certification UID*. A specification the built hardware does not meet is not hidden here: the validation section reports it against the signed value.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules to an open-hardware article in the HardwareX template, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` (the requirements and specifications the operator signed at G-SPEC), the instrument records `study/instruments.json`, the registered raw measurement files `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json`, the agreement record `study/agreement.json` and, when people take part in the validation, the ethics and registration records under `study/` and the participant flow `study/flow.json`.

**Measured size.** None yet; the template's table has seven rows plus an optional certification row.

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

- A cost that differs from the bill of materials total, or one without its currency.
- A license that is not the license file of the repository, or a repository without a DOI or stable URL.
- A subject area or hardware type outside the template's lists.
- A specification or certification the operator's records do not hold.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `protocol` — The protocol is the locked revision whose requirements and specifications the operator signed at G-SPEC. | `spec-table` |
| `repository-url` — The repository-url is the DOI or URL of the source files in an approved repository. | `spec-table` |

### Internal chain

| Block | Depends on |
|---|---|
| `specifications-table.spec-table` — The cost of hardware is the total of the bill of materials. | `bill-of-materials.bom-table` |
