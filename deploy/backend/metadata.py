"""Resolve release metadata without executing user-supplied workflow expressions."""
import datetime
import os
import re


def metadata(env):
    version = env.get("RELEASE_VERSION", "")
    if env.get("GITHUB_REF", "").startswith("refs/tags/backend-v"):
        version = env["GITHUB_REF"].removeprefix("refs/tags/backend-v")
    version = version.removeprefix("v")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:beta|rc)\.(0|[1-9]\d*))?", version):
        raise ValueError("Version must be X.Y.Z, X.Y.Z-beta.N or X.Y.Z-rc.N (optional leading v)")
    channel = "beta" if "-" in version else "stable"
    latest = env.get("PUBLISH_LATEST", "false") == "true"
    if latest and channel != "stable":
        raise ValueError("Prereleases cannot update latest")
    image = f"ghcr.io/{env['GITHUB_REPOSITORY_OWNER'].lower()}/ppanel-backend"
    tags = [f"{image}:{version}", f"{image}:{version}-sha-{env['BACKEND_SHA'][:12]}"]
    if latest:
        tags.append(f"{image}:latest")
    return {"version": version, "channel": channel, "image": image,
            "tags": ",".join(tags),
            "build_time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


if __name__ == "__main__":
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in metadata(os.environ).items():
            print(f"{key}={value}", file=output)
