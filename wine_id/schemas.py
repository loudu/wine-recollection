"""Structured outputs exchanged with the model.

Every field is required (nullable when unknown) so the JSON schema stays
strict: the model must say explicitly "I don't know" instead of omitting.
"""

from typing import Literal

from pydantic import BaseModel, Field


class TextFragment(BaseModel):
    text: str = Field(description="Texte exactement tel qu'il apparaît; '?' pour chaque lettre illisible, ex: '…ILLAC', 'Gr?nd Cru'.")
    legibility: Literal["clear", "partial", "guessed"]
    location: str = Field(description="Où sur l'étiquette: haut, centre, bas, contre-étiquette, bouchon, capsule…")


class VintageClue(BaseModel):
    reading: str | None = Field(description="Millésime tel que lu, ex: '19?5'. null si absent.")
    candidates: list[str] = Field(description="Années compatibles avec la lecture, de la plus à la moins probable.")


class BottleClue(BaseModel):
    shape: str | None = Field(description="bordelaise, bourguignonne, flûte, champenoise, autre… null si non visible.")
    glass_color: str | None
    capsule: str | None = Field(description="Couleur, matière, inscriptions de la capsule.")
    cork: str | None = Field(description="Inscriptions sur le bouchon si photographié.")


class Clues(BaseModel):
    """Step 1: what is observed. No identification here."""

    text_fragments: list[TextFragment]
    vintage: VintageClue
    visual_elements: list[str] = Field(description="Blason, illustration, couleurs, typographie, bordures, médailles…")
    bottle: BottleClue
    legal_mentions: list[str] = Field(description="Mentions légales lisibles: degré, volume, 'mis en bouteille au…', sulfites…")
    likely_country: str | None
    likely_region: str | None
    damage_description: str = Field(description="Nature et étendue des dégâts de l'étiquette.")
    photo_advice: list[str] = Field(description="Photos supplémentaires qui aideraient le plus (bouchon, capsule, contre-étiquette, autre angle…).")


class Candidate(BaseModel):
    producer: str = Field(description="Domaine / château / maison.")
    wine_name: str | None = Field(description="Cuvée ou nom du vin s'il diffère du producteur.")
    appellation: str | None
    region: str | None
    country: str | None
    vintage: str | None
    color: Literal["rouge", "blanc", "rosé", "effervescent", "liquoreux", "inconnu"]
    confidence: int = Field(description="Probabilité estimée (0-100) que ce soit la bonne bouteille. La somme sur tous les candidats ne dépasse pas 100.")
    supporting_evidence: list[str] = Field(description="Indices observés qui concordent avec ce candidat.")
    contradicting_evidence: list[str] = Field(description="Indices observés qui ne concordent pas ou restent inexpliqués.")
    sources: list[str] = Field(description="URLs consultées qui confirment l'existence de ce vin / l'aspect de son étiquette.")


class Identification(BaseModel):
    """Step 2: ranked hypotheses, checked against the web."""

    candidates: list[Candidate] = Field(description="1 à 5 candidats, du plus probable au moins probable.")
    follow_up_questions: list[str] = Field(description="Questions à poser à l'utilisateur pour départager les candidats.")
    summary: str = Field(description="Explication courte du raisonnement, en français.")
