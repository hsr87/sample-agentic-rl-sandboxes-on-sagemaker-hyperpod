"""Upload a results directory to $RESULTS_S3_URI/<relative path> (the trainer image has boto3 but no AWS CLI).

    python -m bench.s3sync /results/oracle
"""

import os
import sys
from pathlib import Path

import boto3


def main():
    src = Path(sys.argv[1])
    uri = os.environ["RESULTS_S3_URI"].removeprefix("s3://")
    bucket, _, prefix = uri.partition("/")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    n = 0
    for f in src.rglob("*"):
        if f.is_file():
            key = "/".join(p for p in (prefix, src.name, str(f.relative_to(src))) if p)
            s3.upload_file(str(f), bucket, key)
            n += 1
    print(f"uploaded {n} files to s3://{bucket}/{prefix}/{src.name}/")


if __name__ == "__main__":
    main()
