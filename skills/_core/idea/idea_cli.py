#!/usr/bin/env python3
"""``smith idea``: the terminal front end of the idea-shaping phase (lane 2a).

    smith idea [VERB] [ROOT] [options]        (plain ``smith idea`` runs ``start``)
    python skills/_core/idea/idea_cli.py [VERB] [ROOT] [options]

Verbs: ``start`` (the six steps, one question at a time; non-interactive with
``--answers FILE.json``), ``show``, ``bank``, ``profile``, ``experience``,
``interests``, ``topics``, ``draft``, ``approve`` and ``handoff``. Each verb
records its step in ``.papersmith/idea_brief.json`` and prints a short text,
or one JSON object with ``--json`` (``{"ok": true, ...}``; a refusal is
``{"ok": false, "error": <CODE>, "message": ...}`` and exits 1). Usage errors
exit 2.
"""

from __future__ import annotations

import sys as _floor_sys
if _floor_sys.version_info < (3, 11):  # the package floor (pyproject requires-python >=3.11)
    _floor_sys.stdout.write('{"ok": false, "error": "PYTHON_VERSION_UNSUPPORTED", "message": "this skill needs '
                            'Python 3.11+; the running interpreter is %d.%d."}\n' % _floor_sys.version_info[:2])
    raise SystemExit(2)

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):  # run as a script: make `skills._core.idea` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.idea import bank, brief, draft, profile, topics  # noqa: E402
else:
    from . import bank, brief, draft, profile, topics

VERBS = ("start", "show", "bank", "profile", "experience", "interests", "topics", "draft", "approve", "handoff")
LAUNCH_HINT = ("Launch it from `smith ui` (Idea tab, \"Launch plausibility\") or paste the line above into "
               "the agent.")
STOPPED = ("Stopped. Your answers so far are kept in .papersmith/idea_brief.json; run `smith idea` again to "
           "continue.")

DESCRIPTION = """\
Idea shaping: an optional guided phase before /plausibility for a vague idea.
Six steps: (1) sources: banco-lia, another bank MCP server or none;
(2) profile: ORCID, OpenAlex author or a Google Scholar link; (3) experience;
(4) interests; (5) three candidate topics with evidence, pick or combine;
(6) a draft checked by the prompt gate, approved and handed off as
`/plausibility <draft>`. Everything is kept in .papersmith/idea_brief.json.
Without a verb, `start` runs."""


class Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
def build_parser(prog: str = "idea_cli.py") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, usage=f"{prog} [VERB] [ROOT] [options]", description=DESCRIPTION,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("root", nargs="?", default=None, metavar="ROOT",
                        help="the workspace root (default: --root, else the current directory)")
    common.add_argument("--root", dest="root_opt", metavar="DIR", help="the workspace root, like ROOT")
    common.add_argument("--json", action="store_true", help="print one JSON object on stdout")
    sub = parser.add_subparsers(dest="verb", metavar="VERB", title="verbs")

    def verb(name: str, summary: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=summary, description=summary)

    start = verb("start", "run the six steps, one question at a time (the default verb)")
    start.add_argument("--answers", metavar="FILE.json",
                       help="run without questions from a JSON file whose keys are the steps: bank, profile, "
                            "experience, interests, chosen, draft (and n, approve)")
    start.add_argument("--bank", metavar="CHOICE",
                       help="the source choice without asking: banco-lia, none, or a server of .mcp.json")
    start.add_argument("--yes", action="store_true",
                       help="approve the draft without asking when the prompt gate passes")

    verb("show", "print the recorded brief")

    bank_verb = verb("bank", "step 1, sources: list, probe, choose or add the knowledge bank")
    action = bank_verb.add_mutually_exclusive_group()
    action.add_argument("--list", action="store_true", help="list banco-lia and the other servers (default)")
    action.add_argument("--probe", metavar="SERVER", help="run tools/list on SERVER and say if it is compatible")
    action.add_argument("--choose", metavar="CHOICE", help="record the choice: banco-lia, none, or a server name")
    action.add_argument("--add", metavar="NAME", help="add a bank server to .mcp.json (with --command or --url)")
    bank_verb.add_argument("--command", metavar="CMD", help="the stdio command of the server added with --add")
    bank_verb.add_argument("--url", metavar="URL", help="the HTTP URL of the server added with --add")

    prof = verb("profile", "step 2, profile: find the author in OpenAlex and summarise their topics")
    prof.add_argument("--orcid", metavar="ID", help="ORCID iD (0000-0000-0000-0000 or its orcid.org URL)")
    prof.add_argument("--openalex", metavar="ID", help="OpenAlex author id (A...) or its URL")
    prof.add_argument("--scholar", metavar="URL",
                      help="a Google Scholar link, used only to read a name (Scholar is never scraped)")
    prof.add_argument("--name", metavar="NAME", help="the author's full name, searched in OpenAlex")

    exp = verb("experience", "step 3, experience: level, methods, data/equipment access and time")
    exp.add_argument("--level", choices=brief.LEVELS, help="research experience")
    exp.add_argument("--methods", metavar="LIST", help="methods you master, comma-separated")
    exp.add_argument("--resources", metavar="LIST", help="data or equipment you can access, comma-separated")
    exp.add_argument("--time", metavar="TEXT", help="time you can give the paper (e.g. 6 months)")

    interests = verb("interests", "step 4, interests: keywords, application domain and an admired paper")
    interests.add_argument("--keywords", metavar="LIST", help="keywords or themes, comma-separated")
    interests.add_argument("--domain", metavar="TEXT", help="the application domain")
    interests.add_argument("--admired", metavar="TEXT", help="a paper you admire (title or DOI)")

    top = verb("topics", "step 5, topics: propose three with evidence, then pick or combine")
    top.add_argument("--propose", action="store_true", help="propose topics from the brief and record them")
    top.add_argument("--n", type=int, default=topics.DEFAULT_N, help="how many topics to propose (default 3)")
    top.add_argument("--choose", metavar="IDS", help="the topics picked: t1, or t1,t3 to combine")
    top.add_argument("--note", metavar="TEXT", help="the angle you want, recorded with the pick")

    dr = verb("draft", "step 6, draft: compose, write or check the base idea")
    dr.add_argument("--compose", action="store_true", help="compose the draft from the chosen topics")
    dr.add_argument("--text", metavar="TEXT", help="record your own draft (- reads stdin)")
    dr.add_argument("--check", action="store_true",
                    help="only score the draft (--text, else the recorded one) with the prompt gate")

    verb("approve", "approve the draft; refused while the prompt gate fails")
    verb("handoff", "print `/plausibility <draft>` for the approved draft")
    return parser


def normalize(argv: list[str]) -> list[str]:
    """``start`` when no verb is named; the verb first when options precede it."""
    index = next((i for i, token in enumerate(argv) if token in VERBS), None)
    if index is None:
        return argv if any(t in ("-h", "--help") for t in argv) and not argv[1:] else ["start", *argv]
    return [argv[index], *argv[:index], *argv[index + 1:]]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _bank_line(b: dict[str, Any]) -> str:
    choice = b.get("choice")
    if not choice:
        return "not chosen"
    if choice == "none":
        return "none (no bank is queried)"
    state = "reachable" if b.get("available") else "unreachable"
    if b.get("available"):
        state += ", compatible" if b.get("compatible") else ", not compatible"
    line = f"{b.get('server')} ({state})"
    return line + (f": {b['reason']}" if b.get("reason") else "")


def _profile_line(p: dict[str, Any]) -> str:
    if p.get("source") == "openalex":
        names = ", ".join(f"{t['name']} ({t['count']})" for t in p.get("topics", [])[:4])
        return (f"{p.get('display_name')} (OpenAlex {p.get('openalex_author')}, {p.get('works_count')} works)"
                + (f"; topics: {names}" if names else ""))
    return f"not found: {p['reason']}" if p.get("reason") else "not given"


def _topic_lines(items: list[dict[str, Any]], chosen: list[str]) -> list[str]:
    lines = []
    for number, topic in enumerate(items, start=1):
        mark = " [chosen]" if topic.get("id") in chosen else ""
        lines.append(f"  {number}) {topic['title']}{mark}")
        lines.append(f"     {topic.get('rationale', '')}")
        for item in topic.get("evidence", []):
            lines.append(f"     - [{item['source']}] {item['detail']}")
    return lines


