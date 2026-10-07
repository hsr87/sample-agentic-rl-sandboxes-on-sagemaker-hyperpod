"""GRPO training on the Harbor task suite with a switchable rollout sandbox.

    accelerate launch --config_file training/zero3.yaml --num_processes 6 training/train_grpo.py --sandbox e2b
    accelerate launch --config_file training/zero3.yaml --num_processes 6 training/train_grpo.py --sandbox agentcore

Everything except the sandbox is identical between the two runs. The policy model is served by a separate
vLLM server (training/run.sh starts it); TRL captures tokens and logprobs on the trainer side, and the sandbox
only executes commands and the verifier (external agent pattern).

Outputs under --output-dir:
  steps.jsonl       per-step wall time (every rank) and TRL's logged metrics (rank 0)
  eval_before.json / eval_after.json   held-out solve rate (eval reward mean) at step 0 and at max_steps
  sandbox/*.jsonl   per-call sandbox timings and failures from training/harness.py
"""

import argparse
import json
import os
import time
from pathlib import Path

from transformers import TrainerCallback
from trl import GRPOConfig, GRPOTrainer
from trl.experimental.harbor import HarborSpec

from training import trl_patches

trl_patches.apply()  # multi-process tool calling in vLLM server mode (see training/trl_patches.py)

SANDBOXES = {
    "e2b": "e2b",  # Harbor's built-in E2B environment
    "agentcore": "harbor_agentcore.environment:AgentCoreEnvironment",
}
HARNESS = "training.harness:TimedBashEnv"
# Unused audio/vision towers (text-only tasks) and the per-layer embedding (PLE) parameters stay frozen
# to fit full fine-tuning of the text decoder on A100 40GB. Same for both sandboxes.
FROZEN_SUBSTRINGS = ("audio", "vision", "per_layer")


class StepLogger(TrainerCallback):
    def __init__(self, path: Path):
        self.path = path
        self.t0 = None

    def _write(self, rec):
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def on_step_begin(self, args, state, control, **kwargs):
        os.environ["TRAIN_STEP"] = str(state.global_step + 1)  # read by the sandbox timing log
        self.t0 = time.time()

    def on_step_end(self, args, state, control, **kwargs):
        self._write({"kind": "step", "rank": int(os.environ.get("RANK", 0)), "step": state.global_step,
                     "t_begin": self.t0, "t_end": time.time()})
        if state.global_step >= state.max_steps:
            os.environ["TRAIN_STEP"] = "eval_after"  # the final evaluation runs right after the last step

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        # eval_on_start runs at global_step 0 ("before"); the last one runs at max_steps ("after").
        if state.is_world_process_zero and metrics:
            tag = "before" if state.global_step == 0 else "after"
            rec = {"tag": tag, "step": state.global_step, "time": time.time(), **metrics}
            (self.path.parent / f"eval_{tag}.json").write_text(json.dumps(rec, indent=2))

    def on_log(self, args, state, control, logs=None, **kwargs):
        if state.is_world_process_zero and logs:
            self._write({"kind": "log", "step": state.global_step, "time": time.time(), **logs})


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sandbox", choices=sorted(SANDBOXES), required=True)
    p.add_argument("--model", default="google/gemma-4-E4B-it")
    p.add_argument("--train-tasks", default="tasks/train")
    p.add_argument("--eval-tasks", default="tasks/heldout")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-steps", type=int, default=40)
    # Gemma 4 has a 262k vocabulary, so full logits for several long sequences do not fit on A100 40GB.
    # 1 per device x 8 accumulation steps x 6 ranks = 48 rollouts (6 prompts x 8 generations) per step.
    p.add_argument("--per-device-train-batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation-steps", type=int, default=8)
    p.add_argument("--per-device-eval-batch-size", type=int, default=2)
    p.add_argument("--num-generations", type=int, default=8)
    p.add_argument("--num-generations-eval", type=int, default=6)
    # Multi-turn completion budget (model tokens + tool outputs). 4096 clipped about half of the rollouts.
    p.add_argument("--max-completion-length", type=int, default=8192)
    p.add_argument("--max-tool-calling-iterations", type=int, default=20)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--learning-rate", type=float, default=2e-6)
    p.add_argument("--vllm-server-base-url", default="http://localhost:8000")
    p.add_argument("--skip-eval", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    out = Path(args.output_dir or f"/results/grpo-{args.sandbox}")
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SANDBOX_TIMING_DIR", str(out / "sandbox"))
    env_type = SANDBOXES[args.sandbox]

    train_spec = HarborSpec(args.train_tasks, agent=HARNESS, environment_type=env_type)
    eval_spec = HarborSpec(args.eval_tasks, agent=HARNESS, environment_type=env_type)

    config = GRPOConfig(
        output_dir=str(out / "trainer"),
        seed=args.seed,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        num_generations=args.num_generations,
        num_generations_eval=args.num_generations_eval,
        max_completion_length=args.max_completion_length,
        max_tool_calling_iterations=args.max_tool_calling_iterations,
        temperature=args.temperature,
        beta=0.0,
        bf16=True,
        gradient_checkpointing=True,
        model_init_kwargs={"dtype": "bfloat16", "attn_implementation": "sdpa"},
        use_vllm=True,
        vllm_mode="server",
        vllm_server_base_url=args.vllm_server_base_url,
        vllm_server_timeout=900,
        logging_steps=1,
        save_strategy="no",
        # Held-out solve rate before and after training, inside the training loop (calling evaluate() before
        # train() with DeepSpeed ZeRO-3 leaves the engine in inference mode and breaks backward).
        eval_strategy="no" if args.skip_eval else "steps",
        eval_steps=args.max_steps,
        eval_on_start=not args.skip_eval,
        report_to="none",
    )
    trainer = GRPOTrainer(
        model=args.model,
        args=config,
        train_dataset=train_spec.train_dataset,
        eval_dataset=eval_spec.train_dataset,
        environment_factory=train_spec.environment_factory,
        reward_funcs=train_spec.reward_funcs,
        callbacks=[StepLogger(out / "steps.jsonl")],
    )
    frozen = 0
    for name, param in trainer.model.named_parameters():
        if any(k in name for k in FROZEN_SUBSTRINGS):
            param.requires_grad = False
            frozen += 1
    # ZeRO-3 partitions parameters, so numel() is 0 on each rank; ds_numel holds the full size.
    size = lambda p: getattr(p, "ds_numel", p.numel())
    trainable = sum(size(p) for p in trainer.model.parameters() if p.requires_grad)
    total = sum(size(p) for p in trainer.model.parameters())
    if trainer.accelerator.is_main_process:
        print(f"[train_grpo] sandbox={args.sandbox} env_type={env_type} frozen_tensors={frozen} "
              f"trainable_params={trainable} total_params={total}")

    if not args.skip_eval:
        os.environ["TRAIN_STEP"] = "eval_before"  # sandbox events of the start-of-run evaluation
    trainer.train()


if __name__ == "__main__":
    main()
