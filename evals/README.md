# DSPy evals

This folder holds evaluation datasets and outputs for prompt optimization.

## Dataset format (JSONL)
Each line contains:
```
{
  "transcript_path": "transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/transcript.txt",
  "gold_npcs": ["Baba Yaga", "Captain Levi"],
  "gold_locations": ["Moonhaven", "Phylantra"],
  "gold_items": ["Bone Key", "Lantern of the Dark Flame"],
  "gold_factions": ["Stonewall Legionnaire"]
}
```

## Build a dataset from legacy analysis docs
If you have legacy analysis outputs under `legacy/summaries/**/raw_txt/`, you can
generate a rough gold set:
```
uv run python scripts/build_eval_from_analysis.py
```

## Run NPC extraction eval
Install eval deps:
- `uv pip install -e ".[eval]"`

Run:
```
uv run python scripts/run_dspy_eval.py --dataset evals/npc_eval_template.jsonl --task npc --limit 3
```

Results land under `artifacts/evals/<run_id>/`.
