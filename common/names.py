"""Entity-name normalisation shared by the pipeline (writing names) and graphdb (looking them up)."""

import re

# Zero-width and other invisible format characters that news HTML leaves inside names
# ("Saudi⁠Arabia"), plus soft hyphens; no-break spaces become ordinary spaces.
_INVISIBLE = re.compile("[­​-‏‪-‮⁠-⁤﻿]")
_LEADING_THE = re.compile(r"^the\s+", flags=re.IGNORECASE)
_POSSESSIVE = re.compile(r"['’]s$")


def normalize_name(name: str) -> str:
    """Case-preserving: strips invisible characters, collapses whitespace, a leading "the" and a trailing possessive.

    "The Federal Reserve" and "Federal Reserve" must become the same graph node.
    """

    name = _INVISIBLE.sub("", (name or "").replace(" ", " "))
    name = " ".join(name.split())
    name = _LEADING_THE.sub("", name)
    return _POSSESSIVE.sub("", name)
