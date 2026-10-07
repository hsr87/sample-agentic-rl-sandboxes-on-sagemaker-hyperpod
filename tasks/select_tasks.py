"""Select the task suite from AdithyaSK/data_agent_rl_environment_train.

Selection rules (see docs/02-tasks-and-images.md):
  * gold answer is a plain number, so the grader's exact/numeric tiers decide the reward
    (no LLM judge, no free-text leniency)
  * package_tier == 1 (only packages that are baked into the base image)
  * Kaggle data for the task is small (<= MAX_DATASET_BYTES), so it can be baked into one shared image
  * empirical solve fraction from the difficulty sweep (Qwen3.5-4B/2B, 8 rollouts) in [solve_lo, solve_hi].
    The first selection (0.25 to 0.625) measured 57% held-out solve rate for google/gemma-4-E4B-it, above the
    10 to 50% target, so the default range is 0.125 to 0.25 (see docs/02-tasks-and-images.md).
  * at most --max-per-dataset tasks per Kaggle dataset; held-out tasks use datasets disjoint from training tasks

Writes tasks/suite.json. Deterministic for a given seed and dataset revision.
"""

import argparse
import json
import random
import re
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download, list_bucket_tree

TRAIN_REPO = "AdithyaSK/data_agent_rl_environment_train"
RANKED_REPO = "AdithyaSK/data_agent_rl_environment_train_difficulty_ranked"
# Dataset revisions used to build this suite (pinned for reproducibility).
TRAIN_REVISION = "4073bb9b817aba164d8697cbe504a646522cd07a"
RANKED_REVISION = "5923562863a29724c026021a2d16cb8e44e376d9"
BUCKET = "AdithyaSK/jupyter-agent-kaggle-all"

NUMERIC_GOLD = re.compile(r"^[-+]?\d[\d,]*(\.\d+)?%?$")
MAX_DATASET_BYTES = 20_000_000


def bucket_prefix(kaggle_name: str) -> str:
    return kaggle_name.replace("/", "__")


def dataset_bytes(kaggle_name: str) -> int:
    items = list_bucket_tree(BUCKET, prefix=bucket_prefix(kaggle_name) + "/", recursive=True)
    return sum(getattr(it, "size", 0) or 0 for it in items if getattr(it, "type", None) == "file")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=40)
    ap.add_argument("--heldout", type=int, default=16)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--solve-lo", type=float, default=0.125)
    ap.add_argument("--solve-hi", type=float, default=0.25)
    ap.add_argument("--max-per-dataset", type=int, default=3)
    ap.add_argument("--heldout-dataset-frac", type=float, default=0.35)
    ap.add_argument("--out", default=str(Path(__file__).parent / "suite.json"))
    args = ap.parse_args()

    manifest = pd.read_parquet(hf_hub_download(TRAIN_REPO, "manifest.parquet", repo_type="dataset", revision=TRAIN_REVISION))
    registry = json.load(open(hf_hub_download(RANKED_REPO, "registry.json", repo_type="dataset", revision=RANKED_REVISION)))
    registry = registry[0] if isinstance(registry, list) else registry
    ranked = pd.DataFrame(registry["tasks"])[["name", "solve_frac", "mean_tool_calls"]]
    ranked["task_dir"] = ranked["name"].str.split("/").str[-1]

    df = manifest.merge(ranked[["task_dir", "solve_frac", "mean_tool_calls"]], on="task_dir")
    df = df[
        (df.verdict == "verified")
        & (df.package_tier == 1)
        & df.answer.str.strip().str.match(NUMERIC_GOLD)
        & df.solve_frac.between(args.solve_lo, args.solve_hi)
    ]

    # Measure data size only for candidate datasets (one bucket listing per dataset).
    sizes = {k: dataset_bytes(k) for k in sorted(df.kaggle_dataset_name.unique())}
    df = df.assign(dataset_bytes=df.kaggle_dataset_name.map(sizes))
    df = df[(df.dataset_bytes > 0) & (df.dataset_bytes <= MAX_DATASET_BYTES)]

    rng = random.Random(args.seed)
    datasets = sorted(df.kaggle_dataset_name.unique())
    rng.shuffle(datasets)
    n_held = max(1, round(len(datasets) * args.heldout_dataset_frac))

    def pick(names, n):
        """Round-robin over datasets, up to max_per_dataset tasks each, until n tasks."""
        pools = {k: df[df.kaggle_dataset_name == k].sort_values("task_dir").to_dict("records") for k in names}
        for pool in pools.values():
            rng.shuffle(pool)
        rows = []
        for rnd in range(args.max_per_dataset):
            for k in names:
                if len(rows) < n and rnd < len(pools[k]):
                    rows.append(pools[k][rnd])
        if len(rows) < n:
            raise SystemExit(f"only {len(rows)} tasks available, need {n}")
        return rows

    heldout_rows = pick(datasets[:n_held], args.heldout)
    train_rows = pick(datasets[n_held:], args.train)

    cols = ["task_dir", "kaggle_dataset_name", "answer", "question", "solve_frac", "mean_tool_calls",
            "dataset_bytes", "reward_mode_initial"]
    to_rec = lambda r: {c: (r[c].item() if hasattr(r[c], "item") else r[c]) for c in cols}
    suite = {
        "source": {"train_repo": TRAIN_REPO, "train_revision": TRAIN_REVISION, "ranked_repo": RANKED_REPO,
                   "ranked_revision": RANKED_REVISION, "bucket": BUCKET},
        "rules": {"solve_frac": [args.solve_lo, args.solve_hi], "max_dataset_bytes": MAX_DATASET_BYTES,
                  "gold": "numeric", "package_tier": 1, "max_per_dataset": args.max_per_dataset, "seed": args.seed},
        "train": [to_rec(r) for r in train_rows],
        "heldout": [to_rec(r) for r in heldout_rows],
    }
    Path(args.out).write_text(json.dumps(suite, indent=2, ensure_ascii=False) + "\n")
    total = sum({r["kaggle_dataset_name"]: r["dataset_bytes"] for r in suite["train"] + suite["heldout"]}.values())
    print(f"eligible datasets={len(datasets)} train={len(suite['train'])} heldout={len(suite['heldout'])} "
          f"data={total / 1e6:.1f} MB -> {args.out}")


if __name__ == "__main__":
    main()
