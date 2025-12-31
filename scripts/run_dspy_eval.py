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


def _normalize(name: str) -> str:
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
    pred_set = {_normalize(p) for p in predicted if p.strip()}
    gold_set = {_normalize(g) for g in gold if g.strip()}
    if not pred_set and not gold_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred_set or not gold_set:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set)
    recall = tp / len(gold_set)
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
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    rows = _load_dataset(dataset_path)
    if not rows:
        raise SystemExit("Dataset is empty.")

    lm = dspy.LM(model=args.model, api_key=settings.gemini_api_key)
    dspy.settings.configure(lm=lm)
    predictor = dspy.Predict(ExtractNPCs)

    run_id = uuid.uuid4().hex
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for row in rows:
        transcript_path = Path(row["transcript_path"])
        transcript_text = _read_transcript(transcript_path)
        gold = row.get("gold_npcs", [])

        prediction = predictor(transcript=transcript_text)
        try:
            predicted = json.loads(prediction.npcs)
        except json.JSONDecodeError:
            predicted = []
        scores = _score(predicted, gold)
        results.append(
            {
                "transcript_path": str(transcript_path),
                "gold_npcs": gold,
                "predicted_npcs": predicted,
                "scores": scores,
            }
        )

    summary = {
        "run_id": run_id,
        "model": args.model,
        "dataset": str(dataset_path),
        "count": len(results),
        "avg_precision": sum(r["scores"]["precision"] for r in results) / len(results),
        "avg_recall": sum(r["scores"]["recall"] for r in results) / len(results),
        "avg_f1": sum(r["scores"]["f1"] for r in results) / len(results),
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
