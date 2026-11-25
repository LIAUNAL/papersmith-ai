# Caztor

Caztor is a local web app for writing LaTeX papers with an AI assistant beside you. You open a project folder, edit it, compile it with Tectonic, read the PDF, and ask a command-line assistant (Claude Code, opencode, Pi or Antigravity) to change the text. Every assistant turn is snapshotted first, so you can undo it.

It runs on your computer, as your user, for one project folder at a time. Read [Disclosed limits](#disclosed-limits) before you open a project you did not write.

## Quick start

```sh
npm install
npm run build -w @caztor/web
npm start -- path/to/your/project
```

Then open the address printed in the terminal (`Caztor is running at http://127.0.0.1:4317 for ...`). The first window asks you to read and accept the limits below, once per project.

### Requirements

| Needed | Why |
|---|---|
| Node.js 26 and npm | Runs the server directly from TypeScript sources (no build step for the server) |
| [Tectonic](https://tectonic-typesetting.github.io/) on the `PATH` | Compiles LaTeX. Tested with 0.17.0 |
| At least one of `claude`, `opencode`, `codex` on the `PATH`, signed in | The chat assistant. Without any, the editor and compile still work |
| `bwrap` (bubblewrap), optional | Only for the opt-in [compile sandbox](#opt-in-compile-sandbox). Linux only |

The server uses port 4317 and the next free port when it is busy; the printed address is the one to open.

## PaperSmith workspaces and the project navigator

The rail at the left lists your projects: every [PaperSmith](https://github.com/Daprosero/papersmith-ai) workspace in `~/papers` (set `CAZTOR_PAPERS_DIR` to scan another folder), and every folder you opened before. A workspace is a folder holding `papersmith.yaml` or `.papersmith/config.json`. Click a project, or move with the arrow keys and press Enter. To open any other folder, type its path at the bottom of the rail. The **+** button creates a project: a new folder in the papers folder with a starter `main.tex`, which opens right away. It is a plain LaTeX project, not a PaperSmith workspace; `smith init` creates those.

- **Switching** saves open edits first and reloads the page. It is refused while a turn runs, or when an edit cannot be saved. A running compile is stopped.
- **In a workspace** Caztor knows the paper is `paper/main.tex`: it opens it and compiles it, with Tectonic into `.caztor/build`, so it does not write `paper/main.pdf`. When it does not exist yet, Caztor asks whether to create it the way PaperSmith's `paper_scaffold` does: `refs.bib`, `Figures/` and `.gitkeep`, without changing anything that exists, and `main.tex` as a short document that compiles, titled from `papersmith.yaml`. PaperSmith reads it like its own empty one (checked with its `status`, `open` and `substitute`). Because PaperSmith adds new blocks at the end of the file, after `\end{document}`, the editor then offers to move `\end{document}` back to the end.
- **Block markers.** PaperSmith writes the paper one named block at a time, between comment lines that start with `%% paper-writing block`, and keeps two regions, `declarations` and `provenance`, between lines that start with `%% paper-writing`. The editor shows them dimmed and does not let them change, and the server refuses a save of a `.tex` file that changes, removes or adds one. The agents are told to leave them alone, but their own tools are not blocked. Editing the text inside a block is fine; PaperSmith then asks to adopt it (`substitute --adopt`) before it writes that block again.
- **Hidden** from the tree and the file API: `.papersmith/`, `.pi/`, `.mcp.json`, `.env`, `.env.local` and `skills/kaggle-accounts/store/`. An agent's own tools are not bound by this, so do not treat it as a sandbox.
- **Not changed:** PaperSmith itself. Caztor only reads a workspace's markers. A chat turn adds Caztor's agent files to the workspace, as in any project, and the workspace's own CLI configuration needs your confirmation first.

- **Not walked:** folders that tools fill with files nobody edits here, at any depth: `.micromamba`, `.venv`, `.conda`, `__pycache__`, `node_modules`, `.git`, `.tox`, `.mypy_cache`, `.pytest_cache` and `.ruff_cache`. They are left out of the tree and of the scan every compile makes, so a workspace that holds Python environments compiles in seconds; a file inside one can still be opened by its path.

The choice of folders is kept in `caztor/projects.json` in your configuration folder. Folders with more than 300 entries start folded in the tree, except `paper`.

The theme control in the header offers System, Light and Dark. The PDF page stays white.

## Inside a PaperSmith dashboard

`npm start -- <workspace> --embed-origin http://127.0.0.1:<port>` (or `CAZTOR_EMBED_ORIGIN`) serves Caztor for the page of that origin, which shows it in a frame: `smith ui` starts it this way in its PDF tab. Only that exact origin may frame the pages (`frame-ancestors`); every other check of the security gate stays as it is. The server stays on its one project: the project rail is hidden and listing, opening or creating projects answers 503. The PDF text becomes selectable, and each selection is posted to the embedding page; a `caztor:compose` message from that page and origin adds its text to the chat box, which you then send yourself.

## The four panes

From left to right: the **file tree** (create, rename, delete, upload, folders), the **editor** (LaTeX and BibTeX highlighting, autosave, a banner and a compare view when a file changes on disk while you edit), the **PDF preview** (zoom and scroll are kept across compiles; a mark shows when the PDF is out of date) and the **chat**. The pane order is fixed and the sizes are remembered by the browser.

### Explained passages

When a reply quotes the paper (inline code, a `>` quote or text in quotation marks), those passages are marked in soft yellow in the editor and on the PDF pages. **Highlight explained passages**, above the message box, turns the marks off and on; the choice is remembered by the browser. Only the latest reply counts. Matching compares letters and digits, so line breaks, hyphenation and punctuation do not matter; on the PDF, LaTeX commands are read as printed (`\cite{...}` dropped, `\textbf{x}` as `x`). A quotation shorter than 20 letters is taken for a name or a path and not marked.

## Compiling

Compile with the toolbar button. Tectonic runs in the project folder and writes only under `.caztor/build/`. When the file open in the editor is a `.tex` file other than the main one, a second button, **Compile <file>**, compiles that file instead; Compile and auto-compile keep using the main file.

- **BibTeX is supported** (`\bibliography` with `bibtex`).
- **biblatex with biber is not supported.** Caztor detects it and says so instead of showing a cryptic engine error.
- **The first compile downloads packages** (Tectonic's support files) into its cache, which can take a few minutes. A run is stopped after 3 minutes, or 10 minutes once it has started downloading.
- Shell escape is never enabled. The engine receives only the environment variables it needs (`PATH`, `HOME`, cache and proxy variables, `TMPDIR`), never your API keys.
- Options next to the button: stop on first error, auto-compile, and, when available, the sandbox. They are saved per project.
- A problem list under the PDF links each message to the file and line. Opening a file outside the project is reported as a warning where Tectonic or its log shows it.

## The chat and the providers

Pick a provider in the chat header. Caztor starts the assistant's own command-line program for each turn, with the project folder as its working directory, and shows the answer, the tools it used and the files it changed.

| Provider | Notes |
|---|---|
| Claude Code (`claude`) | Tested with 2.1.296. The model list holds the current and recent `claude-` models known to Claude Code 2.1.317, since the CLI cannot list them; without a choice Caztor uses `claude-sonnet-5-5`. Another model name can be set with `/model <name>`. |
| opencode (`opencode`) | Tested with 1.19.0. A model is **required**, written `provider/model`, for example `openai/gpt-5.6-terra`. Some models are rejected for ChatGPT-account sign-ins; the chat then says the model is not available and asks you to choose another. |
| Codex (`codex`) | **Not offered in the chat**: no PaperSmith harness drives it, so the selector leaves it out; the server code stays. **Built from documentation and untested**: `codex` was not installed during development, so its command line and output parsing come from published documentation and fixtures that are labelled as such. It runs without a model flag. Run the opt-in check below before relying on it. |
| Antigravity (`agy`) | Tested with 1.4.12 and Gemini 3.8 Flash. Signs in with your Google account only. The model is optional and the list comes from `agy models`. Runs with [partial isolation](#antigravity-partial-isolation). |
| Pi (`pi`) | Built for 1.4.0 from its documentation; no real turn was run during development. Chosen from its own button, in the place Codex had among the four providers. Signs in with Pi's own login or with a per-vendor API key. The model is optional in account mode and written `provider/model`, for example `anthropic/claude-sonnet-4-5`; the list comes from `pi --list-models`, which shows only the providers you are signed in to. Runs with [partial isolation](#pi-partial-isolation). |

Each provider's availability, version and (for opencode) model list are detected when the page opens; the header has a re-check action.

### Commands

Type `/` at the start of the message box to see the commands: `/new`, `/model [name]`, `/provider <name>` (opencode, claude, pi or antigravity), `/login`, `/recheck`, `/compile` and `/stop`. Move with the arrows, run with Enter, complete with Tab, close with Escape. They run in Caztor and never reach the assistant. The CLIs' own slash commands are not available, because a turn turns them off. Text after a slash that names no command, such as a path, is sent as a normal message.

**The project's own agents.** In a project with `.claude/agents/<name>.md` files, such as a PaperSmith workspace (`math-tutor`, `experiments-tutor`, `paper-reviewer` and the rest), the menu also lists each agent with the first sentence of its description. `/math-tutor <message>` sends the message as that agent: the server puts the agent's instructions before your message, so it works with every provider, and the chat shows what you typed. The turn keeps Caztor's rules and file tools; an agent that expects to run commands only reads and edits files here. When `.claude/skills` is PaperSmith's link to the workspace's `skills/`, the skill paths in the instructions are given through `skills/`, which Caztor's agent may read. Caztor's own agent (`caztor.md`) is not listed, and an agent never replaces a command of the same name.

### Account or API key

Each provider signs in with your subscription (**Account**) or with a key (**API key**), chosen in the chat header. The panel folds away once it has nothing left to ask. A provider you already signed in to on this computer counts as signed in from the start, so no sign-in is offered: Caztor checks that its CLI's own sign-in file is there (`~/.claude/.credentials.json` or `CLAUDE_CONFIG_DIR`, or `CLAUDE_CODE_OAUTH_TOKEN`; `~/.pi/agent/auth.json` or `PI_CODING_AGENT_DIR`, when it names a provider; `$XDG_DATA_HOME/opencode/auth.json`; `~/.gemini/antigravity-cli/antigravity-oauth-token`), without reading it. A sign-in that expired shows up at the next turn, as before.

| Subscription | Route |
|---|---|
| Claude Pro or Max | Claude Code in account mode |
| ChatGPT | opencode in account mode, with a model your plan accepts. Accepted models vary: `openai/gpt-5.5` was rejected in October 2026 and `openai/gpt-5.6-terra` worked |
| Google | Antigravity, account mode only |
| Any provider Pi can sign in to | Pi in account mode (run `pi`, then `/login`) |

Pi in API key mode keeps one key per vendor (`pi:anthropic`, `pi:openai`, `pi:google`, `pi:openrouter`, `pi:groq`, `pi:xai`, `pi:mistral`, `pi:deepseek`, `pi:cerebras`, `pi:opencode`), so it needs a model written `provider/model` to know which key to use. The key reaches Pi only as that vendor's environment variable, never on the command line, and Pi then runs with an empty agent folder (`.caztor/pi-agent-api`), so a saved login cannot win over the key.

Keys are stored in `$XDG_CONFIG_HOME/caztor/credentials.json` (or `~/.config/caztor/credentials.json`), mode 0600 in a 0700 folder, outside the project. The browser can set or delete a key but never read it back; it sees only whether one is set and its last four characters. A key reaches only the provider and vendor it belongs to.

**Upgrade note:** an exported `ANTHROPIC_API_KEY` no longer reaches Claude Code in account mode, and opencode account mode ignores exported vendor keys. To bill an API, choose API key mode and store the key.

### Isolation from your global CLI configuration

The assistant runs without your personal setup, so a turn is predictable and cheap (an unisolated one-word Claude turn measured about 25,000 input tokens). What that means for you:

- Your personal **MCP servers, hooks, plugins, skills and global `CLAUDE.md`** are not available to the chat assistant.
- For opencode, a separate configuration folder is used (`.caztor/opencode-xdg` in the project), so **custom providers defined in your global opencode config are hidden**. Your sign-in is kept. Caztor does not run opencode with your own configuration to find out which providers that hides.
- A turn is stopped with an "isolation failed" message if the assistant reports a tool outside the allowed set (read, edit, write, search), for example `Bash` or an MCP tool.
- Claude Code **still writes its own session transcripts** under `~/.claude/projects`; Caztor cannot prevent that.

### Antigravity: partial isolation

Antigravity cannot be isolated like the other providers, and the chat says so for as long as it is active:

- Your global settings, skills, agents and MCP servers in `~/.gemini/` may load, and no flag turns them off.
- Every turn stores your prompts, transcripts and conversation state under `~/.gemini/antigravity-cli/`.
- The agent definition allows six file tools and sets `commandExecutionPolicy: off`, yet `agy` still announces about 60 tools, including `run_command`. In a real test the model declined to run a command, which does not prove the CLI would block one.
- Caztor stops the turn when a tool outside the six appears, but **that tool may already have started**, so this limits damage and does not prevent it.
- A file under `.agents/` other than Caztor's definition blocks the chat until you review and trust it.
- A tool that `agy` denies still ends the turn in success; Caztor shows a warning naming it.

### Pi: partial isolation

Pi turns off everything it would load from the project (its `.pi/` folder, extensions, skills, prompt templates, themes, MCP servers and `AGENTS.md` or `CLAUDE.md` context files), runs offline from its own update checks, and gets only the tools `read`, `edit`, `write`, `grep`, `find` and `ls`. It is still partly isolated, and the chat says so for as long as it is active:

- In account mode your global Pi settings and sign-in in `~/.pi/agent/` load, and no flag turns them off.
- Caztor stops the turn when any other tool appears, for example `bash` or an MCP tool, but **that tool may already have started**.
- Pi's sessions are kept in the project, under `.caztor/pi-sessions`. The project's `.pi/` folder belongs to PaperSmith and Caztor never writes to it, so Pi needs no trust step.

### Agent definitions

The assistant's instructions live in the repository's `agents/` folder (`claude.md`, `opencode.md`, `codex.md`, `antigravity.md`, `pi.md`). Before the first turn of a provider, Caztor copies the matching file into your project:

| Provider | Written to | Ownership |
|---|---|---|
| Claude Code | `.claude/agents/caztor.md` | The whole file |
| opencode | `.opencode/agents/caztor.md` | The whole file |
| Codex | `AGENTS.md` | Only a block between `<!-- caztor:agent:begin -->` and `<!-- caztor:agent:end -->`; the rest of your file is untouched |
| Pi | `.caztor/agents/pi.md` | The whole file. Pi has no agent files, so this is passed as its system prompt (`--system-prompt`) |

A file you edited yourself is never overwritten (the chat offers a "Replace" action). Deleting the files, or the marked block, removes Caztor's instructions again. These folders are hidden from the file tree and left out of snapshots. opencode also installs its own plugin package (about 62 MB) into `.caztor/opencode-xdg` and into the project's `.opencode/`; both stay hidden and outside snapshots, and neither is a reason to ask for trust (see below). Caztor creates `.caztor/opencode-xdg` itself, readable only by you, and refuses to start opencode if it or `.caztor` is a symbolic link. Before each turn it checks that the folder holds only what opencode writes there (`opencode/opencode.json[c]` with display settings only, `.gitignore`, `node_modules`) and empties it otherwise, so a configuration planted there cannot run with your turn.

### Writing guides

Next to the definition, every turn makes sure the project holds a set of advisory writing guides in `.caztor/guides/`: ten guides (abstract, introduction, related work, methods, experimental set-up, results and discussion, limitations, conclusions, title and keywords, back matter), an `INDEX.md`, and `LICENSE-papersmith-ai.txt`. They are written before the snapshot, hidden from the file tree, refused by the file API, and left out of snapshots and the changed-files list. The definitions tell the assistant to read `.caztor/guides/INDEX.md` and then only the guide for the section it is working on, and to treat the guides as advice: your request, your document's structure and the venue template win. The same definitions allow the assistant to read `.caztor/build/last-compile.log` and `.caztor/guides/` and nothing else inside `.caztor/`, and never to write there.

- **Source.** The guides in the repository's `guides/` folder are condensed from the section guides of [papersmith-ai](https://github.com/Daprosero/papersmith-ai) at commit `1f09516` (Apache License 2.0). `node scripts/distill-guides.ts <papersmith-checkout>` regenerates them from that commit; `guides/SOURCE.json` records what was kept and removed. The licence text is shipped as `LICENSES/Apache-2.0.txt` and provisioned as `.caztor/guides/LICENSE-papersmith-ai.txt`; the notice is in [`NOTICE.md`](NOTICE.md).
- **Your edits.** A guide you changed is never overwritten (the chat names the guide and offers "Replace"); a guide you deleted is written again on the next turn; a guide that is a link is never written through. A problem with the guides never stops a turn: the chat says the guides are unavailable and the turn goes on.
- **Updates.** New guides do not start a new conversation; a change to the agent definition does, once, and the chat says so.
- **Removal.** The provisioner removes only files whose content still matches what it wrote, and the guides go with the last provisioned definition. Until then a deleted guide is written again on the next turn.

### A project's own CLI configuration

A project folder can carry configuration that makes the assistant's program start other programs, so opening a project you did not write could run code. Before a turn Caztor looks for it:

| Provider | Files and folders that count |
|---|---|
| Claude Code | `.mcp.json`, `.claude/settings.json`, `.claude/settings.local.json` |
| opencode | `opencode.json` or `opencode.jsonc` (in the project, or in a parent folder up to the repository root) and `.opencode/opencode.json[c]`, unless they hold only display settings; and non-empty `.opencode/plugins/`, `tools/` or `commands/` folders |

If any exist, the turn is refused with an "isolation failed" message and the chat lists the files. **Review project configuration** opens a dialog; the default button is Cancel, and **Trust this project's CLI configuration** records your choice in `.caztor/state.json` as a seal of the files' hash: an HMAC with a key kept outside every project, in `<config>/caztor/trust.key` (600, never mounted in any sandbox), so a later change to any of the files asks again, and a record someone else writes into the project does not count. A confirmation made before this seal existed is asked for once more. Without a configuration folder the key lives only in memory, and a confirmation lasts until Caztor stops. Only you, the host, can trust; a collaborator gets 403. opencode's own checks (its version and model list) never run inside the project folder: opencode is started with `--pure` in a private temporary folder that is deleted afterwards. Codex has no such check, because its project configuration could not be tested here.

## Build recipe for a source that is not a document

Some projects keep their text in a file that does not compile by itself: a PaperSmith workspace can keep `paper/main.tex` as its store of blocks and build the paper with a script. Declare that build in `.caztor/build.json`:

```json
{ "when": ["paper/main.tex"], "before": ["python3", "paper/build_preview.py"], "root": "paper/preview.tex" }
```

Compiling a file listed in `when` (Compile, auto-compile, or Compile <file>) first runs `before` in the project folder, as an argument list without a shell, then compiles `root` and shows its PDF. Other files compile as before.

- It runs only once you confirm it on this computer: `npm start -- trust-build <projectDir>` checks the file, shows what will run and keeps an HMAC of its exact bytes in `.caztor/build.seal`, made with Caztor's private trust key. A recipe that arrives with a project (a clone, a shared folder, an archive), or one changed after you confirmed it, is refused with that command in the problem list.
- The step is your project's own code and runs as you, with the engine's environment only (`PATH`, `HOME`, cache, proxy and `TMPDIR`; never API keys). It is stopped after 2 minutes and when you cancel the compile.
- A sandboxed compile refuses to run it, and so does every compile once collaborators can reach the server, since those compiles always run in the sandbox.
- A step that fails shows its exit code and the end of its output in the problem list, and nothing is compiled.

## Snapshots and undo

Before every assistant turn Caztor saves a snapshot of the project's files (the newest 20 turns are kept, large or numerous files are skipped and reported). After the turn the chat lists the changed files. **Undo** puts the files back as they were; if you edited a file yourself after the turn, you choose between a strict undo that stops, skipping those files, or forcing it. Text you typed in the editor during a turn is not attributed to the assistant.

## Disclosed limits

Caztor does not claim to be a sandbox. Open only projects you trust. The first-use window says the same.

- **Compiling can read any file you can read.** Tectonic is not confined to the project: a document can `\input` a file elsewhere in your home folder and put its text in the PDF or log. Shell escape stays disabled. This is accepted by default; the [sandbox](#opt-in-compile-sandbox) removes it when you enable it.
- **Agent reads are not confined to the project**, and **whatever an agent reads is sent to the model provider** (Anthropic, OpenAI or the provider you chose in opencode).
- **A project's own CLI configuration can run programs** once you trust it (see above). Trust it only for projects you wrote or know.
- **The provider CLI may put account details in the model's context**, for example the signed-in email address.
- **Codex can run commands** on your computer, inside its own sandbox (`--sandbox workspace-write`). Caztor cannot turn this off. Claude Code and opencode are restricted to file tools.
- Claude Code writes session transcripts under `~/.claude/projects` (see above).
- **Antigravity is only partly isolated** and may start a disallowed tool before Caztor stops the turn (see above).
- **Pi is only partly isolated**: its global settings and sign-in load, and it may start a disallowed tool before Caztor stops the turn (see above).

## Opt-in compile sandbox

Off by default. When `bwrap` is installed and unprivileged user namespaces work on your kernel (Linux and WSL2), the compile options show **Sandboxed compile (experimental)**. Caztor decides this with a trial run of Tectonic inside bubblewrap when the page opens; if it fails, the option is hidden and the reason is listed in the session data.

Inside the sandbox Tectonic can read:

- the project folder (read-only),
- the Tectonic binary and the shared libraries it links against,
- the system folders and a few network files it needs (`/usr`, `/lib*`, `/bin`, `/etc/resolv.conf`, certificates, fonts),
- the Tectonic cache (`~/.cache/tectonic`, or `$TECTONIC_CACHE_DIR`).

It can write only `.caztor/build` and the cache. It sees a private `/tmp` and nothing else of your home folder. **The network stays available**, because package downloads need it, so the sandbox limits what a document can read, not what the engine can send. If the sandbox cannot start, the compile fails with a message telling you to turn the option off.

## The local server's security model

Unless you share it (next section), the server accepts connections only on `127.0.0.1`. Every `/api` request must carry a launch token (32 random bytes made at startup, kept in memory and handed to the page inside `index.html`), the `Host` header must be the loopback address with the server's port, and a request with an `Origin` must come from that address. State-changing requests must be JSON (uploads: `application/octet-stream`). There are no CORS headers, and the page is served with a strict Content-Security-Policy. A web page on another site cannot call the server, but any program running as your user can read the printed address and the page.

## Sharing with collaborators (first version)

Collaborators use only a browser: you send each person an invite, which is a link plus a random access key, and they type the key on the page the link opens. Without the options below nothing changes: Caztor listens on loopback and your own browser works as before.

**Start Caztor reachable.** The recommended way is [Tailscale](https://tailscale.com): only devices on your tailnet can reach it, and `tailscale serve` adds HTTPS with your machine's MagicDNS name.

```sh
# Caztor stays on loopback; tailscale serve fronts it with HTTPS on your MagicDNS name.
tailscale serve --bg 4317
npm start -- path/to/project --public-name box.tail1234.ts.net --secure
```

Without a proxy, bind an address yourself, and name every host name collaborators type (with the port when it is not 80):

```sh
npm start -- path/to/project --host 100.101.102.103 --public-name box.tail1234.ts.net:4317
```

- `--host <address>` (`CAZTOR_HOST`): the IP address to bind, `127.0.0.1` by default. Anything but loopback is refused without a public name.
- `--public-name <name[:port]>` (`CAZTOR_PUBLIC_NAME`, comma separated; repeatable): the names allowed in `Host` and `Origin` besides loopback. Invite links use the first one.
- `--secure` (`CAZTOR_SECURE=1`): a TLS proxy fronts Caztor, so cookies get `Secure` and links and allowed origins use `https://`.

**Sign yourself in.** Once a public name is set, a browser without a session gets only "Ask the host for an invite link and its access key", even on `127.0.0.1`, because a proxy such as `tailscale serve` reaches Caztor through loopback too. At start Caztor prints a host link (`http://127.0.0.1:4317/host/...`): open it once and that browser is the host. It works once per launch; restart Caztor for a new one.

**Invite someone, step by step.**

1. In the app, open **Collaborators** in the header, type the person's name, and choose how long the key lasts: 1 hour, 1 day, 7 days (the default), 30 days, or until a date and time you pick (from 10 minutes to 365 days).
2. Press **Invite**. The dialog shows the link (`https://<public name>/invite/<id>`), the access key (four groups of five characters, such as `K7MQ2-XW4TR-9HJNP-3BVCE`), each with a copy button, and when the key expires. The key is shown only this once; Caztor keeps only its SHA-256 hash.
3. Send the person the link and the key, apart if you can (for example the link by mail and the key by message). The link holds no secret: a chat app that fetches it for a preview signs nobody in and uses nothing up.
4. They open the link, type the key (with or without dashes, in either case) and press **Sign in**. That browser is signed in with a cookie session. The same key signs in their other browsers too, such as a phone, until it expires.
5. When the key expires, it stops working and every browser signed in with it is signed out. Make a new invite for that person to keep going; inviting the same name again adds a key to the same person, with the same chat and logins.

The dialog lists, per person, how many browsers are signed in and each key's state: "expires in 6 days", "expired", "locked after 10 wrong keys", or "old invite, create a new one" for a one-time link made before this version (those no longer work; sessions they opened keep working until you revoke them). **Revoke key** ends one key and the browsers it signed in; **Revoke** removes the person, every key and every browser of theirs.

From a terminal, with the same public name and `--secure` as the server:

```sh
npm start -- invite "Ana" --for 7d --public-name box.tail1234.ts.net --secure   # prints the link, the key and the expiry
npm start -- invite "Ana" --for 2026-12-01T18:00 --public-name box.tail1234.ts.net
npm start -- users                 # people, their browsers, and each key's id and expiry
npm start -- revoke <id>           # a person's id removes the person; a key's id ends that key
```

`--for` takes `90m`, `24h`, `7d` or the date and time the key ends (ISO 8601); without it a key lasts 7 days. The commands change the users store directly (under a lock); the running server reads it on every check, so a revoke signs the person out at once. A folder named `invite`, `users` or `revoke` is opened as `./invite`.

**What is stored.** `<config>/caztor/users.json` (next to the key store, `~/.config/caztor` by default), mode 600 in a 700 folder: names, roles, invite ids with their expiry and wrong-key count, and SHA-256 hashes of session secrets and access keys, never the raw values. Each session made with a key carries that key's expiry and is refused from then on. A store of the first version loads as it is and is written in the new format on the next change. A session cookie is HttpOnly and SameSite=Strict, and its page carries a token of its own, never your launch token. The sign-in page posts the key back to its own link, with no script, and only from an allowed `Origin`. A wrong, expired, locked or unknown key gets the same 403 page, with nothing about why. After 10 wrong keys an invite locks, so even the right key no longer works, and the dialog shows it as locked. After twenty failed sign-ins or twenty failed cookie checks per address and minute, further failures get 429; a valid key, host link or session always works, because behind a proxy everyone shares one address.

**Compiles.** Once a public name is set, every compile, yours too, runs in the [compile sandbox](#opt-in-compile-sandbox), whatever the project setting says, because a collaborator can write the source and the engine would otherwise read any file it is given a path to. Without bubblewrap compiles are refused with a message saying so. Only you can change the sandbox setting.

**What is shared, and what is not yet.**

- Shared: the projects in the navigator, files, compile and project settings, and the undo snapshots, because the files are shared. A collaborator cannot open a folder that is not in the project list.
- Per person: the chat history (a collaborator's in `<config>/caztor/users/<user id>/chat/<project key>/<provider>.jsonl`, outside the project, where no agent turn sees it; yours stays in `.caztor/chat/<provider>.jsonl`), agent sessions, the chosen provider and model, auth modes (kept under `users` in `.caztor/state.json`; yours stay where they were, and a project only you use never gets the key), API keys (`<config>/caztor/users/<user id>/credentials.json`, 600 in a 700 folder; yours stay in `<config>/caztor/credentials.json`) and what turns show about the CLI login. Each collaborator also has a private folder, `<config>/caztor/users/<user id>/home` (700, outside every project), that their turns use as `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, the `XDG_*` folders and `PI_CODING_AGENT_DIR`; agy gets only `HOME` and no D-Bus, so its login is written to a file there.
- One turn at a time per project, whoever runs it. Someone else's send, stop or undo is refused with "<name> has a turn running. Wait for it to finish." Only the person who ran a turn can follow it, running or finished; anyone else gets 404 with nothing of it. Only the person who ran a turn can undo it, you included, also after a restart: a collaborator's turn is known from their kept history. A turn nobody else ran stays yours to undo, as before.
- Each person chats with their own subscription or key: collaborators sign in from the browser (below), and their turns run sandboxed.

**Collaborator turns run sandboxed.** Every agent turn of a collaborator, with any of the five CLIs, runs inside [bubblewrap](https://github.com/containers/bubblewrap); yours never do. Inside, the CLI sees:

- the project, read-write, except its `.caztor/` folder, which is an empty tmpfs: your chat, the project state (with the trust records and your sessions), the snapshots and your CLI folders do not exist there. Back come, read-only, `.caztor/agents`, `.caztor/guides` and `.caztor/build`, and, writable, the per-turn folders the runners use (`opencode-xdg`, `opencode-data-api`, `pi-sessions`, `pi-agent-api`), each one the person's own, from `<private home>/.caztor-turns/<project key>/`;
- the project files your own turns load only after you trusted them, read-only when they exist: `.claude/`, `.opencode/`, `.agents/`, `.mcp.json`, `opencode.json[c]`. One a collaborator's turn creates is new to the trust check, so your next turn asks you again;
- the person's private folder, read-write, as `HOME` (every CLI's config folder is in it);
- read-only: `/usr`, `/lib*`, `/bin`, `/sbin`, the network and certificate files of `/etc`, `/etc/passwd` and `/etc/group`, and the CLI's own install folder found from its real path (the file itself, such as `~/.local/share/claude/versions/<v>` or `~/.local/bin/agy`, or the whole package prefix, such as the Homebrew prefix for opencode, pi and codex together with the `node` their first line names). A prefix inside your home (npm's `~/.local`) is never mounted: only the package's own folder (`~/.local/lib/node_modules/<package>`); a broad folder of your home (`~/.local`, `~/.config` and the like) is refused;
- an empty tmpfs over your home, so nothing else of it shows; a private `/tmp`; the network.

There is no D-Bus socket and no `XDG_RUNTIME_DIR`, new namespaces except the network's, a new session, and the sandbox ends with Caztor. Caztor's config folder is never mounted beyond the person's own home: no one sees the users store, the key stores, their own chat history or anyone else's private folder. The first turn of each CLI and person runs `<cli> --version` inside the sandbox; if bwrap is missing or that fails, the turn is refused with the reason (`isolation_failed`), never run without the sandbox.

**Signing collaborators in to their subscriptions.** In account mode the chat's sign-in panel has a **Sign in** button. It runs the provider's own login on your machine, for that person: inside their sandbox, with their private folder as `HOME`, so the login lands there and never mixes with yours or anyone else's. A dialog relays the CLI's text (links open in a new tab), shows a device code with a copy button, and has a box for the code a web page gives back. Your own **Sign in** runs the same command without a sandbox, as a terminal of yours would; the terminal hint stays as a fallback.

| Provider | What runs | What the person does |
|---|---|---|
| Claude Code | `claude auth login --claudeai` | opens the link, signs in, pastes the code the page shows |
| Codex | `codex login --device-auth` | opens the link and enters the device code shown |
| opencode | `opencode auth login -p openai -m "ChatGPT Pro/Plus (headless)"`, or opencode's own menu in a terminal for other providers | enters the device code, or follows the menu with the arrow keys |
| Pi | `pi` in a terminal (`script`), with `/login` typed for them | picks a provider with the arrow keys, then follows its link or code |
| Antigravity | `agy` in a terminal (`script`): signed out, it starts with its login menu | picks Google OAuth, opens the link, pastes the code |

One sign-in at a time per person; starting another ends the first. It ends after 10 minutes, or a minute after the dialog stops asking for it. Only that person sees it. A pasted line is never shown back, and known token and key shapes are masked. When the CLI exits successfully (for Pi: when it writes its `auth.json`; for agy: when `agy models` succeeds in the same sandbox) the provider shows as signed in for that person.

**What the host installs.** The CLIs collaborators will use (`claude`, `codex`, `opencode`, `pi`, `agy`), on the `PATH` Caztor starts with; [bubblewrap](https://github.com/containers/bubblewrap) (`bwrap`), with unprivileged user namespaces allowed; and util-linux `script` in `/usr/bin` for Pi and agy. Collaborators install nothing.

**Tailscale, step by step.**

1. Install Tailscale on the host and sign in (`tailscale up`); turn on MagicDNS and HTTPS certificates in the admin console.
2. Share the machine with each collaborator from the admin console (or add them to your tailnet); they install Tailscale and sign in too.
3. Start Caztor on loopback behind `tailscale serve`, as above: `tailscale serve --bg 4317` and `npm start -- path/to/project --public-name <machine>.<tailnet>.ts.net --secure`.
4. Open the printed host link once, then invite each person and send them their link and access key.

## Tests

```sh
npx vitest run    # about 2,900 tests, no real binary and no network
npx tsc -b        # typecheck
```

Opt-in checks use real programs. They are skipped unless the variable is set:

| Command | What it does |
|---|---|
| `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local` | Real Tectonic compile, the [sandbox](#opt-in-compile-sandbox) checks (it downloads packages into a temporary cache), and detection of the installed CLIs. Spends no tokens. |
| add `CAZTOR_REAL_CLAUDE=1` | Two real Claude Code turns. **Spends tokens.** `CAZTOR_REAL_CLAUDE_TURNS=1` runs one. |
| add `CAZTOR_REAL_OPENCODE=1` | opencode detection. With `CAZTOR_REAL_OPENCODE_TURNS=1` and `CAZTOR_REAL_OPENCODE_MODEL=provider/model` it runs real turns. **Spends tokens.** |
| add `CAZTOR_REAL_CODEX=1` | Checks every flag Caztor passes against `codex exec --help`. Spends nothing. |
| add `CAZTOR_REAL_AGY=1` | Antigravity detection, which is free. With `CAZTOR_REAL_AGY_TURNS=1`, one real turn. **Spends quota.** |
| add `CAZTOR_REAL_PI=1` | Pi detection only (`pi --version` and `pi --list-models`). Spends nothing; there is no real Pi turn test. |
| `CAZTOR_PLAYWRIGHT=/path/to/playwright/index.mjs node e2e/compile.mjs` | Browser checks (also `e2e/dialog.mjs`, `e2e/chat.mjs`); needs the web app built and a Chromium. See `e2e/README.md`. |
| `CAZTOR_PAPERSMITH_DIR=/path/to/papersmith-ai npx vitest run guides` | Rebuilds the guides from the pinned papersmith-ai commit and compares them byte for byte with the committed ones. Needs a papersmith-ai checkout. |

`CAZTOR_REAL_REPORT=<file>` appends what each real step showed to a file.

## Project layout

| Path | Role | Runs in a browser or Worker? |
|---|---|---|
| `packages/core` | Domain: paths, ports (interfaces), compile queue, turn service, chat reducer | Yes (no Node imports) |
| `packages/api` | The HTTP API as a Hono app: routes, security middleware, SSE | Yes (Web APIs only) |
| `packages/adapters-local` | Node adapters: project folder, state, snapshots, Tectonic, sandbox, provider runners | No |
| `apps/server-local` | Starts the server: loopback bind, token, static files | No |
| `apps/web` | The React app | Yes |
| `agents/` | Canonical agent definitions | n/a |
| `guides/`, `LICENSES/`, `scripts/` | Distilled writing guides (generated), the Apache-2.0 text, and the script that regenerates the guides | n/a |
| `e2e/` | Opt-in browser checks | n/a |

`packages/core` and `packages/api` import no Node built-in; a test enforces it. Everything the app needs from the machine is behind a port, which keeps a future Cloudflare deployment possible: the web app on Pages, `core` and `api` on a Worker, and the local adapters replaced by cloud ones (R2 or Durable Objects for files, a container for Tectonic). **The terminal-backed chat is local-only**: it needs the provider command-line programs on your machine, so a hosted version would need an API-based assistant instead.

## Logos and notices

The provider logos are the owners' marks, used only to show which assistant is active. Caztor is independent and not affiliated with Anthropic, opencode or OpenAI. Their origin, hashes and terms are in [`NOTICE.md`](NOTICE.md).
