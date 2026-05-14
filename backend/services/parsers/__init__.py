"""NXT1 — AI response parsers.

Public re-exports from this package:
    - `AIProviderError`         — raised by `parse_ai_response` on total failure.
    - `parse_ai_response(text)` — 5-level JSON parsing pipeline with progressive
      recovery (strict → control-char normalize → json_repair → regex salvage
      → code-fence salvage).

The pipeline implementation lives in `json_pipeline.py`.

Historical context
==================
This module used to live inline in `services/ai_service.py`. As the
recovery levels grew, the file became hard to navigate. Splitting the parser
out keeps `ai_service.py` focused on provider routing + streaming, and lets
us test the parsers in isolation without touching real LLM clients.

Backwards compatibility
=======================
`services.ai_service` still re-exports the same names, so existing imports
keep working unchanged.
"""
from .json_pipeline import (
    AIProviderError,
    parse_ai_response,
    # Internal helpers (exposed for tests / power-users only):
    strip_markdown_fences,
    extract_json_block,
    escape_control_chars_in_strings,
    salvage_files_array,
    salvage_files_from_fences,
    strip_outer_fence,
)

__all__ = [
    "AIProviderError",
    "parse_ai_response",
    "strip_markdown_fences",
    "extract_json_block",
    "escape_control_chars_in_strings",
    "salvage_files_array",
    "salvage_files_from_fences",
    "strip_outer_fence",
]
