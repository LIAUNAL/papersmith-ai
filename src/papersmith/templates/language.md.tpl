## Language

Reply to the human in the language they write in (Spanish or English).
Everything else stays English regardless of the conversation language: skills,
agent definitions, delegations and messages between agents, tool inputs, and
every generated artifact (code, comments, docs, commit messages, the data files
the dashboard displays under `.papersmith/` and `sota-pool/`, and paper
internals unless the paper declares another language). The dashboard's language
selector translates its own labels, never a workspace file, so a file written in
Spanish shows Spanish under English; only the conversation with an agent
follows the human's language.
