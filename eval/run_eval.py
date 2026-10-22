"""Measure identification accuracy on a set of photos with known answers.

    python eval/run_eval.py                       # eval/dataset/answers.csv
    python eval/run_eval.py --limit 5 --no-web    # quick, cheaper run

answers.csv columns: photos (several separated by ';'), producer, wine_name,
appellation, vintage, notes. Photo paths are relative to eval/dataset/photos.
Each run writes a JSON report to eval/results/ so runs can be compared.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wine_id.matching import matches_expected  # noqa: E402
from wine_id.pipeline import DEFAULT_MODEL, IdentificationError, WineIdentifier  # noqa: E402

DATASET = ROOT / "eval" / "dataset"
RESULTS = ROOT / "eval" / "results"


def load_cases(csv_path: Path, photo_dir: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cases = []
    for row in rows:
        photos = [photo_dir / p.strip() for p in row["photos"].split(";") if p.strip()]
        missing = [str(p) for p in photos if not p.exists()]
        if missing:
            print(f"! ignoré, photo introuvable: {', '.join(missing)}", file=sys.stderr)
            continue
        cases.append({**row, "photos": photos})
    return cases


def score_case(case: dict, candidates) -> dict:
    rank = next((i for i, c in enumerate(candidates, start=1) if matches_expected(c, case)), None)
    vintage_ok = None
    if case.get("vintage"):
        vintage_ok = bool(candidates) and (candidates[0].vintage or "").strip() == case["vintage"].strip()
    return {"rank": rank, "top1": rank == 1, "top3": rank is not None and rank <= 3, "vintage_top1": vintage_ok}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", type=Path, default=DATASET / "answers.csv")
    parser.add_argument("--photos", type=Path, default=DATASET / "photos")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high")
    parser.add_argument("--no-web", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--label", default="", help="Nom court pour ce run (ex: 'prompt-v2').")
    args = parser.parse_args()

    if not args.answers.exists():
        print(f"Fichier {args.answers} absent. Copiez eval/dataset/answers.example.csv et remplissez-le.", file=sys.stderr)
        return 1
    cases = load_cases(args.answers, args.photos)[: args.limit]
    if not cases:
        print("Aucun cas exploitable.", file=sys.stderr)
        return 1

    identifier = WineIdentifier(model=args.model, effort=args.effort, web_search=not args.no_web)
    records, total_cost = [], 0.0
    for i, case in enumerate(cases, start=1):
        expected = " ".join(x for x in (case["producer"], case.get("wine_name"), case.get("vintage")) if x)
        print(f"[{i}/{len(cases)}] {expected} … ", end="", flush=True)
        started = time.monotonic()
        try:
            result = identifier.identify(case["photos"])
        except (IdentificationError, anthropic.APIError) as e:
            print(f"ERREUR ({e})")
            records.append({"expected": expected, "error": str(e)})
            continue
        candidates = result.identification.candidates
        score = score_case(case, candidates)
        cost = result.usage.cost_usd(result.model) or 0.0
        total_cost += cost
        top = candidates[0] if candidates else None
        print(("✓" if score["top1"] else "≈" if score["top3"] else "✗")
              + (f"  → {top.producer} {top.wine_name or ''} {top.vintage or ''} [{top.confidence}%]" if top else ""))
        records.append({
            "expected": expected,
            "photos": [str(p.relative_to(args.photos)) for p in case["photos"]],
            **score,
            "seconds": round(time.monotonic() - started, 1),
            "cost_usd": round(cost, 4),
            "clues": result.clues.model_dump(),
            "identification": result.identification.model_dump(),
        })

    scored = [r for r in records if "error" not in r]
    n = len(records)
    with_vintage = [r for r in scored if r["vintage_top1"] is not None]
    summary = {
        "cases": n,
        "errors": n - len(scored),
        "top1": sum(r["top1"] for r in scored) / n,
        "top3": sum(r["top3"] for r in scored) / n,
        "vintage_top1": (sum(r["vintage_top1"] for r in with_vintage) / len(with_vintage)) if with_vintage else None,
        "cost_usd": round(total_cost, 3),
    }
    print("\n== Résultat ==")
    print(f"Top-1 : {summary['top1']:.0%}   Top-3 : {summary['top3']:.0%}   ({n} cas, {summary['errors']} erreurs)")
    if summary["vintage_top1"] is not None:
        print(f"Millésime exact (candidat n°1) : {summary['vintage_top1']:.0%}")
    print(f"Coût estimé : {summary['cost_usd']:.2f} $")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}{'-' + args.label if args.label else ''}.json"
    out.write_text(json.dumps({
        "settings": {"model": args.model, "effort": args.effort, "web_search": not args.no_web, "label": args.label},
        "summary": summary,
        "cases": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rapport : {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
