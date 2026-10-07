"""Generate the Harbor task directories and stage the Kaggle data for the shared base image.

Input:  tasks/suite.json (from select_tasks.py)
Output: tasks/train/<task>/ and tasks/heldout/<task>/ (Harbor task format)
        tasks/image/data/<owner>__<dataset>/ (baked into the base image, not in git)

Changes from the upstream task (same for both sandboxes):
  * environment/Dockerfile uses the shared base image instead of savatar101/env-data-agent-train:base
  * the healthcheck links the pre-staged data into /home/user/input instead of downloading it
    from the Hugging Face bucket at sandbox start (removes network noise and HF rate limits)
  * resources set explicitly to 2 vCPU / 4096 MB (E2B template); AgentCore is fixed at 2 vCPU / 8 GB
  * verifier: no LLM judge (OPENAI_API_KEY removed) and no `pip install openai` at verify time
  * solution/solve.sh added (oracle writes the gold answer), since upstream tasks have none
"""

import json
import shlex
import shutil
import tomllib
from pathlib import Path

import tomli_w
from huggingface_hub import download_bucket_files, list_bucket_tree, snapshot_download

HERE = Path(__file__).parent
DATA_DIR = HERE / "image" / "data"

DOCKERFILE = """\
# Shared base image built by tasks/image (see docs/02-tasks-and-images.md).
ARG BASE_IMAGE=harbor-rl-tasks-base:latest
FROM ${BASE_IMAGE}
WORKDIR /workdir
"""

TEST_SH = """\
#!/usr/bin/env bash
set -u
mkdir -p /logs/verifier

answer_path="/workdir/answer.txt"
if [ ! -s "$answer_path" ]; then
  echo "0.0" > /logs/verifier/reward.txt
  echo "[grader] no answer at $answer_path" >&2
  exit 0
fi

python3 /tests/grader.py < "$answer_path" > /logs/verifier/reward.txt
"""

GRADER_LINE_OLD = "The grader does exact match → numeric tolerance → LLM judge against the gold answer."
GRADER_LINE_NEW = "The grader does exact match, then numeric tolerance, against the gold answer."


def bucket_prefix(kaggle_name: str) -> str:
    return kaggle_name.replace("/", "__")


def stage_data(bucket: str, kaggle_name: str) -> None:
    prefix = bucket_prefix(kaggle_name)
    dest = DATA_DIR / prefix
    if dest.is_dir() and any(dest.iterdir()):
        return
    dest.mkdir(parents=True, exist_ok=True)
    # Flatten like upstream pull_bucket.py: every file lands directly in the input folder.
    targets = [
        (it.path, str(dest / Path(it.path).name))
        for it in list_bucket_tree(bucket, prefix=prefix + "/", recursive=True)
        if getattr(it, "type", None) == "file"
    ]
    download_bucket_files(bucket, files=targets)


def build_task(src: Path, dst: Path, rec: dict, split: str) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "environment").mkdir(parents=True)
    (dst / "tests").mkdir()
    (dst / "solution").mkdir()

    instruction = (src / "instruction.md").read_text()
    (dst / "instruction.md").write_text(instruction.replace(GRADER_LINE_OLD, GRADER_LINE_NEW))

    cfg = tomllib.loads((src / "task.toml").read_text())
    prefix = bucket_prefix(rec["kaggle_dataset_name"])
    cfg["task"]["name"] = f"harbor-rl-suite/{rec['task_dir']}"
    cfg["metadata"].update({"suite_split": split, "sweep_solve_frac": rec["solve_frac"],
                            "data_prefix": prefix})
    env = cfg["environment"]
    env.update({"cpus": 2, "memory_mb": 4096})
    # The data is baked into the image, so tasks need no network. Model-generated code runs with egress blocked.
    env.pop("allow_internet", None)
    env["network_mode"] = "no-network"
    env["healthcheck"] = {
        "command": f"rm -rf /home/user/input && ln -s /data/{prefix} /home/user/input && [ -n \"$(ls /home/user/input/)\" ]",
        "interval_sec": 1.0, "timeout_sec": 30.0, "start_period_sec": 0.0, "start_interval_sec": 1.0, "retries": 3,
    }
    env["env"] = {"KAGGLE_DATASET_NAME": rec["kaggle_dataset_name"]}
    cfg["verifier"]["env"].pop("OPENAI_API_KEY", None)
    (dst / "task.toml").write_text(tomli_w.dumps(cfg))

    (dst / "environment" / "Dockerfile").write_text(DOCKERFILE)
    (dst / "tests" / "test.sh").write_text(TEST_SH)
    shutil.copy(src / "tests" / "grader.py", dst / "tests" / "grader.py")
    solve = f"#!/usr/bin/env bash\nset -eu\nmkdir -p /workdir\nprintf '%s' {shlex.quote(rec['answer'])} > /workdir/answer.txt\n"
    (dst / "solution" / "solve.sh").write_text(solve)
    for p in [dst / "tests" / "test.sh", dst / "solution" / "solve.sh"]:
        p.chmod(0o755)


def main() -> None:
    suite = json.loads((HERE / "suite.json").read_text())
    recs = [("train", r) for r in suite["train"]] + [("heldout", r) for r in suite["heldout"]]
    src_root = Path(snapshot_download(
        suite["source"]["train_repo"], repo_type="dataset",
        revision=suite["source"].get("train_revision", "4073bb9b817aba164d8697cbe504a646522cd07a"),
        allow_patterns=[f"tasks/{r['task_dir']}/**" for _, r in recs],
    )) / "tasks"

    for split, rec in recs:
        build_task(src_root / rec["task_dir"], HERE / split / rec["task_dir"], rec, split)
        stage_data(suite["source"]["bucket"], rec["kaggle_dataset_name"])

    size = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
    print(f"tasks: train={len(suite['train'])} heldout={len(suite['heldout'])}; staged data {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