def _gate_line(gate: dict[str, Any]) -> str:
    verdict = "passes" if gate.get("ok") else "fails"
    missing = " ".join(gate.get("missing") or [])
    return f"Prompt gate: {verdict} (score {gate.get('score')})" + (f". {missing}" if missing else "")


def summary(b: dict[str, Any]) -> list[str]:
    exp, inter, d = b["experience"], b["interests"], b["draft"]
    lines = [f"Idea brief ({brief.PATH})",
             f"1 Sources: {_bank_line(b['bank'])}",
             f"2 Profile: {_profile_line(b['profile'])}",
             f"3 Experience: level {exp.get('level') or '-'}; methods {', '.join(exp.get('methods') or []) or '-'}; "
             f"resources {', '.join(exp.get('resources') or []) or '-'}; time {exp.get('time') or '-'}",
             f"4 Interests: keywords {', '.join(inter.get('keywords') or []) or '-'}; domain "
             f"{inter.get('domain') or '-'}; admired paper {inter.get('admired_paper') or '-'}",
             "5 Topics:" + ("" if b["topics"] else " none proposed")]
    lines += _topic_lines(b["topics"], b["chosen"].get("topic_ids") or [])
    if d.get("text"):
        lines += [f"6 Draft ({'approved' if d.get('approved') else 'not approved'}): {d['text']}",
                  "  " + _gate_line(d.get("gate") or {})]
    else:
        lines.append("6 Draft: none")
    return lines


# --------------------------------------------------------------------------
# Verbs
# --------------------------------------------------------------------------
def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root or args.root_opt or ".").expanduser().resolve()
    if not (root / ".papersmith").is_dir():
        raise Refusal("NOT_A_WORKSPACE", f"{root} is not a papersmith workspace (no .papersmith/)")
    return root


