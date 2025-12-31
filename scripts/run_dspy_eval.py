from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path

import dspy

from dnd_summary.config import settings


class ExtractNPCs(dspy.Signature):
    transcript = dspy.InputField(desc="Full transcript text with speaker labels.")
    npcs = dspy.OutputField(desc="JSON array of NPC names mentioned.")


class ExtractLocations(dspy.Signature):
    transcript = dspy.InputField(desc="Full transcript text with speaker labels.")
    locations = dspy.OutputField(desc="JSON array of location names mentioned.")


class ExtractItems(dspy.Signature):
    transcript = dspy.InputField(desc="Full transcript text with speaker labels.")
    items = dspy.OutputField(desc="JSON array of item names mentioned.")


class ExtractFactions(dspy.Signature):
    transcript = dspy.InputField(desc="Full transcript text with speaker labels.")
    factions = dspy.OutputField(desc="JSON array of faction or organization names mentioned.")


def _normalize(name: str) -> str:
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"[^a-zA-Z0-9\\s]+", " ", name)
    return re.sub(r"\s+", " ", name.strip().lower())


def _load_dataset(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _read_transcript(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _score(predicted: list[str], gold: list[str]) -> dict:
    pred_list = [_normalize(p) for p in predicted if p.strip()]
    gold_list = [_normalize(g) for g in gold if g.strip()]
    if not pred_list and not gold_list:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred_list or not gold_list:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    matched_gold = set()
    matched_pred = set()
    for pi, pred in enumerate(pred_list):
        for gi, gold_name in enumerate(gold_list):
            if gi in matched_gold:
                continue
            if pred == gold_name or pred in gold_name or gold_name in pred:
                matched_pred.add(pi)
                matched_gold.add(gi)
                break

    tp = len(matched_pred)
    precision = tp / len(pred_list)
    recall = tp / len(gold_list)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DSPy NPC extraction eval.")
    parser.add_argument("--dataset", required=True, help="Path to JSONL eval set.")
    parser.add_argument("--output-dir", default="artifacts/evals", help="Output directory.")
    parser.add_argument("--model", default=settings.gemini_model, help="Model name.")
    parser.add_argument(
        "--task",
        default="npc",
        choices=["npc", "location", "item", "faction"],
        help="Which entity type to evaluate.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of rows.")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    rows = _load_dataset(dataset_path)
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("Dataset is empty.")

    model = args.model
    if "/" not in model:
        model = f"gemini/{model}"
    lm = dspy.LM(model=model, api_key=settings.gemini_api_key)
    dspy.settings.configure(lm=lm)
    signature_map = {
        "npc": (ExtractNPCs, "npcs", "gold_npcs"),
        "location": (ExtractLocations, "locations", "gold_locations"),
        "item": (ExtractItems, "items", "gold_items"),
        "faction": (ExtractFactions, "factions", "gold_factions"),
    }
    signature, output_key, gold_key = signature_map[args.task]
    predictor = dspy.Predict(signature)

    run_id = uuid.uuid4().hex
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for row in rows:
        transcript_path = Path(row["transcript_path"])
        transcript_text = _read_transcript(transcript_path)
        gold = row.get(gold_key, [])

        prediction = predictor(transcript=transcript_text)
        parse_error = False
        try:
            predicted = json.loads(getattr(prediction, output_key))
        except (json.JSONDecodeError, TypeError):
            predicted = []
            parse_error = True
        scores = _score(predicted, gold)
        results.append(
            {
                "transcript_path": str(transcript_path),
                "task": args.task,
                "gold": gold,
                "predicted": predicted,
                "scores": scores,
                "parse_error": parse_error,
            }
        )

    summary = {
        "run_id": run_id,
        "model": args.model,
        "task": args.task,
        "dataset": str(dataset_path),
        "count": len(results),
        "avg_precision": sum(r["scores"]["precision"] for r in results) / len(results),
        "avg_recall": sum(r["scores"]["recall"] for r in results) / len(results),
        "avg_f1": sum(r["scores"]["f1"] for r in results) / len(results),
        "parse_errors": sum(1 for r in results if r["parse_error"]),
        "parse_error_rate": sum(1 for r in results if r["parse_error"]) / len(results),
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
