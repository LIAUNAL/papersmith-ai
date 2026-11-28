## The paper is written in English, whatever language the session is in

The conversation may be Spanish or English. **The artifact is English.** A block's
body, a section's contract prose, a figure caption, the fields of a `refs.bib`
entry and every report this skill writes land in English, and one that lands
otherwise is a defect of the draft rather than a preference of the operator.

The split is not invented here. `proposal-implementation` states it for its own
artifacts — *"Every artifact stays English — code, comments, commit messages,
reports, every file written. The conversation does not."* — and this skill is held
to the same rule, because a manuscript is the one deliverable that leaves this
workspace and is read by people who were never part of the conversation that
produced it.

**Why this is written down rather than assumed.** Until now nothing here said
which language a block is written in, so the answer was whatever language the
session happened to be speaking. A Spanish session that produces a Spanish block
has not served the operator: it has produced a manuscript in a language nobody
chose, and the defect stays invisible until the paper is read by someone else.

**What this rule does not touch.** Identifiers, paths, code, LaTeX commands,
citation keys and the strings a contract quotes stay byte-identical — they were
never prose. The `style` channel's samples keep whatever language they were
ingested in: a style reference is evidence about rhythm and register, and
`STYLE_OVERLAP` already refuses a draft that borrows its words.

**The rule is enforced, not only stated.** `paper_language.py` is the one
detector: `write` refuses a draft carrying Spanish prose (`DRAFT_NOT_ENGLISH`)
or placeholder text — `por definir`, `TODO`, `TBD`, `FIXME`, `\todo`
(`DRAFT_PLACEHOLDER_TEXT`) — before evidence-audit runs, so no attempt is
spent and `main.tex` stays byte-identical; `verify`'s `language` check and the
manuscript QA report (`language`/`placeholder` findings) scan the whole
`main.tex`. Math, comments, markers, citations, the bibliography and
capitalized accented words (names, institutions) are never read as Spanish.
A paper that declares another main language in `main.tex` (babel's `main=`
or last option, polyglossia's `\setmainlanguage`) is exempt from the Spanish
check, never from the placeholder check.
A span the paper marks as another language, `\foreignlanguage{<lang>}{…}` or an `otherlanguage` environment, is exempt from the Spanish check; a placeholder inside it still counts.

A journal that receives only Spanish does not change this: the paper is written
and verified in English, then translated as a derived file under
`paper/translations/es/` ("Translation to Spanish: `translate`" in `references/translate.md`).
