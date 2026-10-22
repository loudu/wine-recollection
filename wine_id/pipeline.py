"""Two-step identification: observe the label, then hypothesise and verify."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .images import image_blocks
from .prompts import EXTRACT_SYSTEM, IDENTIFY_SYSTEM
from .schemas import Clues, Identification

DEFAULT_MODEL = os.environ.get("WINE_ID_MODEL", "claude-opus-5-5")

# On a safety-classifier decline, the API re-runs the request on Anthropic's
# recommended fallback model instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}
MAX_PAUSE_RESUMES = 4

# USD per million tokens (input, output).
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
}
WEB_SEARCH_PRICE = 10.00 / 1000


class IdentificationError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0

    def add(self, usage) -> None:
        self.input_tokens += usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
        self.output_tokens += usage.output_tokens
        if usage.server_tool_use is not None:
            self.web_searches += usage.server_tool_use.web_search_requests or 0

    def cost_usd(self, model: str) -> float | None:
        if model not in PRICES:
            return None
        price_in, price_out = PRICES[model]
        return (
            self.input_tokens * price_in / 1e6
            + self.output_tokens * price_out / 1e6
            + self.web_searches * WEB_SEARCH_PRICE
        )


@dataclass
class Result:
    clues: Clues
    identification: Identification
    model: str
    usage: Usage = field(default_factory=Usage)


class WineIdentifier:
    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "high", web_search: bool = True, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.web_search = web_search

    def identify(self, photos: list[str | Path], user_notes: str | None = None) -> Result:
        usage = Usage()
        images = image_blocks(photos)
        clues = self.extract_clues(images, user_notes, usage)
        identification = self.propose_candidates(images, clues, user_notes, usage)
        return Result(clues=clues, identification=identification, model=self.model, usage=usage)

    def extract_clues(self, images: list[dict], user_notes: str | None, usage: Usage) -> Clues:
        text = "Relève tous les indices visibles sur cette bouteille."
        if user_notes:
            text += f"\nInformations données par l'utilisateur: {user_notes}"
        return self._parse(
            system=EXTRACT_SYSTEM,
            content=[*images, {"type": "text", "text": text}],
            output_format=Clues,
            tools=None,
            usage=usage,
        )

    def propose_candidates(self, images: list[dict], clues: Clues, user_notes: str | None, usage: Usage) -> Identification:
        text = (
            "Indices relevés à l'étape d'observation:\n"
            f"{clues.model_dump_json(indent=2)}\n\n"
            "Propose et vérifie les vins possibles."
        )
        if user_notes:
            text += f"\nInformations données par l'utilisateur: {user_notes}"
        return self._parse(
            system=IDENTIFY_SYSTEM,
            content=[*images, {"type": "text", "text": text}],
            output_format=Identification,
            tools=[WEB_SEARCH_TOOL] if self.web_search else None,
            usage=usage,
        )

    def _parse(self, *, system: str, content: list[dict], output_format, tools, usage: Usage):
        messages = [{"role": "user", "content": content}]
        kwargs = {"tools": tools} if tools else {}
        for _ in range(MAX_PAUSE_RESUMES + 1):
            try:
                response = self.client.beta.messages.parse(
                    model=self.model,
                    max_tokens=16000,
                    system=system,
                    messages=messages,
                    output_format=output_format,
                    output_config={"effort": self.effort},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                    **kwargs,
                )
            except TypeError as e:
                # The SDK only reports missing credentials when the first request is built.
                if "authentication" in str(e):
                    raise IdentificationError("Aucune clé API trouvée. Définissez ANTHROPIC_API_KEY (voir README).") from e
                raise
            usage.add(response.usage)
            if response.stop_reason == "pause_turn":
                # Long server-tool turn: send it back so the model resumes where it stopped.
                messages = [messages[0], {"role": "assistant", "content": response.content}]
                continue
            break
        else:
            raise IdentificationError("La recherche web n'a pas abouti (trop de reprises).")

        if response.stop_reason == "refusal":
            raise IdentificationError("Le modèle a refusé la requête.")
        if response.stop_reason == "max_tokens":
            raise IdentificationError("Réponse tronquée (max_tokens atteint).")
        if response.parsed_output is None:
            raise IdentificationError(f"Réponse non structurée (stop_reason={response.stop_reason}).")
        return response.parsed_output
