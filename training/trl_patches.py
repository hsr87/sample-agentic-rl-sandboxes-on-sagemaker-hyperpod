"""Workaround for TRL 1.14.1: GRPO tool calling + vLLM server mode + more than one training process.

Problem (checked against TRL 1.14.1 and main at 7379929, 2026-09-30):
  * VLLMGeneration.generate (server mode) gathers prompts from all ranks, generates on rank 0, broadcasts, then
    slices the result as `process_index * len(prompts)`, which assumes every rank sent the same number of prompts.
  * In GRPOTrainer._tool_call_loop each rank only regenerates for its own samples that made a tool call, so the
    counts differ across ranks. The slices are wrong (IndexError), and a rank whose samples all finish leaves the
    loop while the others still call the collective gather, which deadlocks.

Fix (same for both sandboxes, no change to what is generated):
  * slice by per-rank offsets computed from the gathered prompt counts
  * after a rank finishes its own tool loop it keeps joining the collective with an empty request until a round in
    which every rank is idle, so all ranks run the same number of collectives
  * each generation round is timed into the sandbox timing log (op="generate"), so the per-step breakdown does not
    depend on TRL's own logging

Text-only prompts are assumed (the task suite has no images).
"""

import time
from itertools import accumulate

from accelerate.utils import broadcast_object_list, gather_object

_APPLIED = False


def _server_generate(gen, prompts, num_generations, profiler, active):
    """One collective generation round. Returns None on every rank when no rank had work."""
    acc = gen.accelerator
    gathered = gather_object([(active, prompts)])
    if not any(a for a, _ in gathered):
        return None
    counts = [len(p) for _, p in gathered]
    all_prompts = [p for _, ps in gathered for p in ps]

    t0 = time.perf_counter()
    payload = None
    if acc.is_main_process and all_prompts:
        sampling_params = {
            "n": num_generations,
            "repetition_penalty": gen.repetition_penalty,
            "temperature": gen.temperature,
            "top_p": gen.top_p,
            "top_k": gen.top_k,
            "min_p": 0.0 if gen.min_p is None else gen.min_p,
            "max_tokens": gen.max_completion_length,
            "logprobs": gen.logprobs,
            "structured_outputs_regex": gen.structured_outputs_regex,
            "generation_kwargs": gen.generation_kwargs,
        }
        with profiler:
            out = gen.vllm_client.generate(prompts=all_prompts[::num_generations], features=None, **sampling_params)
        payload = (out["prompt_ids"], out["completion_ids"], out["logprobs"], out.get("logprob_token_ids"))
    obj = [payload]
    broadcast_object_list(obj, from_process=0)
    # Every rank waits for the same round, so each rank logs it (its own critical path).
    from training.harness import log_event

    log_event(op="generate", dur=time.perf_counter() - t0, n_prompts=len(prompts), n_total=len(all_prompts),
              active=active)
    if obj[0] is None:
        return [], [], [], None
    all_prompt_ids, all_completion_ids, all_logprobs, all_logprob_token_ids = obj[0]
    all_prompt_ids = [ids for ids in all_prompt_ids for _ in range(num_generations)]

    start = ([0] + list(accumulate(counts)))[acc.process_index]
    sl = slice(start, start + len(prompts))
    return (
        all_prompt_ids[sl],
        all_completion_ids[sl],
        all_logprobs[sl] if all_logprobs is not None else None,
        all_logprob_token_ids[sl] if all_logprob_token_ids is not None else None,
    )


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from contextlib import nullcontext

    from trl.generation.vllm_generation import VLLMGeneration
    from trl.trainer.grpo_trainer import GRPOTrainer

    orig_generate = VLLMGeneration.generate
    orig_loop = GRPOTrainer._tool_call_loop

    def generate(self, prompts, images, num_generations, profiler=None):
        if self.mode != "server" or self.accelerator.num_processes == 1:
            return orig_generate(self, prompts, images, num_generations, profiler=profiler)
        if images is not None and any(img for img in images):
            raise NotImplementedError("trl_patches supports text-only prompts")
        return _server_generate(self, prompts, num_generations, profiler or nullcontext(), active=True)

    def _tool_call_loop(self, *args, **kwargs):
        result = orig_loop(self, *args, **kwargs)
        gen = getattr(self, "vllm_generation", None)
        if gen is not None and gen.mode == "server" and self.accelerator.num_processes > 1:
            while _server_generate(gen, [], 1, nullcontext(), active=False) is not None:
                pass
        return result

    VLLMGeneration.generate = generate
    GRPOTrainer._tool_call_loop = _tool_call_loop
    _APPLIED = True
