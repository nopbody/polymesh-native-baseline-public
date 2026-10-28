"""Hosted-only native baseline. No node, vulnerability payload, or local Rust build."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

RELEASE = "d44a84c1634d2fa6e0b3c690c569f43345683a1d"
TEST = "corporate_actions_test::dist_claim_works"
# Same toolchain image used by the released .circleci/config.yml:438-464.
IMAGE = "polymeshassociation/rust@sha256:012f704d6eda97fda7a80b11425882f19694caa7f8435eb32a3e2b3f5d1d14d2"
BUILD_SECONDS = 70 * 60
TEST_SECONDS = 30
GIB = 1024 ** 3


def main():
    if not (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_OS") == "Linux"
            and os.environ.get("AUTHORIZED_HOSTED_RUNNER") == "github-hosted"):
        raise SystemExit("Refusing: this entry point requires an authorized GitHub-hosted Linux job.")
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    source = workspace / "upstream"
    out = workspace / "artifacts"
    out.mkdir(exist_ok=True)
    status = {"release": RELEASE, "test": TEST, "image": IMAGE,
              "kind": "Native TestStorage infrastructure baseline, not vulnerability evidence",
              "status": "not passed", "commands": [], "node_or_chain_transactions": 0,
              "limits": {"build_workers": 2, "build_cpus": 2, "build_memory_gib": 6,
                         "build_seconds": BUILD_SECONDS, "test_memory_gib": 1,
                         "test_seconds": TEST_SECONDS},
              "limitations": ["Released TestStorage uses Identity/no_cdd; not unchanged Mainnet configuration",
                              "Linux artifacts are compiled here; macOS cached executables are not reused",
                              "Passing this test establishes the harness, not allowance security"]}
    name = "native-baseline-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=source, text=True, timeout=15).strip()

    def command(args, label, seconds, container=None):
        entry = {"label": label, "argv": args}
        status["commands"].append(entry)
        started = time.monotonic()
        initial_free = shutil.disk_usage(workspace).free
        with (out / (label + ".stdout")).open("xb") as stdout, (out / (label + ".stderr")).open("xb") as stderr:
            process = subprocess.Popen(args, cwd=workspace, stdout=stdout, stderr=stderr)
            try:
                while process.poll() is None:
                    free = shutil.disk_usage(workspace).free
                    if time.monotonic() - started > seconds:
                        raise RuntimeError(label + " exceeded its wall timeout")
                    if free < 2 * GIB or initial_free - free > 12 * GIB:
                        raise RuntimeError(label + " exceeded its bounded disk allowance")
                    time.sleep(1)
                entry["exit_code"] = process.returncode
                if process.returncode != 0:
                    raise RuntimeError(label + " failed; see preserved stdout/stderr")
            finally:
                if process.poll() is None:
                    try:
                        if container:
                            subprocess.run(["docker", "kill", container], stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, timeout=15, check=False)
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=15)
                entry["exit_code"] = process.returncode
                entry["elapsed_seconds"] = round(time.monotonic() - started, 3)

    try:
        assert git("rev-parse", "HEAD") == RELEASE, "Wrong source revision"
        assert not git("status", "--porcelain"), "Baseline requires an unmodified checkout"
        status["cargo_lock_sha256"] = hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest()
        command(["docker", "pull", IMAGE], "image-pull", 10 * 60)
        command(["docker", "run", "--rm", "--network", "none", IMAGE,
                 "rustc", "--version", "--verbose"], "compiler", 30)
        compiler = (out / "compiler.stdout").read_text()
        assert "rustc 1.100.0-nightly" in compiler and "2026-08-31" in compiler, "Unexpected compiler"
        mount = str(workspace) + ":/work"
        build = ["docker", "run", "--rm", "--name", name,
                 "--cpus", "2", "--memory", "6g", "--memory-swap", "6g", "--pids-limit", "1024",
                 "--ulimit", "core=0", "--volume", mount, "--workdir", "/work/upstream"]
        for key, value in {"SKIP_WASM_BUILD": "1", "RUST_BACKTRACE": "1", "RUSTFLAGS": "-D warnings",
                           "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
                           "CARGO_PROFILE_DEV_DEBUG": "0", "CARGO_PROFILE_TEST_DEBUG": "0",
                           "CARGO_HOME": "/work/.ci-cache/cargo"}.items():
            build += ["--env", key + "=" + value]
        build += [IMAGE, "cargo", "test", "--locked", "--package", "polymesh-runtime-tests",
                  "--lib", "--no-run", "--message-format=json"]
        print("Building the pinned native harness remotely; no test body has run yet.", flush=True)
        command(build, "build", BUILD_SECONDS, name)
        artifacts = []
        for line in (out / "build.stdout").read_text().splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (item.get("reason") == "compiler-artifact"
                    and item.get("target", {}).get("name") == "polymesh_runtime_tests"
                    and item.get("profile", {}).get("test") and item.get("executable")):
                artifacts.append(item["executable"])
        assert len(set(artifacts)) == 1, "Did not identify exactly one newly built test executable"
        executable = artifacts[0]
        relative = Path(executable).relative_to("/work/upstream/target")
        binary = source / "target" / relative
        assert binary.is_file()
        binary_hash = hashlib.sha256()
        with binary.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                binary_hash.update(block)
        status["binary_sha256"] = binary_hash.hexdigest()
        status["binary_container_path"] = executable
        assert not git("status", "--porcelain"), "Build changed tracked source"
        test = ["docker", "run", "--rm", "--name", name + "-test",
                "--network", "none", "--read-only", "--cpus", "1",
                "--memory", "1g", "--memory-swap", "1g", "--pids-limit", "128",
                "--ulimit", "core=0", "--ulimit", "cpu=10:15",
                "--tmpfs", "/tmp:rw,size=256m,mode=1777", "--volume", mount + ":ro",
                "--workdir", "/work/upstream", "--env", "RUST_BACKTRACE=1",
                IMAGE, executable, TEST, "--exact", "--nocapture", "--test-threads=1"]
        command(test, "test", TEST_SECONDS, name + "-test")
        stdout = (out / "test.stdout").read_text()
        assert "test " + TEST + " ... ok" in stdout, "Exact test did not pass"
        assert re.search(r"test result: ok\. 1 passed; 0 failed; 0 ignored;", stdout), "Zero/ignored tests do not count"
        assert not git("status", "--porcelain")
        status["status"] = "passed"
        status["runtime_test_bodies_passed"] = 1
        (out / "baseline-success.json").write_text(json.dumps(status, indent=2) + "\n")
        print(stdout, end="")
    except Exception as error:
        status["error"] = repr(error)
        raise
    finally:
        (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")


if __name__ == "__main__":
    main()
