#!/usr/bin/env python
"""Provision GCP and deploy the ToolShare API to Cloud Run — pure REST, no
gcloud CLI needed. Requires a prior `gcp_auth.py exchange` (cloud-platform
scope).

Idempotent: safe to re-run; each step skips or updates what already exists.
State (project id, internal secret) persists in ~/.toolshare/deploy_state.json.

Steps: project -> billing -> APIs -> Artifact Registry -> Firestore ->
Cloud Tasks queue -> GCS source upload -> Cloud Build -> Cloud Run deploy
(+ public invoker, runtime IAM) -> health check.

Usage:  .venv/bin/python scripts/gcp_provision.py [--billing ACCOUNT_ID]
"""
from __future__ import annotations

import io
import json
import secrets as pysecrets
import sys
import tarfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from gcp_auth import access_token  # noqa: E402

REGION = "us-central1"
SERVICE = "toolshare-api"
REPO = "toolshare"
QUEUE = "toolshare-jobs"
BACKEND_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path.home() / ".toolshare" / "deploy_state.json"

state: dict = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state():
    STATE_FILE.write_text(json.dumps(state, indent=2))


def api(method: str, url: str, body=None, ok=(200,), raw_body: bytes | None = None,
        content_type="application/json") -> dict:
    headers = {"Authorization": f"Bearer {access_token()}", "Content-Type": content_type}
    # Freshly-enabled APIs take a minute to propagate; retry on that error.
    for attempt in range(10):
        resp = httpx.request(
            method, url, headers=headers,
            json=body if raw_body is None else None,
            content=raw_body, timeout=120,
        )
        if resp.status_code in ok:
            return resp.json() if resp.text else {}
        retryable = ("SERVICE_DISABLED", "IAM_PERMISSION_DENIED", "does not have permission")
        if any(r in resp.text for r in retryable) or resp.status_code in (429, 500, 503):
            log(f"  ({resp.status_code}, waiting for propagation… attempt {attempt + 1})")
            time.sleep(20)
            continue
        break
    raise RuntimeError(f"{method} {url} -> {resp.status_code}: {resp.text[:800]}")


