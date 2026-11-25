# Third-party notices

Caztor is an independent project. It is not affiliated with, endorsed by or sponsored by Anthropic, opencode (Anomaly), OpenAI or Google. The names Claude Code, opencode, Codex, Antigravity and Pi belong to their owners and are used only, as plain text, to tell the user which command-line assistant is active in the chat. Caztor ships no logo or other brand asset of these vendors.

## Writing guides

The advisory writing guides in `guides/` are modified derivatives of the section guides of papersmith-ai (https://github.com/Daprosero/papersmith-ai), taken at commit `1f09516` (the file `sections/*.md` of that commit). papersmith-ai is licensed under the Apache License, Version 2.0; a verbatim copy of the license is in `LICENSES/Apache-2.0.txt` and is also provisioned next to the guides as `LICENSE-papersmith-ai.txt`.

Caztor made these changes: it removed the JSON front matter and the parts that belong to papersmith-ai's own tooling (input tables, dependency references and block identifiers), removed HTML comments, reworded a few sentences that named that tooling, renamed the remaining input sections to "Drafting order", added a modification notice and an advisory note to every guide, appended a "Shared conventions" section written by Caztor, and wrote `guides/INDEX.md`. `guides/SOURCE.json` records, for each guide, the source path, the SHA-256 of the source text, and the headings that were kept and removed. `scripts/distill-guides.ts` regenerates all of it from the source commit. Each guide carries its own notice with the source path and commit.

papersmith-ai is not affiliated with Caztor and does not endorse it.