def run_show(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    b = brief.load(root)
    return {"brief": b, "path": brief.PATH}, summary(b)


def run_bank(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    if (args.command or args.url) and not args.add:
        raise Refusal("USAGE", "--command and --url go with --add NAME")
    if args.add:
        added = bank.add_server(root, args.add, command=args.command, url=args.url)
        return {"added": added}, [f"Added {added['server']} to .mcp.json; choose it with "
                                  f"`smith idea bank --choose {added['server']}`."]
    if args.probe:
        result = bank.probe(root, args.probe)
        return {"server": args.probe, **result}, [f"{args.probe}: " + _bank_line(
            {"choice": "other", "server": args.probe, **result})]
    if args.choose:
        chosen = bank.choose(root, args.choose)
        return {"bank": chosen}, [f"Sources: {_bank_line(chosen)}"]
    listing = bank.choices(root)
    current = brief.load(root)["bank"]
    others = [f"  {o['server']} ({o['transport']}: {o.get('url') or ' '.join([o['command'], *o['args']])})"
              for o in listing["others"]]
    return {**listing, "bank": current}, [
        f"Current choice: {_bank_line(current)}", f"Managed: {listing['managed']}",
        "Other servers in .mcp.json:" + ("" if others else " none (add one with --add NAME --command|--url)"),
        *others]


def run_profile(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    ids = {"orcid": args.orcid, "openalex_author": args.openalex, "scholar_url": args.scholar, "name": args.name}
    if not any(ids.values()):
        current = brief.load(root)["profile"]
        return {"profile": current}, [f"Profile: {_profile_line(current)}"]
    result = brief.record(root, "profile", profile.lookup(**ids))["profile"]
    return {"profile": result}, [f"Profile: {_profile_line(result)}"]


def run_experience(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    data = {k: v for k, v in {"level": args.level, "methods": args.methods, "resources": args.resources,
                              "time": args.time}.items() if v is not None}
    b = brief.record(root, "experience", data) if data else brief.load(root)
    return {"experience": b["experience"]}, summary(b)[3:4]


def run_interests(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    data = {k: v for k, v in {"keywords": args.keywords, "domain": args.domain,
                              "admired_paper": args.admired}.items() if v is not None}
    b = brief.record(root, "interests", data) if data else brief.load(root)
    return {"interests": b["interests"]}, summary(b)[4:5]


def run_topics(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    if args.propose:
        topics.propose(root, args.n)
    if args.choose:
        topics.choose(root, args.choose, args.note)
    b = brief.load(root)
    lines = (["Topics:"] + _topic_lines(b["topics"], b["chosen"].get("topic_ids") or [])) if b["topics"] else \
        ["No topics yet: run `smith idea topics --propose` after giving keywords or a profile."]
    return {"topics": b["topics"], "chosen": b["chosen"]}, lines


def run_draft(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    text = sys.stdin.read() if args.text == "-" else args.text
    if args.check:
        target = text if text is not None else brief.load(root)["draft"].get("text", "")
        gate = draft.check(target)
        return {"gate": gate, "text": " ".join(str(target).split())}, [_gate_line(gate)]
    if text is not None:
        result = draft.store(root, text)
    elif args.compose:
        result = draft.compose(root)
    else:
        result = brief.load(root)["draft"]
    return {"draft": result}, [f"Draft: {result.get('text') or 'none'}", _gate_line(result.get("gate") or {})]


def run_approve(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    result = draft.approve(root)
    line = draft.handoff(root)
    return {"draft": result, "handoff": line}, ["Draft approved. Launch plausibility with:", line, LAUNCH_HINT]


def run_handoff(root: Path, args: argparse.Namespace) -> tuple[dict, list[str]]:
    line = draft.handoff(root)
    return {"handoff": line}, [line]


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------
def _bank_spec(value: Any) -> tuple[str, str | None]:
    if isinstance(value, dict):
        return str(value.get("choice") or ""), (str(value["server"]) if value.get("server") else None)
    return str(value or ""), None


def _profile_spec(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return profile.identify(value)
    if not isinstance(value, dict):
        return {}
    keys = {"orcid": "orcid", "openalex_author": "openalex_author", "openalex": "openalex_author",
            "scholar_url": "scholar_url", "scholar": "scholar_url", "name": "name"}
    return {keys[k]: v for k, v in value.items() if k in keys and v}


def _finish(root: Path, approve: bool) -> tuple[dict, list[str], int]:
    if approve:
        draft.approve(root)
        b = brief.load(root)
        line = draft.handoff(root)
        return {"brief": b, "handoff": line}, summary(b) + ["Draft approved. Launch plausibility with:",
                                                            line, LAUNCH_HINT], 0
    b = brief.load(root)
    return {"brief": b, "handoff": None}, summary(b) + ["Approve the draft with `smith idea approve`."], 0


def start_from_answers(root: Path, args: argparse.Namespace) -> tuple[dict, list[str], int]:
    try:
        answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("ANSWERS_UNREADABLE", f"cannot read {args.answers}: {exc}") from None
    if not isinstance(answers, dict):
        raise Refusal("ANSWERS_UNREADABLE", f"{args.answers} is not a JSON object")
    choice, server = _bank_spec(args.bank) if args.bank else _bank_spec(answers.get("bank"))
    if choice:
        bank.choose(root, choice, server)
    elif not brief.load(root)["bank"].get("choice"):
        bank.choose(root, "none")
    ids = _profile_spec(answers.get("profile"))
    if ids:
        brief.record(root, "profile", profile.lookup(**ids))
    for step in ("experience", "interests"):
        if isinstance(answers.get(step), dict):
            brief.record(root, step, answers[step])
    proposed = topics.propose(root, int(answers.get("n") or topics.DEFAULT_N))
    chosen = answers.get("chosen")
    note = None
    if isinstance(chosen, dict):
        chosen, note = chosen.get("topic_ids"), chosen.get("note")
    if chosen or proposed:
        topics.choose(root, chosen or [proposed[0]["id"]], note)
    text = answers.get("draft")
    if isinstance(text, dict):
        text = text.get("text")
    if text:
        draft.store(root, str(text))
    else:
        draft.compose(root)
    return _finish(root, bool(args.yes or answers.get("approve") is True))


class _Asker:
    def __init__(self, ask: Callable[[str], str], say: Callable[[str], None]) -> None:
        self.ask_raw, self.say = ask, say

    def ask(self, prompt: str) -> str:
        return self.ask_raw(prompt).strip()


def _ask_bank(root: Path, io: _Asker) -> dict[str, Any]:
    while True:
        listing = bank.choices(root)
        others = listing["others"]
        io.say("1/6 Sources: which knowledge bank should guide the topics?")
        io.say("  1) banco-lia: the lab's bank of papers and projects (managed by smith)")
        io.say("  2) another bank MCP server: " + (", ".join(o["server"] for o in others) if others
                                                    else "none in .mcp.json yet; you can add one"))
        io.say("  3) none: no bank; only your profile, interests, OpenAlex and Asta")
        answer = io.ask("Choose 1, 2 or 3: ").lower()
        if answer in ("1", "banco-lia"):
            result = bank.choose(root, "banco-lia")
        elif answer in ("3", "none"):
            return bank.choose(root, "none")
        elif answer == "2":
            for number, other in enumerate(others, start=1):
                io.say(f"  {number}) {other['server']} ({other['transport']})")
            io.say("  +) add a new server")
            pick = io.ask("Server number, or + to add one: ")
            if pick == "+":
                name = io.ask("Server name: ")
                spec = io.ask("Its command (e.g. uvx my-bank-mcp) or URL: ")
                try:
                    added = bank.add_server(root, name, **({"url": spec} if spec.startswith(("http://", "https://"))
                                                           else {"command": spec}))
                except brief.IdeaError as exc:
                    io.say(f"Not added: {exc.message}")
                    continue
                server = added["server"]
            elif pick.isdigit() and 1 <= int(pick) <= len(others):
                server = others[int(pick) - 1]["server"]
            else:
                io.say("Not a listed server.")
                continue
            try:
                result = bank.choose(root, "other", server)
            except brief.IdeaError as exc:
                io.say(f"Not chosen: {exc.message}")
                continue
        else:
            io.say("Answer 1, 2 or 3.")
            continue
        io.say(f"Sources: {_bank_line(result)}")
        while not result.get("available"):
            again = io.ask("[r]etry, [c]hange the choice, or [k]eep it and continue: ").lower()
            if again.startswith("r"):
                result = bank.choose(root, result["choice"], result["server"])
                io.say(f"Sources: {_bank_line(result)}")
            elif again.startswith("c"):
                break
            elif again.startswith("k"):
                return result
        else:
            return result


def _ask_level(io: _Asker) -> str | None:
    while True:
        answer = io.ask("3/6 Experience: your level, 1 student, 2 early-career, 3 experienced, 4 senior "
                        "(Enter to skip): ").lower()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(brief.LEVELS):
            return brief.LEVELS[int(answer) - 1]
        if answer in brief.LEVELS:
            return answer
        io.say("Answer 1 to 4.")


def _interactive(root: Path, args: argparse.Namespace, io: _Asker) -> tuple[dict, list[str], int]:
    io.say("Idea shaping: six short steps before /plausibility. Enter skips a question; Ctrl-C stops and "
           "keeps what you answered.")
    if args.bank:
        result = bank.choose(root, *_bank_spec(args.bank))
        io.say(f"1/6 Sources: {_bank_line(result)}")
    else:
        _ask_bank(root, io)

    raw = io.ask("2/6 Profile: your ORCID iD, OpenAlex author id, Google Scholar link or full name "
                 "(Enter to skip): ")
    if raw:
        ids = profile.identify(raw)
        found = profile.lookup(**ids)
        if found["source"] != "openalex" and ids.get("scholar_url") and not profile.scholar_name(raw):
            name = io.ask("The Scholar link carries no name (smith never scrapes Scholar); your full name: ")
            if name:
                found = profile.lookup(scholar_url=raw, name=name)
        brief.record(root, "profile", found)
        io.say(f"Profile: {_profile_line(found)}")

    level = _ask_level(io)
    methods = io.ask("Methods you master (comma-separated, Enter to skip): ")
    resources = io.ask("Data or equipment you can access (comma-separated, Enter to skip): ")
    time_text = io.ask("Time you can give the paper (e.g. 6 months, Enter to skip): ")
    brief.record(root, "experience", {"level": level, "methods": methods, "resources": resources,
                                      "time": time_text})

    keywords = io.ask("4/6 Interests: keywords or themes (comma-separated): ")
    domain = io.ask("Application domain (Enter to skip): ")
    admired = io.ask("A paper you admire, title or DOI (Enter to skip): ")
    brief.record(root, "interests", {"keywords": keywords, "domain": domain, "admired_paper": admired})

    proposed = topics.propose(root)
    while not proposed:
        keywords = io.ask("Too little to propose topics: give at least one keyword (Enter to stop): ")
        if not keywords:
            return {"brief": brief.load(root), "handoff": None}, [STOPPED], 0
        brief.record(root, "interests", {"keywords": keywords})
        proposed = topics.propose(root)
    io.say("5/6 Topics:")
    for line in _topic_lines(proposed, []):
        io.say(line)
    while True:
        pick = io.ask("Pick a topic by number, or combine several (e.g. 1,3): ")
        try:
            topics.choose(root, pick, None)
        except brief.IdeaError as exc:
            io.say(exc.message)
            continue
        note = io.ask("The angle you want, in a few words (Enter to skip): ") or None
        if note:
            topics.choose(root, pick, note)
        break

    result = draft.compose(root)
    while True:
        io.say("6/6 Draft:")
        io.say(result["text"])
        io.say(_gate_line(result["gate"]))
        if result["gate"]["ok"]:
            answer = "y" if args.yes else io.ask("Approve it and hand it to /plausibility? [y]es, [e]dit, "
                                                 "[n]o: ").lower()
        else:
            answer = io.ask("The prompt gate refuses it: [e]dit, or [n]o to stop here: ").lower()
        if answer.startswith("y") and result["gate"]["ok"]:
            return _finish(root, True)
        if answer.startswith("e"):
            text = io.ask("Your draft (at least two sentences: the problem, then what you propose): ")
            if text:
                result = draft.store(root, text)
            continue
        if answer.startswith("n"):
            return _finish(root, False)


def run_start(root: Path, args: argparse.Namespace, ask: Callable[[str], str] | None = None
              ) -> tuple[dict, list[str], int]:
    if args.answers:
        return start_from_answers(root, args)
    stream = sys.stderr if args.json else sys.stdout

    def say(text: str) -> None:
        stream.write(text + "\n")
        stream.flush()

    def default_ask(prompt: str) -> str:
        stream.write(prompt)
        stream.flush()
        line = sys.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\n")

    io = _Asker(ask or default_ask, say)
    try:
        return _interactive(root, args, io)
    except EOFError:
        say("")
        return {"brief": brief.load(root), "handoff": None, "stopped": True}, [STOPPED], 0
    except KeyboardInterrupt:
        say("")
        return {"brief": brief.load(root), "handoff": None, "stopped": True}, [STOPPED], 130


HANDLERS: dict[str, Callable[[Path, argparse.Namespace], tuple[dict, list[str]]]] = {
    "show": run_show, "bank": run_bank, "profile": run_profile, "experience": run_experience,
    "interests": run_interests, "topics": run_topics, "draft": run_draft, "approve": run_approve,
    "handoff": run_handoff,
}


def main(argv: list[str] | None = None, prog: str = "idea_cli.py", *,
         ask: Callable[[str], str] | None = None) -> int:
    """Run one verb; returns the exit code (never raises SystemExit)."""
    parser = build_parser(prog)
    try:
        args = parser.parse_args(normalize(list(sys.argv[1:] if argv is None else argv)))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.verb is None:
        parser.print_help()
        return 2
    try:
        root = _root(args)
        if args.verb == "start":
            payload, lines, code = run_start(root, args, ask)
        else:
            (payload, lines), code = HANDLERS[args.verb](root, args), 0
    except (Refusal, brief.IdeaError) as exc:
        if args.json:
            sys.stdout.write(json.dumps({"ok": False, "error": exc.code, "message": exc.message},
                                        ensure_ascii=False) + "\n")
        else:
            sys.stderr.write(f"{prog}: error: {exc.code}: {exc.message}\n")
        return 2 if exc.code == "USAGE" else 1
    if args.json:
        sys.stdout.write(json.dumps({"ok": True, **payload}, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write("\n".join(lines) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
