"""Agent-platform plugins (constitution v2.0.0 Principle IV).

Each subpackage here ships one ``AgentPlatform`` implementation. The
satellite core selects one at startup via ``~/.satellite/config.yaml``
``platform:`` and does not import the others. The base ``AgentPlatform``
Protocol arrives in Phase 2 of feature 011 at :mod:`.base`.
"""
