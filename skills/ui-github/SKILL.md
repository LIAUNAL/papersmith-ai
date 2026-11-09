---
name: ui-github
description: "Trigger: an operator wants to share the paper's dashboard (the Paper Command Center of `smith ui`) as a read-only web page on GitHub Pages, for viewing only. Exports a static snapshot of every panel (nothing runs: no server, no terminal, no agent, no phase execution), commits it as one orphan commit on the `gh-pages` branch of the workspace's GitHub remote, force-pushes it, enables Pages for that branch with `gh api` and reports the public URL. The site is PUBLIC even for a private repository. The masked AI history is included by default; `--no-ai-history` leaves it out. Runs only after the operator confirms the public URL and the AI-history choice; never edits a workspace file or the workspace's branches."
---

# UI on GitHub Pages

`smith ui` serves a live dashboard on the operator's machine. This skill puts a
**read-only copy** of it on the web, at
`https://<owner>.github.io/<repo>/`, so a co-author, a reviewer or a reader can
browse the paper's state without installing anything.

## What the page is

- A **snapshot**: every read-only answer the dashboard shows (pipeline, model,
  experiments, citations, novelty, atlas, the PDF preview) written as files on
  the date it was published. It does not change until it is published again.
- **Nothing runs.** There is no backend: buttons that type a slash command,
  launch a phase, open the terminal or write a file are hidden or refused
  (`STATIC_SNAPSHOT`). A banner says it is a read-only snapshot and its date.
- **Public.** A GitHub Pages site is public even when the repository is
  private (Pro, Team or Enterprise are needed to serve one from a private
  repository at all).
- **What is never published:** team and account data, credential status,
  absolute or home paths, the operator's PDF annotations, and any workspace
  file outside the snapshot's allow-list. The paper PDF (`paper/main.pdf`) and
  its figures are published **as they are**.
- **AI history:** included by default, with emails, names of the workspace's
  people, keys and tokens masked. `--no-ai-history` leaves the AI History tab
  and its conversations out entirely.

## Command

```
smith ui . --publish-pages --yes [--no-ai-history] [--snapshot-lang en,es]
           [--pages-branch gh-pages] [--pages-remote origin]
```

Treat `$ARGUMENTS` as flags for this command and pass them through
(`--no-ai-history`, `--snapshot-lang es`, `--pages-branch <name>`,
`--pages-remote <name>`); never add `--yes` before step 2.

## Steps

1. **Check the remote.** `git remote get-url origin` (or the remote named in
   `$ARGUMENTS`) must be a `github.com` repository. If it is not, stop and say
   so; do not create or change a repository.
2. **Confirm with the operator**, in one message, before anything is pushed:
   - the site will be PUBLIC at `https://<owner>.github.io/<repo>/`;
   - whether to include the masked AI history (default yes; `--no-ai-history`
     if they say no);
   - that the PDF and figures are published as they are.
   Wait for an explicit yes. Silence, a question or "maybe" is not a yes.
3. **Publish** only after that yes: run the command above with `--yes` and the
   flags the operator chose. It exports a fresh snapshot into a temporary
   directory outside the workspace, prints what it publishes (file count,
   size, AI history included or not), pushes one orphan commit to the Pages
   branch with `--force`, and makes Pages serve that branch (`gh api
   repos/<owner>/<repo>/pages`: created when missing, repointed when it
   serves another branch).
4. **Report** the site URL the command printed and that GitHub takes a minute
   or two to build it. If `gh` is missing or not authenticated, the branch is
   still published: relay the exact `gh api ... /pages` command it printed so
   the operator enables Pages once.

## Refusals

The command exits non-zero, publishing nothing, when:

- the workspace is not a git repository or has no remote of that name;
- the remote is not a GitHub repository;
- the snapshot export fails;
- it is not interactive and `--yes` was not given.

It never touches the workspace's working tree, index, HEAD or current branch:
the snapshot is committed with a temporary index and pushed by commit id.
Republishing replaces the previous snapshot (the Pages branch always holds a
single commit).
