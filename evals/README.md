# DSPy evals

This folder holds evaluation datasets and outputs for prompt optimization.

## Dataset format (JSONL)
Each line contains:
```
{
  "transcript_path": "transcripts/campaigns/<campaign_slug>/sessions/<session_slug>/transcript.txt",
  "gold_npcs": ["Baba Yaga", "Captain Levi"]
}
```

## Run NPC extraction eval
Install eval deps:
- `uv pip install -e ".[eval]"`

Run:
```
uv run python scripts/run_dspy_eval.py --dataset evals/npc_eval_template.jsonl
```

Results land under `artifacts/evals/<run_id>/`.
