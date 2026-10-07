"""Turn raw results into the summary tables and charts cited by docs/05-comparison.md.

Inputs (results/ as synced from s3://<bucket>/results/):
  oracle/oracle_<sandbox>_*.csv                       task validity
  bench/bench_<sandbox>_*.csv, *_throughput.csv       sandbox micro-benchmark
  grpo-<sandbox>/steps.jsonl, sandbox/*.jsonl, eval_before.json, eval_after.json   training runs
  usage/agentcore_usage.json (optional)               CloudWatch vended CPU/memory usage of the runtime

Outputs: results/summary/*.csv (incl. training_sandbox_ops.csv, training_sandbox_sessions.csv) and results/charts/*.png

    python bench/analyze.py --results results
"""

import argparse
import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SANDBOXES = ["e2b", "agentcore"]
COLORS = {"e2b": "#E8710A", "agentcore": "#1A73E8"}
LABELS = {"e2b": "E2B sandbox", "agentcore": "AgentCore Runtime"}


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def oracle_summary(res: Path, out: Path):
    rows = []
    for sb in SANDBOXES:
        f = latest(str(res / "oracle" / f"oracle_{sb}_*.csv"))
        if not f:
            continue
        df = pd.read_csv(f)
        rows.append({"sandbox": sb, "tasks": len(df), "passed": int(df.passed.sum()),
                     "failed_tasks": ";".join(df[df.passed == 0].task), "median_wall_sec": df.wall_sec.median(),
                     "source": Path(f).name})
    if rows:
        pd.DataFrame(rows).to_csv(out / "oracle.csv", index=False)
    return rows


