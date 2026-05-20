"""Voice (WebRTC) plane subpackage. Platform-agnostic.

``session.py`` and ``signaling.py`` currently import the Hermes bridge by
its concrete path (``..platforms.hermes.bridge``). Phase 2 of feature 011
introduces the ``AgentPlatform`` interface in
``satellite_core.platforms.base`` and rewires these modules to depend on
that abstraction instead — at which point the constitution-IV neutrality
gate (``tests/unit/test_no_platform_branching.py``) goes green.
"""
