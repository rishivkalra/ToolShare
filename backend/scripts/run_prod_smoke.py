#!/usr/bin/env python
"""Run prod_smoke.sh against the deployed Cloud Run service from inside GCP
(via a Cloud Build step), since local egress may not reach *.run.app.

Usage: .venv/bin/python scripts/run_prod_smoke.py
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from gcp_auth import access_token  # noqa: E402
from gcp_provision import api, state  # noqa: E402

PROJECT = state["project_id"]
URL = state["service_url"]
BUCKET = f"{PROJECT}-build-src"


def main() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(Path(__file__).parent / "prod_smoke.sh", arcname="prod_smoke.sh")
    blob = f"smoke-{int(time.time())}.tar.gz"
    api(
        "POST",
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={blob}",
        raw_body=buf.getvalue(), content_type="application/gzip",
    )

    build = api(
        "POST", f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds",
        {
            "source": {"storageSource": {"bucket": BUCKET, "object": blob}},
            "steps": [{
                "name": "python:3.12-slim",
                "entrypoint": "bash",
                "args": ["-c", "apt-get -qq update && apt-get -qq install -y curl >/dev/null && bash prod_smoke.sh"],
                "env": [f"URL={URL}"],
            }],
            "timeout": "300s",
        },
    )
    build_id = build["metadata"]["build"]["id"]
    print(f"smoke build {build_id} against {URL}")

    status = "QUEUED"
    for _ in range(60):
        b = api("GET", f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{build_id}")
        status = b["status"]
        if status not in ("QUEUED", "WORKING", "PENDING"):
            break
        time.sleep(5)

    # Fetch the step log from the build logs bucket.
    log_bucket = b.get("logsBucket", f"gs://{PROJECT}_cloudbuild").removeprefix("gs://")
    resp = httpx.get(
        f"https://storage.googleapis.com/storage/v1/b/{log_bucket}/o/log-{build_id}.txt?alt=media",
        headers={"Authorization": f"Bearer {access_token()}"}, timeout=30,
    )
    for line in resp.text.splitlines():
        if line.startswith(("Step #0", "==", "SMOKE")) or "listing:" in line or "booking:" in line:
            print(line.replace("Step #0: ", "  "))
    print(f"\nRESULT: {status}")
    sys.exit(0 if status == "SUCCESS" else 1)


if __name__ == "__main__":
    main()
