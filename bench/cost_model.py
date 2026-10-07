"""Cost estimates for docs/05-comparison.md, computed from measured usage and documented prices.

Inputs (all under results/):
  summary/training_sandbox_sessions.csv  measured sandbox session-hours and run wall time (bench/analyze.py)
  usage/agentcore_grpo_window.json       AgentCore vended usage for the AgentCore training run (CloudWatch)
  usage/e2b_client_cpu.json              CPU utilization of the self-hosted E2B client node during the E2B run

Outputs:
  summary/cost.csv          one row per line item, with the formula used
  charts/break_even.png     AgentCore vs E2B Cloud cost per sandbox-hour as a function of CPU utilization

Prices are on-demand list prices for us-west-2 checked on 2026-10-01 (sources in docs/references.md).

    python bench/cost_model.py --results results
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# AgentCore Runtime V2 consumption pricing [documented]
AC_VCPU_H = 0.1276
AC_GB_H = 0.0169
AC_VCPU, AC_MEM_GB = 2, 8  # fixed session size
# Interface endpoints in 2 AZs [documented price]: ecr.api, ecr.dkr, logs (VPC mode without internet) and
# bedrock-agentcore (private data-plane path from the trainer)
AC_ENDPOINTS_H = 4 * 2 * 0.01
# E2B Cloud pricing [documented], billed on allocated resources while the sandbox runs
E2B_VCPU_S = 0.000014
E2B_GIB_S = 0.0000045
E2B_VCPU, E2B_MEM_GIB = 2, 4  # D11
# Self-hosted E2B (sample-e2b-on-aws, this deployment), EC2 on-demand [documented] per hour
SELF_HOSTED = {
    "client c8i.metal-48xl x1": 8.99616,
    "nomad server t3.xlarge x3": 3 * 0.1664,
    "api t3.xlarge x2": 2 * 0.1664,
    "build m8i.4xlarge x1": 0.84672,
    "bastion c7i.xlarge x1": 0.1785,
    "nat gateway x1": 0.045,
    "alb (hourly part)": 0.0225,
    "aurora serverless v2 (0.5 ACU floor)": 0.5 * 0.12,
    "elasticache serverless redis (1 GB floor)": 0.125,
}
# HyperPod ml.p4d.24xlarge on-demand [documented]
GPU_H = 25.91


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    res = Path(ap.parse_args().results)
    out, charts = res / "summary", res / "charts"
    sess = pd.read_csv(out / "training_sandbox_sessions.csv").set_index("sandbox")
    usage = json.loads((res / "usage" / "agentcore_grpo_window.json").read_text())["usage"]
    e2b_cpu = json.loads((res / "usage" / "e2b_client_cpu.json").read_text())

    rows = []

    def add(item, sandbox, value, formula, tag):
        rows.append({"item": item, "sandbox": sandbox, "value": round(value, 4), "formula": formula, "tag": tag})

    ac, e2 = sess.loc["agentcore"], sess.loc["e2b"]
    rollouts = {"agentcore": ac.sessions, "e2b": e2.sessions}

    # AgentCore: measured usage x documented price
    ac_cpu_cost = usage["CPUUsed-vCPUHours"] * AC_VCPU_H
    ac_mem_cost = usage["MemoryUsed-GBHours"] * AC_GB_H
    ac_endpoint_cost = AC_ENDPOINTS_H * ac.run_wall_hours
    ac_cost = ac_cpu_cost + ac_mem_cost + ac_endpoint_cost
    add("sandbox cost per run (USD)", "agentcore", ac_cost,
        f"{usage['CPUUsed-vCPUHours']:.3f} vCPU-h x {AC_VCPU_H} + {usage['MemoryUsed-GBHours']:.2f} GB-h x {AC_GB_H}"
        f" + VPC endpoints {AC_ENDPOINTS_H:.2f} $/h x {ac.run_wall_hours:.2f} h", "estimated")
    add("sandbox cost per 1,000 rollouts (USD)", "agentcore", ac_cost / ac.sessions * 1000,
        "run cost / sessions x 1000", "estimated")
    ac_util = usage["CPUUsed-vCPUHours"] / (ac.session_hours * AC_VCPU)
    add("sandbox CPU utilization", "agentcore", ac_util,
        f"{usage['CPUUsed-vCPUHours']:.3f} used vCPU-h / ({ac.session_hours:.1f} session-h x {AC_VCPU} vCPU)",
        "measured")
    ac_mem_avg = usage["MemoryUsed-GBHours"] / ac.session_hours
    add("average memory used per session (GB)", "agentcore", ac_mem_avg,
        f"{usage['MemoryUsed-GBHours']:.1f} GB-h / {ac.session_hours:.1f} session-h", "measured")

    # E2B Cloud: same sandbox-hours as the measured E2B run, documented price (not measured on E2B Cloud)
    e2b_cloud_h = E2B_VCPU * E2B_VCPU_S * 3600 + E2B_MEM_GIB * E2B_GIB_S * 3600
    add("E2B Cloud price per sandbox-hour (USD)", "e2b-cloud", e2b_cloud_h,
        f"{E2B_VCPU} x {E2B_VCPU_S} x 3600 + {E2B_MEM_GIB} x {E2B_GIB_S} x 3600", "documented")
    add("sandbox cost per run if run on E2B Cloud (USD)", "e2b-cloud", e2.session_hours * e2b_cloud_h,
        f"{e2.session_hours:.1f} measured session-h x {e2b_cloud_h:.4f}", "estimated")
    add("sandbox cost per 1,000 rollouts on E2B Cloud (USD)", "e2b-cloud",
        e2.session_hours * e2b_cloud_h / e2.sessions * 1000, "run cost / sessions x 1000", "estimated")

    # Self-hosted E2B: fixed hourly cost x run wall time (dedicated to this run)
    sh_h = sum(SELF_HOSTED.values())
    add("self-hosted E2B fixed cost per hour (USD)", "e2b-selfhosted", sh_h,
        " + ".join(f"{k} {v:.4f}" for k, v in SELF_HOSTED.items()), "estimated")
    add("sandbox cost per run, self-hosted, dedicated (USD)", "e2b-selfhosted", sh_h * e2.run_wall_hours,
        f"{sh_h:.2f} x {e2.run_wall_hours:.2f} h", "estimated")
    add("sandbox cost per 1,000 rollouts, self-hosted, dedicated (USD)", "e2b-selfhosted",
        sh_h * e2.run_wall_hours / e2.sessions * 1000, "run cost / sessions x 1000", "estimated")
    add("client node CPU utilization during the run", "e2b-selfhosted", e2b_cpu["average_percent"] / 100,
        "CloudWatch CPUUtilization average, 5 min periods", "measured")
    ac_per_session_h = ac_cost / ac.session_hours
    add("concurrent sessions needed for self-hosted to match AgentCore sandbox cost", "e2b-selfhosted",
        sh_h / ac_per_session_h,
        f"{sh_h:.2f} $/h / ({ac_cost:.2f} / {ac.session_hours:.1f}) $ per session-h", "estimated")
    add("average concurrent sessions during the run", "e2b-selfhosted", e2.session_hours / e2.run_wall_hours,
        f"{e2.session_hours:.1f} session-h / {e2.run_wall_hours:.2f} h", "measured")

    # Total training cost: GPU time is set by run wall time, which the sandbox latency changes
    for sb, sandbox_cost in (("agentcore", ac_cost), ("e2b-selfhosted", sh_h * e2.run_wall_hours)):
        wall = (ac if sb == "agentcore" else e2).run_wall_hours
        gpu = wall * GPU_H
        add("GPU cost per run (USD)", sb, gpu, f"{wall:.2f} h x {GPU_H}", "estimated")
        add("total cost per run (USD)", sb, gpu + sandbox_cost, "GPU + sandbox", "estimated")
        add("sandbox share of total cost", sb, sandbox_cost / (gpu + sandbox_cost), "sandbox / total", "estimated")

    df = pd.DataFrame(rows)
    df.to_csv(out / "cost.csv", index=False)

    # Break-even chart: cost per sandbox-hour vs CPU utilization
    u = [i / 100 for i in range(0, 101)]
    fig, ax = plt.subplots(figsize=(7, 4))
    for mem, style in ((ac_mem_avg, "-"), (4.295, "--"), (AC_MEM_GB, ":")):
        ax.plot([x * 100 for x in u], [AC_VCPU * x * AC_VCPU_H + mem * AC_GB_H for x in u], style, color="#1A73E8",
                label=f"AgentCore, memory used {mem:.1f} GB")
    ax.axhline(e2b_cloud_h, color="#E8710A", label="E2B Cloud, 2 vCPU / 4 GiB (allocated)")
    ax.axvline(ac_util * 100, color="#5F6368", lw=0.8)
    ax.text(ac_util * 100 + 1, e2b_cloud_h * 1.6, f"measured AgentCore\nCPU {ac_util:.1%}", fontsize=8)
    ax.set_xlabel("sandbox CPU utilization (%)")
    ax.set_ylabel("USD per sandbox-hour")
    ax.set_title("Break-even CPU utilization: AgentCore vs E2B Cloud")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(charts / "break_even.png", dpi=150)
    plt.close(fig)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
