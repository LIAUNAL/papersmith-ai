"""papersmith — CLI workspace orchestrator for the papersmith-ai framework.

The CLI keeps framework internals (skills, agents, generators, harnesses) and
decoupled paper research workspaces (proposals, synthesized codebases,
notebooks, references, remote execution drops) strictly separated: a workspace
copies framework files at ``init`` and re-syncs them at ``upgrade``, while
every research artifact is protected by the preservation contract.
"""

__version__ = "0.24.0"
