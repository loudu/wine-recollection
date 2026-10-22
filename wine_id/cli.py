import argparse
import json
import sys

import anthropic

from .pipeline import DEFAULT_MODEL, IdentificationError, Result, WineIdentifier


def format_result(result: Result) -> str:
    clues, ident = result.clues, result.identification
    lines = ["== Indices relevés =="]
    for frag in clues.text_fragments:
        lines.append(f"  [{frag.legibility}] {frag.text}  ({frag.location})")
    if clues.vintage.reading:
        lines.append(f"  Millésime lu: {clues.vintage.reading} -> {', '.join(clues.vintage.candidates) or '?'}")
    if clues.visual_elements:
        lines.append(f"  Visuel: {'; '.join(clues.visual_elements)}")
    if clues.bottle.shape:
        lines.append(f"  Bouteille: {clues.bottle.shape}")

    lines.append("\n== Candidats ==")
    for i, c in enumerate(ident.candidates, start=1):
        name = c.producer + (f" – {c.wine_name}" if c.wine_name else "")
        where = ", ".join(x for x in (c.appellation, c.region, c.country) if x)
        lines.append(f"{i}. {name} {c.vintage or ''} [{c.confidence} %]")
        if where:
            lines.append(f"   {where} · {c.color}")
        for ev in c.supporting_evidence:
            lines.append(f"   + {ev}")
        for ev in c.contradicting_evidence:
            lines.append(f"   - {ev}")
        for src in c.sources[:3]:
            lines.append(f"   ↗ {src}")

    lines.append(f"\n{ident.summary}")
    if ident.follow_up_questions or clues.photo_advice:
        lines.append("\n== Pour affiner ==")
        lines.extend(f"  • {q}" for q in [*ident.follow_up_questions, *clues.photo_advice])

    cost = result.usage.cost_usd(result.model)
    lines.append(
        f"\n({result.model} · {result.usage.input_tokens} tokens entrée, "
        f"{result.usage.output_tokens} sortie, {result.usage.web_searches} recherches"
        + (f" · ~{cost:.3f} $)" if cost is not None else ")")
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wine_id", description="Identifier une bouteille de vin à partir de photos d'étiquette abîmée.")
    parser.add_argument("photos", nargs="+", help="Photos: étiquette, contre-étiquette, bouchon, capsule…")
    parser.add_argument("--notes", help="Ce que vous savez déjà (ex: 'acheté à Bordeaux dans les années 90').")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--no-web", action="store_true", help="Désactiver la vérification par recherche web.")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute.")
    args = parser.parse_args(argv)

    identifier = WineIdentifier(model=args.model, effort=args.effort, web_search=not args.no_web)
    try:
        result = identifier.identify(args.photos, user_notes=args.notes)
    except (IdentificationError, anthropic.APIError) as e:
        print(f"Erreur: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "clues": result.clues.model_dump(),
            "identification": result.identification.model_dump(),
            "usage": vars(result.usage),
        }, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))
    return 0