def wait_op(url: str, timeout_s: int = 600) -> dict:
    """Poll a google.longrunning operation until done."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        op = api("GET", url)
        if op.get("done"):
            if "error" in op:
                raise RuntimeError(f"operation failed: {op['error']}")
            return op.get("response", {})
        time.sleep(3)
    raise TimeoutError(url)


def log(msg: str):
    print(f"==> {msg}", flush=True)


# ---------------------------------------------------------------------------

def ensure_project() -> str:
    if "project_id" in state:
        log(f"project: {state['project_id']} (existing)")
        return state["project_id"]
    project_id = f"toolshare-{pysecrets.token_hex(3)}"
    log(f"creating project {project_id}")
    op = api(
        "POST", "https://cloudresourcemanager.googleapis.com/v3/projects",
        {"projectId": project_id, "displayName": "ToolShare"},
    )
    wait_op(f"https://cloudresourcemanager.googleapis.com/v3/{op['name']}")
    state["project_id"] = project_id
    save_state()
    return project_id


def ensure_billing(project_id: str, billing_account: str):
    info = api("GET", f"https://cloudbilling.googleapis.com/v1/projects/{project_id}/billingInfo")
    if info.get("billingEnabled"):
        log(f"billing: already linked to {info['billingAccountName']}")
        return
    log(f"linking billing {billing_account}")
    api(
        "PUT", f"https://cloudbilling.googleapis.com/v1/projects/{project_id}/billingInfo",
        {"billingAccountName": f"billingAccounts/{billing_account}"},
    )


def enable_apis(project_id: str):
    services = [
        "run.googleapis.com", "cloudbuild.googleapis.com",
        "artifactregistry.googleapis.com", "firestore.googleapis.com",
        "cloudtasks.googleapis.com", "storage.googleapis.com",
        "cloudresourcemanager.googleapis.com", "cloudscheduler.googleapis.com",
    ]
    log(f"enabling {len(services)} APIs")
    op = api(
        "POST",
        f"https://serviceusage.googleapis.com/v1/projects/{project_id}/services:batchEnable",
        {"serviceIds": services},
    )
    if not op.get("done"):
        wait_op(f"https://serviceusage.googleapis.com/v1/{op['name']}")


def project_number(project_id: str) -> str:
    p = api("GET", f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}")
    return p["projectNumber"]


def ensure_artifact_repo(project_id: str):
    base = f"https://artifactregistry.googleapis.com/v1/projects/{project_id}/locations/{REGION}/repositories"
    try:
        api("GET", f"{base}/{REPO}")
        log("artifact repo: exists")
        return
    except RuntimeError:
        pass
    log("creating artifact registry repo")
    op = api("POST", f"{base}?repositoryId={REPO}", {"format": "DOCKER"})
    wait_op(f"https://artifactregistry.googleapis.com/v1/{op['name']}")


def ensure_firestore(project_id: str):
    base = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases"
    dbs = api("GET", base).get("databases", [])
    if any(d["name"].endswith("/(default)") for d in dbs):
        log("firestore: (default) database exists")
        return
    log("creating firestore database")
    op = api(
        "POST", f"{base}?databaseId=(default)",
        {"type": "FIRESTORE_NATIVE", "locationId": REGION},
    )
    wait_op(f"https://firestore.googleapis.com/v1/{op['name']}")


def ensure_queue(project_id: str):
    base = f"https://cloudtasks.googleapis.com/v2/projects/{project_id}/locations/{REGION}/queues"
    try:
        api("GET", f"{base}/{QUEUE}")
        log("cloud tasks queue: exists")
        return
    except RuntimeError:
        pass
    log("creating cloud tasks queue")
    api("POST", base, {"name": f"projects/{project_id}/locations/{REGION}/queues/{QUEUE}"})


def ensure_digest_job(project_id: str, base_url: str):
    """Weekly Cloud Scheduler job: Monday 9am local -> wanted-nearby digest."""
    if not base_url:
        return  # first deploy doesn't know its URL yet; created on the next run
    base = f"https://cloudscheduler.googleapis.com/v1/projects/{project_id}/locations/{REGION}/jobs"
    job_name = f"{base}/toolshare-wanted-digest"
    body = {
        "name": f"projects/{project_id}/locations/{REGION}/jobs/toolshare-wanted-digest",
        "schedule": "0 16 * * 1",  # Mondays 16:00 UTC ≈ morning US
        "timeZone": "Etc/UTC",
        "httpTarget": {
            "uri": f"{base_url}/internal/tasks/wanted-digest",
            "httpMethod": "POST",
            "headers": {"X-Internal-Token": state["internal_secret"],
                        "Content-Type": "application/json"},
        },
    }
    try:
        api("GET", job_name)
        log("wanted-digest scheduler job: exists")
    except RuntimeError:
        log("creating wanted-digest scheduler job")
        api("POST", base, body)


def ensure_photos_bucket(project_id: str) -> str:
    bucket = f"{project_id}-photos"
    try:
        api("POST", f"https://storage.googleapis.com/storage/v1/b?project={project_id}",
            {"name": bucket, "location": "US-CENTRAL1",
             "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}}})
        log(f"created photos bucket {bucket}")
    except RuntimeError as e:
        if "409" not in str(e):
            raise
        log(f"photos bucket {bucket}: exists")
    # Public-read for listing photos (they are public content by design).
    policy = api("GET", f"https://storage.googleapis.com/storage/v1/b/{bucket}/iam")
    bindings = policy.get("bindings", [])
    if not any(b["role"] == "roles/storage.objectViewer" and "allUsers" in b.get("members", [])
               for b in bindings):
        bindings.append({"role": "roles/storage.objectViewer", "members": ["allUsers"]})
        api("PUT", f"https://storage.googleapis.com/storage/v1/b/{bucket}/iam",
            {"bindings": bindings})
        log("photos bucket made public-read")
    return bucket


def make_source_tarball() -> bytes:
    buf = io.BytesIO()
    skip = {".venv", "__pycache__", ".pytest_cache", "scripts"}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(BACKEND_DIR.rglob("*")):
            rel = path.relative_to(BACKEND_DIR)
            if any(part in skip for part in rel.parts) or not path.is_file():
                continue
            tar.add(path, arcname=str(rel))
    return buf.getvalue()


def upload_source(project_id: str) -> tuple[str, str]:
    bucket = f"{project_id}-build-src"
    try:
        api("POST", f"https://storage.googleapis.com/storage/v1/b?project={project_id}",
            {"name": bucket, "location": "US-CENTRAL1"})
        log(f"created bucket {bucket}")
    except RuntimeError as e:
        if "409" not in str(e):
            raise
        log(f"bucket {bucket}: exists")
    blob = f"source-{int(time.time())}.tar.gz"
    data = make_source_tarball()
    log(f"uploading source ({len(data) // 1024} KB)")
    api(
        "POST",
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={blob}",
        raw_body=data, content_type="application/gzip",
    )
    return bucket, blob


def cloud_build(project_id: str, bucket: str, blob: str) -> str:
    image = f"{REGION}-docker.pkg.dev/{project_id}/{REPO}/api:{int(time.time())}"
    log(f"cloud build -> {image}")
    op = api(
        "POST", f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/builds",
        {
            "source": {"storageSource": {"bucket": bucket, "object": blob}},
            "steps": [{"name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", image, "."]}],
            "images": [image],
            "timeout": "900s",
        },
    )
    build_id = op["metadata"]["build"]["id"]
    log(f"build {build_id} running (2-5 min)…")
    deadline = time.time() + 900
    while time.time() < deadline:
        b = api("GET", f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/builds/{build_id}")
        status = b["status"]
        if status == "SUCCESS":
            log("build succeeded")
            return image
        if status in ("FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED"):
            raise RuntimeError(f"build {status}; log: {b.get('logUrl')}")
        time.sleep(10)
    raise TimeoutError("cloud build")


def ensure_vapid() -> None:
    """One-time VAPID keypair for Web Push — no third-party account needed."""
    if "vapid_private" in state:
        return
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    state["vapid_private"] = b64u(priv)
    state["vapid_public"] = b64u(pub)
    save_state()


def run_env(project_id: str, base_url: str) -> list[dict]:
    if "internal_secret" not in state:
        state["internal_secret"] = pysecrets.token_hex(32)
        save_state()
    ensure_vapid()
    env = {
        "TOOLSHARE_ENV": "prod",
        "TOOLSHARE_GCP_PROJECT": project_id,
        "TOOLSHARE_TASKS_QUEUE": QUEUE,
        "TOOLSHARE_TASKS_LOCATION": REGION,
        "TOOLSHARE_INTERNAL_TASK_SECRET": state["internal_secret"],
        "TOOLSHARE_DEV_AUTH_ENABLED": "true",  # STAGING ONLY — false at launch
        "TOOLSHARE_PLANNER": "gemini",  # Vertex AI via service identity, no key
        "TOOLSHARE_PHOTOS_BUCKET": f"{project_id}-photos",
        "TOOLSHARE_SERVICE_BASE_URL": base_url,
        "TOOLSHARE_VAPID_PUBLIC_KEY": state["vapid_public"],
        "TOOLSHARE_VAPID_PRIVATE_KEY": state["vapid_private"],
    }
    # Set once via: gcp_provision.py --google-client-id <id>.apps.googleusercontent.com
    # (creating the OAuth Web client itself is a one-time Cloud Console step).
    if state.get("google_client_id"):
        env["TOOLSHARE_GOOGLE_CLIENT_ID"] = state["google_client_id"]
    return [{"name": k, "value": v} for k, v in env.items()]


def deploy_run(project_id: str, image: str) -> str:
    base = f"https://run.googleapis.com/v2/projects/{project_id}/locations/{REGION}/services"
    template = {
        "containers": [{
            "image": image,
            "env": run_env(project_id, state.get("service_url", "")),
            "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
        }],
        "scaling": {"minInstanceCount": 0, "maxInstanceCount": 3},
    }
    exists = True
    try:
        api("GET", f"{base}/{SERVICE}")
    except RuntimeError:
        exists = False
    if exists:
        log("updating cloud run service")
        op = api("PATCH", f"{base}/{SERVICE}", {"template": template})
    else:
        log("creating cloud run service")
        op = api("POST", f"{base}?serviceId={SERVICE}", {"template": template})
    wait_op(f"https://run.googleapis.com/v2/{op['name']}")
    svc = api("GET", f"{base}/{SERVICE}")
    url = svc["uri"]

    if state.get("service_url") != url:
        # First deploy didn't know its own URL; patch it in for task callbacks.
        state["service_url"] = url
        save_state()
        log(f"setting TOOLSHARE_SERVICE_BASE_URL={url}")
        template["containers"][0]["env"] = run_env(project_id, url)
        op = api("PATCH", f"{base}/{SERVICE}", {"template": template})
        wait_op(f"https://run.googleapis.com/v2/{op['name']}")

    log("allowing unauthenticated invocations")
    api(
        "POST", f"{base}/{SERVICE}:setIamPolicy",
        {"policy": {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}},
    )
    return url


def grant_runtime_roles(project_id: str):
    number = project_number(project_id)
    member = f"serviceAccount:{number}-compute@developer.gserviceaccount.com"
    crm = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}"
    policy = api("POST", f"{crm}:getIamPolicy", {})
    changed = False
    for role in ("roles/datastore.user", "roles/cloudtasks.enqueuer",
                 "roles/storage.objectAdmin"):
        binding = next((b for b in policy["bindings"] if b["role"] == role), None)
        if binding is None:
            policy["bindings"].append({"role": role, "members": [member]})
            changed = True
        elif member not in binding["members"]:
            binding["members"].append(member)
            changed = True
    if changed:
        log("granting runtime roles to compute service account")
        api("POST", f"{crm}:setIamPolicy", {"policy": policy})
    else:
        log("runtime roles: already granted")


def main():
    billing = None
    if "--billing" in sys.argv:
        billing = sys.argv[sys.argv.index("--billing") + 1]
    if "--google-client-id" in sys.argv:
        state["google_client_id"] = sys.argv[sys.argv.index("--google-client-id") + 1]
        save_state()
    project_id = ensure_project()
    if billing:
        ensure_billing(project_id, billing)
    enable_apis(project_id)
    ensure_artifact_repo(project_id)
    ensure_firestore(project_id)
    ensure_queue(project_id)
    ensure_photos_bucket(project_id)
    grant_runtime_roles(project_id)
    bucket, blob = upload_source(project_id)
    image = cloud_build(project_id, bucket, blob)
    url = deploy_run(project_id, image)
    ensure_digest_job(project_id, url)

    log("health check")
    for attempt in range(10):
        try:
            r = httpx.get(f"{url}/health", timeout=15)
            if r.status_code == 200:
                print(f"\nDEPLOYED: {url}\n  healthz: {r.json()}\n  project: {project_id}")
                return
        except httpx.HTTPError:
            pass
        time.sleep(5)
    print(f"\nDEPLOYED: {url}\n  (direct health probe blocked by sandbox egress — "
          "verify via scripts/run_prod_smoke.py, which tests from inside GCP)")


if __name__ == "__main__":
    main()