def bench_summary(res: Path, out: Path, charts: Path):
    lat, thr = [], []
    for sb in SANDBOXES:
        f = latest(str(res / "bench" / f"bench_{sb}_*[0-9].csv"))
        if not f:
            continue
        df = pd.read_csv(f)
        lat_df = df[df.test == "latency"]
        for op, g in lat_df.groupby("op"):
            ok = g[g.ok == 1].dur_sec
            lat.append({"sandbox": sb, "op": op, "n": len(g), "errors": int((g.ok == 0).sum()),
                        "p50_ms": ok.quantile(0.5) * 1000, "p95_ms": ok.quantile(0.95) * 1000,
                        "mean_ms": ok.mean() * 1000})
        conc = df[df.test == "concurrency"]
        for c, g in conc.groupby("concurrency"):
            starts = g[g.op == "start"]
            execs = g[g.op == "exec_true"]
            thr.append({"sandbox": sb, "concurrency": c,
                        "start_p50_ms": starts[starts.ok == 1].dur_sec.quantile(0.5) * 1000,
                        "start_p95_ms": starts[starts.ok == 1].dur_sec.quantile(0.95) * 1000,
                        "exec_p50_ms": execs[execs.ok == 1].dur_sec.quantile(0.5) * 1000,
                        "exec_p95_ms": execs[execs.ok == 1].dur_sec.quantile(0.95) * 1000,
                        "calls": len(g), "errors": int((g.ok == 0).sum()), "throttled": int(g.throttled.sum()),
                        "error_rate": float((g.ok == 0).mean()),
                        "sample_errors": " | ".join(g[g.ok == 0].err.dropna().astype(str).unique()[:3])})
        tf = f.replace(".csv", "_throughput.csv")
        if Path(tf).exists():
            t = pd.read_csv(tf)
            for r in thr:
                if r["sandbox"] == sb:
                    m = t[t.concurrency == r["concurrency"]]
                    if len(m):
                        r.update(m.iloc[0][["sessions_ok", "sessions_failed", "wall_sec", "sessions_per_sec",
                                            "execs_per_sec"]].to_dict())
    if lat:
        lat_df = pd.DataFrame(lat)
        lat_df.to_csv(out / "bench_latency.csv", index=False)
        ops = ["start", "py_import_first", "py_import_again", "exec_true", "upload_1MB", "download_1MB", "upload_8MB",
               "download_8MB", "stop"]
        fig, ax = plt.subplots(figsize=(9, 4))
        w = 0.38
        for i, sb in enumerate(SANDBOXES):
            d = lat_df[lat_df.sandbox == sb].set_index("op").reindex(ops)
            xs = [j + (i - 0.5) * w for j in range(len(ops))]
            ax.bar(xs, d.p50_ms, w, color=COLORS[sb], label=f"{LABELS[sb]} p50")
            ax.errorbar(xs, d.p50_ms, yerr=[[0] * len(ops), (d.p95_ms - d.p50_ms).fillna(0)], fmt="none",
                        ecolor="#333", capsize=3)
        ax.set_xticks(range(len(ops)), ops, rotation=20)
        ax.set_yscale("log")
        ax.set_ylabel("latency (ms, log), bar p50, whisker p95")
        ax.set_title("Sandbox operation latency (sequential sessions)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(charts / "bench_latency.png", dpi=150)
        plt.close(fig)
    if thr:
        thr_df = pd.DataFrame(thr)
        thr_df.to_csv(out / "bench_concurrency.csv", index=False)
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        for sb in SANDBOXES:
            d = thr_df[thr_df.sandbox == sb].sort_values("concurrency")
            if "sessions_per_sec" in d:
                axes[0].plot(d.concurrency, d.sessions_per_sec, "o-", color=COLORS[sb], label=LABELS[sb])
            axes[1].plot(d.concurrency, d.error_rate * 100, "o-", color=COLORS[sb], label=LABELS[sb])
        axes[0].set_title("Session throughput (start + 10 exec + stop)")
        axes[0].set_xlabel("concurrent sessions")
        axes[0].set_ylabel("sessions / s")
        axes[1].set_title("Error rate")
        axes[1].set_xlabel("concurrent sessions")
        axes[1].set_ylabel("% of calls")
        for a in axes:
            a.set_xscale("log", base=2)
            a.legend()
        fig.tight_layout()
        fig.savefig(charts / "bench_concurrency.png", dpi=150)
        plt.close(fig)


def load_events(run_dir: Path):
    ev = []
    for f in (run_dir / "sandbox").glob("*.jsonl"):
        rank = f.stem.split("_rank")[-1].split("_")[0]
        for line in open(f):
            r = json.loads(line)
            r["rank"] = int(rank)
            ev.append(r)
    return pd.DataFrame(ev)


def training_summary(res: Path, out: Path, charts: Path):
    per_step_all, runs = [], []
    for sb in SANDBOXES:
        run_dir = next(iter(sorted(res.glob(f"grpo-{sb}*"))), None)
        if run_dir is None:
            continue
        steps = [json.loads(line) for line in open(run_dir / "steps.jsonl")]
        step_wall = {r["step"]: r["t_end"] - r["t_begin"] for r in steps if r["kind"] == "step" and r["rank"] == 0}
        logs = {r["step"]: r for r in steps if r["kind"] == "log" and "reward" in r and "eval_reward" not in r}
        ev = load_events(run_dir)
        ev = ev[ev.step.astype(str).str.isdigit()].copy()
        ev["step"] = ev.step.astype(int)
        rows = []
        for step, g in ev.groupby("step"):
            # Sequential within a rank: the rank's time in each category is the sum of its calls.
            per_rank = g.groupby(["rank", "op"]).dur.sum().unstack(fill_value=0.0)
            mean = per_rank.mean()
            fails = g[g.op == "rollout_failed"]
            rows.append({
                "sandbox": sb, "step": step, "step_wall_sec": step_wall.get(step),
                "generation_sec": mean.get("generate", 0.0),
                "sandbox_provision_sec": mean.get("provision", 0.0),
                "sandbox_exec_sec": mean.get("exec", 0.0),
                "sandbox_verify_sec": mean.get("verify", 0.0),
                "sandbox_stop_sec": mean.get("stop", 0.0),
                "rollouts": int((g.op == "reward").sum() + len(fails)),
                "mean_reward": logs.get(step, {}).get("reward"),
                "failed_rollouts": len(fails),
                "failure_causes": ";".join(sorted(set(fails.err.dropna().astype(str).str[:80]))),
                "exec_calls": int((g.op == "exec").sum()),
                "exec_timeouts": int(((g.op == "exec") & (g.get("rc", pd.Series(dtype=float)) == -1)).sum()),
            })
        df = pd.DataFrame(rows).sort_values("step")
        sandbox_cols = ["sandbox_provision_sec", "sandbox_exec_sec", "sandbox_verify_sec", "sandbox_stop_sec"]
        df["sandbox_wait_sec"] = df[sandbox_cols].sum(axis=1)
        df["train_and_other_sec"] = df.step_wall_sec - df.generation_sec - df.sandbox_wait_sec
        per_step_all.append(df)
        ev_b = run_dir / "eval_before.json"
        ev_a = run_dir / "eval_after.json"
        eb = json.loads(ev_b.read_text()) if ev_b.exists() else {}
        ea = json.loads(ev_a.read_text()) if ev_a.exists() else {}
        runs.append({"sandbox": sb, "run": run_dir.name, "steps": len(df),
                     "total_train_wall_sec": df.step_wall_sec.sum(),
                     "mean_step_sec": df.step_wall_sec.mean(), "mean_generation_sec": df.generation_sec.mean(),
                     "mean_sandbox_wait_sec": df.sandbox_wait_sec.mean(),
                     "mean_sandbox_provision_sec": df.sandbox_provision_sec.mean(),
                     "sandbox_share_of_step": (df.sandbox_wait_sec / df.step_wall_sec).mean(),
                     "rollouts": int(df.rollouts.sum()), "failed_rollouts": int(df.failed_rollouts.sum()),
                     "heldout_before": eb.get("eval_reward"), "heldout_after": ea.get("eval_reward"),
                     "first5_reward": df.mean_reward.head(5).mean(), "last5_reward": df.mean_reward.tail(5).mean()})
    if not per_step_all:
        return
    steps_df = pd.concat(per_step_all)
    steps_df.to_csv(out / "training_steps.csv", index=False)
    pd.DataFrame(runs).to_csv(out / "training_runs.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for sb in SANDBOXES:
        d = steps_df[steps_df.sandbox == sb]
        if len(d):
            axes[0].plot(d.step, d.mean_reward, "-", color=COLORS[sb], label=LABELS[sb])
    axes[0].set_title("Mean training reward per step")
    axes[0].set_xlabel("step")
    axes[0].legend()
    parts = ["generation_sec", "sandbox_provision_sec", "sandbox_exec_sec", "sandbox_verify_sec",
             "train_and_other_sec"]
    means = steps_df.groupby("sandbox")[parts].mean().reindex([s for s in SANDBOXES if s in set(steps_df.sandbox)])
    bottom = [0.0] * len(means)
    palette = ["#9AA0A6", "#F9AB00", "#34A853", "#A142F4", "#5F6368"]
    for p, col in zip(parts, palette):
        axes[1].bar([LABELS[s] for s in means.index], means[p], bottom=bottom, color=col, label=p.replace("_sec", ""))
        bottom = [b + v for b, v in zip(bottom, means[p])]
    axes[1].set_title("Mean step time breakdown (per rank, seconds)")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(charts / "training.png", dpi=150)
    plt.close(fig)


def sandbox_usage_summary(res: Path, out: Path):
    """Per-op latency inside training runs and total sandbox session time (input to the cost model).

    Event `ts` is the end time of a call, so a session lives from (create.ts - create.dur) to stop.ts.
    Covers the whole run including the start and end evaluations, matching the AgentCore usage window.
    """
    ops, sessions = [], []
    for sb in SANDBOXES:
        run_dir = next(iter(sorted(res.glob(f"grpo-{sb}*"))), None)
        if run_dir is None:
            continue
        ev = load_events(run_dir)
        for op, g in ev.groupby("op"):
            ops.append({"sandbox": sb, "op": op, "n": len(g), "errors": int((~g.ok.astype(bool)).sum()),
                        "p50_ms": g.dur.quantile(0.5) * 1e3, "p95_ms": g.dur.quantile(0.95) * 1e3,
                        "mean_ms": g.dur.mean() * 1e3})
        life = ev[ev.op.isin(["create", "stop"])].copy()
        life["t0"] = life.ts - life.dur
        span = life.groupby("rollout").agg(t_start=("t0", "min"), t_end=("ts", "max"), n=("op", "size"))
        span = span[span.n >= 2]  # create and stop both recorded
        sec = (span.t_end - span.t_start)
        sessions.append({"sandbox": sb, "run": run_dir.name, "sessions": len(span),
                         "session_hours": sec.sum() / 3600, "mean_session_sec": sec.mean(),
                         "p50_session_sec": sec.median(),
                         "run_wall_hours": (span.t_end.max() - span.t_start.min()) / 3600})
    if ops:
        pd.DataFrame(ops).to_csv(out / "training_sandbox_ops.csv", index=False)
        pd.DataFrame(sessions).to_csv(out / "training_sandbox_sessions.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    args = ap.parse_args()
    res = Path(args.results)
    out, charts = res / "summary", res / "charts"
    out.mkdir(parents=True, exist_ok=True)
    charts.mkdir(parents=True, exist_ok=True)
    oracle_summary(res, out)
    bench_summary(res, out, charts)
    training_summary(res, out, charts)
    sandbox_usage_summary(res, out)
    print("wrote", sorted(p.name for p in out.iterdir()), sorted(p.name for p in charts.iterdir()))


if __name__ == "__main__":
    main()
