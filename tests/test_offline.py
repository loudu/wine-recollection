"""Tests that run without an API key: the HTTP layer is replaced by canned responses."""

import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.degrade import DAMAGES, degrade  # noqa: E402
from wine_id.matching import matches_expected, normalize, same_name  # noqa: E402
from wine_id.pipeline import IdentificationError, WineIdentifier  # noqa: E402

CLUES = {
    "text_fragments": [{"text": "…ILLAC", "legibility": "partial", "location": "bas"}],
    "vintage": {"reading": "19?5", "candidates": ["1995", "1985"]},
    "visual_elements": ["blason avec lion"],
    "bottle": {"shape": "bordelaise", "glass_color": "vert foncé", "capsule": None, "cork": None},
    "legal_mentions": [],
    "likely_country": "France",
    "likely_region": "Bordeaux",
    "damage_description": "tache d'humidité sur la moitié gauche",
    "photo_advice": ["Photographier le bouchon"],
}
IDENTIFICATION = {
    "candidates": [{
        "producer": "Château Lynch-Bages", "wine_name": None, "appellation": "Pauillac",
        "region": "Bordeaux", "country": "France", "vintage": "1995", "color": "rouge",
        "confidence": 60, "supporting_evidence": ["…ILLAC"], "contradicting_evidence": [],
        "sources": ["https://example.com"],
    }],
    "follow_up_questions": [],
    "summary": "Pauillac probable.",
}


def message(payload: dict | None, stop_reason: str = "end_turn") -> dict:
    content = [{"type": "text", "text": json.dumps(payload)}] if payload is not None else []
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 200, "server_tool_use": {"web_search_requests": 1}},
    }


def fake_client(responses: list[dict], seen: list[dict]) -> anthropic.Anthropic:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append({"body": json.loads(request.content), "headers": dict(request.headers)})
        return httpx2.Response(200, json=queue.pop(0))

    return anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    path = tmp_path / "label.png"
    Image.new("RGB", (3000, 2000), (240, 230, 200)).save(path)
    return path


def test_pipeline_two_steps(photo):
    seen: list[dict] = []
    client = fake_client([message(CLUES), message(IDENTIFICATION)], seen)
    result = WineIdentifier(client=client).identify([photo], user_notes="cave de mon grand-père")

    assert result.clues.vintage.candidates == ["1995", "1985"]
    assert result.identification.candidates[0].producer == "Château Lynch-Bages"
    assert result.usage.input_tokens == 2000 and result.usage.web_searches == 2
    assert result.usage.cost_usd("claude-opus-5-5") == pytest.approx(2000 * 4e-6 + 400 * 20e-6 + 2 * 0.01)

    extract, identify = seen[0]["body"], seen[1]["body"]
    assert extract["model"] == "claude-opus-5-5"
    assert extract["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen[0]["headers"]["anthropic-beta"]
    assert extract["output_config"]["format"]["type"] == "json_schema"
    assert "tools" not in extract
    assert identify["tools"][0]["type"] == "web_search_20260209"
    # Clues from step 1 are handed to step 2, images are resized.
    assert "…ILLAC" in identify["messages"][0]["content"][-1]["text"]
    image = next(b for b in extract["messages"][0]["content"] if b["type"] == "image")
    assert image["source"]["media_type"] == "image/jpeg"


def test_pause_turn_is_resumed(photo):
    seen: list[dict] = []
    client = fake_client([message(CLUES), message(None, "pause_turn"), message(IDENTIFICATION)], seen)
    result = WineIdentifier(client=client).identify([photo])
    assert result.identification.candidates
    assert [m["role"] for m in seen[2]["body"]["messages"]] == ["user", "assistant"]


def test_refusal_raises(photo):
    client = fake_client([message(None, "refusal")], [])
    with pytest.raises(IdentificationError):
        WineIdentifier(client=client).identify([photo])


def test_no_web_option(photo):
    seen: list[dict] = []
    client = fake_client([message(CLUES), message(IDENTIFICATION)], seen)
    WineIdentifier(client=client, web_search=False).identify([photo])
    assert "tools" not in seen[1]["body"]


@pytest.mark.parametrize("a,b", [
    ("Château Lynch-Bages", "lynch bages"),
    ("Domaine Leflaive", "Leflaive"),
    ("Château d'Yquem", "Chateau d’Yquem"),
    ("Château Cos d'Estournel", "Cos d Estournel"),
])
def test_same_name(a, b):
    assert same_name(a, b)


def test_different_names():
    assert not same_name("Château Margaux", "Château Palmer")
    assert not same_name("Château Latour", "")
    assert normalize("Château de la Tour") == "tour"


def test_matches_expected_pools_producer_and_cuvee():
    cand = SimpleNamespace(producer="Domaine Leflaive – Puligny-Montrachet", wine_name=None)
    assert matches_expected(cand, {"producer": "Domaine Leflaive", "wine_name": "Puligny-Montrachet"})
    assert not matches_expected(cand, {"producer": "Domaine Leflaive", "wine_name": "Chevalier-Montrachet"})


def test_degrade_all_damages():
    img = Image.new("RGB", (400, 300), (240, 230, 200))
    rng = random.Random(1)
    for damage in DAMAGES.values():
        out = damage(img, rng)
        assert out.size == img.size and out.mode == "RGB"
    out, names = degrade(img, rng, 3)
    assert len(names) == 3 and out.tobytes() != img.tobytes()
