# Third-party notices

Caztor is an independent project. It is not affiliated with, endorsed by or sponsored by Anthropic, opencode (Anomaly) or OpenAI. The names and logos below belong to their owners and are used only to tell the user which command-line assistant is active in the chat.

## Provider logos

The logos are shipped unmodified, byte for byte as downloaded, in `apps/web/src/assets/providers/`. They were retrieved on 2026-10-25, and `codex.svg` on 2026-10-26. Each vendor's brand rules apply to them; review those rules before Caztor is published.

| Asset | Owner | Official source | Terms |
|---|---|---|---|
| `claude.svg` (the Claude mark) | Anthropic | https://claude.ai/favicon.svg (the favicon the Claude web app serves; SHA-256 `b150888bc7257af83e3b85d3c2be4294f88986026f8168f6c12fc1fde6697350`) | Anthropic trademark. No open license is published with the file. Used here only to identify the Claude Code provider. Review Anthropic's brand guidelines before publishing. |
| `opencode-logo-light.svg` (mark for light backgrounds) | Anomaly (opencode) | `Logo/opencode-logo-light.svg` in https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/console/app/public/opencode-brand-assets.zip, the "Download all assets" file of https://opencode.ai/brand (SHA-256 `5eeb3a5f14dbbccc03111296ecfd3cd05cc98844150d4f9d77ba921847953380`) | Published by the vendor on its brand page "to help you work with the OpenCode brand". The source repository's MIT license covers its code; the brand page states no separate license for the marks. |
| `opencode-logo-dark.svg` (mark for dark backgrounds) | Anomaly (opencode) | `Logo/opencode-logo-dark.svg` in https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/console/app/public/opencode-brand-assets.zip (SHA-256 `4e84f87aa7bc2a5f8a72eeb08d3d4f1836b422189256d0bd5e7bfabc830d7ed0`) | Same as above. |
| `codex.svg` (the OpenAI mark, a white blossom on a blue disc, the same file for light and dark backgrounds) | OpenAI | https://developers.openai.com/favicon.svg (the icon the developers.openai.com site serves; retrieved on 2026-10-26; SHA-256 `8e1b976ba47e927ac2928303fd5362fcadfefd68743506510596f107df676e58`) | OpenAI trademark. It is the OpenAI company mark, used here only to identify Codex: no Codex-specific official logo could be found. No open license is published with the file. Review OpenAI's brand guidelines before publishing. |
| `antigravity.svg` (Google Antigravity favicon) | Google | https://antigravity.google/favicon.svg, retrieved on 2026-10-31; SHA-256 `de7911c3d206a3d2fe3d5b4e76e84b185c581d7a259406f64db247b5b824f02e` | Google trademark. The official asset is shipped unmodified, byte for byte, only to identify the Antigravity provider. Caztor is not affiliated with, endorsed by, or sponsored by Google. Review Google's brand guidelines before publishing. |

### Codex

No logo specific to Codex could be obtained from an official source: the `openai/codex` repository on GitHub has no logo file (only SVG icons of sample skills and a README splash screenshot), developers.openai.com publishes only its own site marks, and openai.com/brand is blocked by a bot challenge, so it could not be read. By the user's decision of 2026-10-26 the OpenAI mark published on developers.openai.com is shipped instead, to identify Codex, byte for byte as downloaded. The same site's header logo (`/OpenAI_Developers.svg`) is the words "OpenAI Developers" in black, which the site inverts in dark mode with a style rule; it was not used, because the mark alone has no text to read as a product name and needs no variant. Nothing was drawn or approximated.

## Writing guides

The advisory writing guides in `guides/` are modified derivatives of the section guides of papersmith-ai (https://github.com/Daprosero/papersmith-ai), taken at commit `1f09516` (the file `sections/*.md` of that commit). papersmith-ai is licensed under the Apache License, Version 2.0; a verbatim copy of the license is in `LICENSES/Apache-2.0.txt` and is also provisioned next to the guides as `LICENSE-papersmith-ai.txt`.

Caztor made these changes: it removed the JSON front matter and the parts that belong to papersmith-ai's own tooling (input tables, dependency references and block identifiers), removed HTML comments, reworded a few sentences that named that tooling, renamed the remaining input sections to "Drafting order", added a modification notice and an advisory note to every guide, appended a "Shared conventions" section written by Caztor, and wrote `guides/INDEX.md`. `guides/SOURCE.json` records, for each guide, the source path, the SHA-256 of the source text, and the headings that were kept and removed. `scripts/distill-guides.ts` regenerates all of it from the source commit. Each guide carries its own notice with the source path and commit.

papersmith-ai is not affiliated with Caztor and does not endorse it.
