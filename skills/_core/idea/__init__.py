"""Idea shaping: the optional guided phase before ``/plausibility`` (lane 2a).

A user with a vague idea answers a few key questions, one step at a time:

1. sources: the managed ``banco-lia`` bank, another bank MCP server of the
   workspace's ``.mcp.json``, or none (``bank.py``);
2. profile: ORCID, OpenAlex author or a Google Scholar link used only to find
   the author in OpenAlex (``profile.py``);
3. experience and 4. interests (``brief.record``);
5. three candidate topics with their evidence, picked or combined
   (``topics.py``);
6. a draft of at least two sentences checked by the prompt gate, approved and
   handed off as ``/plausibility <draft>`` (``draft.py``).

Everything is recorded in ``.papersmith/idea_brief.json`` (``brief.py``).
``idea_cli.py`` is the terminal front end (``smith idea``); the dashboard's
Idea tab calls the same functions. Standard library only, so the workspace's
bare Python, the dashboard and ``smith`` all run it.
"""
