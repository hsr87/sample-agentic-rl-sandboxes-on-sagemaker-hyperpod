"""Pull AgentCore Runtime CloudWatch metrics for a time window (vended, service-side numbers).

  * Invocations / Throttles / Errors / SystemErrors / UserErrors per operation
    (dimensions: Resource=<runtime ARN>, Operation, ComputeType=MicroVM, Name=<runtime>::DEFAULT)
  * Sessions (new sessions) for InvokeAgentRuntime
  * CPUUsed-vCPUHours / MemoryUsed-GBHours, the billing-relevant usage
    (dimensions: Resource=<runtime ARN>, Service=AgentCore.Runtime, Name=<runtime>::DEFAULT).
    AWS documents that these usage metrics can arrive up to 60 minutes late.

    python bench/agentcore_metrics.py --start 2026-10-01T00:35:00Z --end 2026-10-01T01:05:00Z --out results/usage/x.json
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import boto3

NS = "AWS/Bedrock-AgentCore"
OPS = ["InvokeAgentRuntime", "InvokeAgentRuntimeCommand"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--runtime-arn", default=os.environ.get("AGENTCORE_RUNTIME_ARN"), required="AGENTCORE_RUNTIME_ARN" not in os.environ)
    ap.add_argument("--endpoint-name", default="harbor_rl_tasks::DEFAULT")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cw = boto3.client("cloudwatch", region_name=a.region)
    start, end = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (a.start, a.end))

    def stat(metric, dims, stat="Sum", period=60):
        r = cw.get_metric_statistics(Namespace=NS, MetricName=metric, StartTime=start, EndTime=end, Period=period,
                                     Statistics=[stat], Dimensions=[{"Name": k, "Value": v} for k, v in dims.items()])
        pts = r["Datapoints"]
        return {"sum": sum(p[stat] for p in pts), "max_per_min": max((p[stat] for p in pts), default=0.0)}

    out = {"window": [a.start, a.end], "runtime_arn": a.runtime_arn, "by_operation": {}, "usage": {}}
    for op in OPS:
        dims = {"Resource": a.runtime_arn, "Operation": op, "ComputeType": "MicroVM", "Name": a.endpoint_name}
        metrics = ["Invocations", "Throttles", "Errors", "SystemErrors", "UserErrors"]
        if op == "InvokeAgentRuntime":
            metrics.append("Sessions")
        out["by_operation"][op] = {m: stat(m, dims) for m in metrics}
    usage_dims = {"Resource": a.runtime_arn, "Service": "AgentCore.Runtime", "Name": a.endpoint_name}
    for m in ["CPUUsed-vCPUHours", "MemoryUsed-GBHours"]:
        out["usage"][m] = stat(m, usage_dims, period=300)["sum"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
