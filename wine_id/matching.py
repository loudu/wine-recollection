"""Fuzzy comparison of wine names, tolerant to accents, articles and generic words."""

import re
import unicodedata
from difflib import SequenceMatcher

GENERIC_WORDS = {
    "chateau", "domaine", "dom", "clos", "maison", "cave", "caves", "cellier", "mas",
    "tenuta", "bodega", "bodegas", "weingut", "estate", "winery", "vineyards",
    "le", "la", "les", "de", "du", "des", "d", "l", "et", "the",
}


def normalize(name: str | None) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    return " ".join(w for w in words if w not in GENERIC_WORDS)


def same_name(a: str | None, b: str | None, threshold: float = 0.85) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def matches_expected(candidate, expected: dict) -> bool:
    """A candidate is right when the producer matches and, if a cuvée is expected, the cuvée too.

    Producer and cuvée are often swapped or merged by the model
    ("Domaine Leflaive – Puligny-Montrachet"), so both fields are pooled.
    """
    found = " ".join(x for x in (candidate.producer, candidate.wine_name) if x)
    if not same_name(expected["producer"], found):
        return False
    if expected.get("wine_name"):
        return same_name(expected["wine_name"], found)
    return True
