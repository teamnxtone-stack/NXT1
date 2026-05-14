"""NXT1 route modules (Phase 8 refactor).

This package will progressively absorb routes currently living in `server.py`.
Each module exposes a `router` (APIRouter, prefix=/api) that `server.py` registers.

Migration order (P0 backlog):
  1. agents (DONE — agents.py)
  2. autofix (DONE — autofix.py)
  3. product (DONE — product.py)
  4. requests / saved-requests
  5. databases
  6. imports / analysis
  7. env-vars
  8. domains
  9. deployments
 10. runtime
 11. ai / chat
 12. files
 13. projects (last; touches everything)
"""
