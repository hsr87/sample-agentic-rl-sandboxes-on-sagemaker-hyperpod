"""CPU utilization of the self-hosted E2B client node(s) for a time window (input to bench/cost_model.py).

Reads the EC2 CPUUtilization metric (5 minute periods) of the running instances named <stack>-client, which run the
Firecracker sandboxes.

    python bench/e2b_client_cpu.py --start 2026-10-06T17:46:00Z --end 2026-10-06T20:50:00Z \
        --out results/usage/e2b_client_cpu.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import boto3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--stack", default="harbor-rl-e2b")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))

    ec2 = boto3.client("ec2", region_name=args.region)
    cw = boto3.client("cloudwatch", region_name=args.region)
    reservations = ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": [f"{args.stack}-client"]},
        {"Name": "instance-state-name", "Values": ["running"]},
    ])["Reservations"]
    instances = [(i["InstanceId"], i["InstanceType"]) for r in reservations for i in r["Instances"]]
    if not instances:
        raise SystemExit(f"no running instance named {args.stack}-client")

    points = []
    for instance_id, _ in instances:
        points += cw.get_metric_statistics(
            Namespace="AWS/EC2", MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start, EndTime=end, Period=300, Statistics=["Average", "Maximum"],
        )["Datapoints"]
    if not points:
        raise SystemExit("no datapoints in the window")
    out = {
        "instance": ", ".join(sorted({t for _, t in instances})) + " (self-hosted E2B client node)",
        "window": [args.start, args.end],
        "period_sec": 300,
        "datapoints": len(points),
        "average_percent": sum(p["Average"] for p in points) / len(points),
        "max_percent": max(p["Maximum"] for p in points),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
