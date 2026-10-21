"""Entity-name normalization mirrored from Person A's pipeline.

``pipeline/extract.py`` owns the canonical implementation. This module is a
small, tested backend copy so ``graphdb`` does not import spaCy-dependent
pipeline modules. If the canonical function moves into ``common/``, this copy
should be replaced with the shared one.
"""

from __future__ import annotations

import re

_LEADING_THE = re.compile(r"^the\s+", flags=re.IGNORECASE)
_POSSESSIVE = re.compile(r"['’]s$")


def normalize_entity_name(name: str) -> str:
    """Apply the same normalization Person A uses for entity names.

    The function is case-preserving. It collapses whitespace, strips a leading
    case-insensitive ``"the"``, and strips a trailing possessive.
    """

    result = " ".join(name.split())
    result = _LEADING_THE.sub("", result)
    result = _POSSESSIVE.sub("", result)
    return result
