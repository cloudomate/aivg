"""Management plane subpackage (design Appendix A).

``ManagementService`` and ``build_management_app`` live in :mod:`.service`
for now; feature 011 Phase 2/3 will split out ``app.py`` (route wiring),
``adopt.py``, ``command.py``, ``ota.py``, and ``log_sse.py`` as new
operator endpoints land.
"""

from .service import ManagementService, build_management_app

__all__ = ["ManagementService", "build_management_app"]
