#!/usr/bin/env python3
"""Deploy tested revisions from origin/main to a local release directory."""

from __future__ import annotations

import argparse
import fcntl
import io
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger("mydictionary-autodeploy")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MUTABLE_DATA_FILES = ("words.json", "words_vi.json", "words_ja.json")


@dataclass(frozen=True)
class Config:
    app_root: Path
    repository_url: str
    service_label: str
    bootstrap_python: Path
    source_dir: Path
    releases_dir: Path
    current_link: Path
    state_file: Path
    lock_file: Path
    config_file: Path
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Config":
        app_root = Path(os.environ["MYDICTIONARY_APP_ROOT"]).expanduser().resolve()
        return cls(
            app_root=app_root,
            repository_url=os.environ["MYDICTIONARY_REPOSITORY_URL"],
            service_label=os.environ.get(
                "MYDICTIONARY_SERVICE_LABEL",
                "com.pirajoke.max-context-bot",
            ),
            bootstrap_python=Path(
                os.environ["MYDICTIONARY_BOOTSTRAP_PYTHON"]
            ).expanduser().resolve(),
            source_dir=app_root / ".deploy-source",
            releases_dir=app_root / "releases",
            current_link=app_root / "current",
            state_file=app_root / ".deployed-sha",
            lock_file=app_root / ".deploy.lock",
            config_file=app_root / "config.yaml",
            data_dir=app_root,
        )


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    LOGGER.info("Running: %s", " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=text,
    )


def validate_config(config: Config) -> None:
    if not config.app_root.is_dir():
        raise RuntimeError(f"Application root does not exist: {config.app_root}")
    if not config.bootstrap_python.is_file():
        raise RuntimeError(f"Bootstrap Python does not exist: {config.bootstrap_python}")
    if not config.config_file.is_file():
        raise RuntimeError(f"Bot config does not exist: {config.config_file}")
    for filename in MUTABLE_DATA_FILES:
        if not (config.data_dir / filename).is_file():
            raise RuntimeError(f"Mutable dictionary is missing: {filename}")


def ensure_source_checkout(config: Config) -> None:
    git_dir = config.source_dir / ".git"
    if not git_dir.is_dir():
        if config.source_dir.exists():
            raise RuntimeError(f"Deploy source exists but is not a Git repository: {config.source_dir}")
        run([
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            config.repository_url,
            str(config.source_dir),
        ])
    remote = run(
        ["git", "-C", str(config.source_dir), "remote", "get-url", "origin"]
    ).stdout.strip()
    if remote != config.repository_url:
        raise RuntimeError(f"Unexpected origin URL: {remote}")
    run([
        "git",
        "-C",
        str(config.source_dir),
        "fetch",
        "--prune",
        "origin",
        "main",
    ])


def main_sha(config: Config) -> str:
    sha = run([
        "git",
        "-C",
        str(config.source_dir),
        "rev-parse",
        "origin/main",
    ]).stdout.strip()
    if not SHA_PATTERN.fullmatch(sha):
        raise RuntimeError(f"Invalid origin/main revision: {sha}")
    return sha


def deployed_sha(config: Config) -> str | None:
    if not config.state_file.exists():
        return None
    sha = config.state_file.read_text(encoding="ascii").strip()
    return sha if SHA_PATTERN.fullmatch(sha) else None


def changed_mutable_data(config: Config, old_sha: str, new_sha: str) -> list[str]:
    result = run([
        "git",
        "-C",
        str(config.source_dir),
        "diff",
        "--name-only",
        old_sha,
        new_sha,
        "--",
        *MUTABLE_DATA_FILES,
    ])
    return [line for line in result.stdout.splitlines() if line]


def is_fast_forward(config: Config, old_sha: str, new_sha: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(config.source_dir),
            "merge-base",
            "--is-ancestor",
            old_sha,
            new_sha,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Unable to validate main history: {result.stderr.strip()}")
    return result.returncode == 0


def safe_extract(archive: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError(f"Release archive contains a link: {member.name}")
            target = (destination / member.name).resolve()
            if destination.resolve() not in (target, *target.parents):
                raise RuntimeError(f"Unsafe archive path: {member.name}")
        bundle.extractall(destination, filter="data")


def build_release(config: Config, sha: str) -> Path:
    release = config.releases_dir / sha
    if release.is_dir():
        return release

    config.releases_dir.mkdir(parents=True, exist_ok=True)
    temp_release = Path(tempfile.mkdtemp(prefix=f".{sha[:12]}-", dir=config.releases_dir))
    try:
        archive = run(
            [
                "git",
                "-C",
                str(config.source_dir),
                "archive",
                "--format=tar",
                sha,
            ],
            text=False,
        ).stdout
        safe_extract(archive, temp_release)

        for filename in ("bot.py", "tts.py", "requirements.txt"):
            if not (temp_release / filename).is_file():
                raise RuntimeError(f"Release is missing required file: {filename}")
        if (temp_release / "config.yaml").exists():
            raise RuntimeError("Repository release must not contain config.yaml")

        venv_dir = temp_release / ".venv"
        run([str(config.bootstrap_python), "-m", "venv", str(venv_dir)])
        release_python = venv_dir / "bin" / "python3"
        run([
            str(release_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--requirement",
            str(temp_release / "requirements.txt"),
        ])

        test_env = os.environ.copy()
        test_env.update({
            "ALLOWED_USER_ID": "1",
            "BOT_TOKEN": "123456:AUTODEPLOYTEST",
            "DATA_DIR": str(temp_release / ".test-data"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        run(
            [str(release_python), "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=temp_release,
            env=test_env,
        )
        python_files = sorted(str(path.name) for path in temp_release.glob("*.py"))
        run(
            [str(release_python), "-m", "py_compile", *python_files],
            cwd=temp_release,
            env=test_env,
        )
        shutil.rmtree(temp_release / ".test-data", ignore_errors=True)
        (temp_release / "config.yaml").symlink_to(config.config_file)
        temp_release.rename(release)
        return release
    except Exception:
        shutil.rmtree(temp_release, ignore_errors=True)
        raise


def current_target(config: Config) -> Path | None:
    if config.current_link.is_symlink():
        return config.current_link.resolve()
    if config.current_link.exists():
        raise RuntimeError(f"Current path is not a symlink: {config.current_link}")
    return None


def activate_release(config: Config, release: Path) -> None:
    next_link = config.app_root / f".current-{os.getpid()}"
    next_link.unlink(missing_ok=True)
    next_link.symlink_to(release, target_is_directory=True)
    os.replace(next_link, config.current_link)


def restart_service(config: Config) -> None:
    domain = f"gui/{os.getuid()}/{config.service_label}"
    run(["launchctl", "kickstart", "-k", domain])


def service_is_running(config: Config) -> bool:
    domain = f"gui/{os.getuid()}/{config.service_label}"
    result = subprocess.run(
        ["launchctl", "print", domain],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "state = running" in result.stdout


def wait_for_service(config: Config, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    consecutive_checks = 0
    while time.monotonic() < deadline:
        if service_is_running(config):
            consecutive_checks += 1
            if consecutive_checks >= 3:
                return
        else:
            consecutive_checks = 0
        time.sleep(2)
    raise RuntimeError(f"Service did not become healthy: {config.service_label}")


def write_state(config: Config, sha: str) -> None:
    temp_state = config.state_file.with_suffix(".tmp")
    temp_state.write_text(f"{sha}\n", encoding="ascii")
    os.replace(temp_state, config.state_file)


def deploy(config: Config, *, prepare_only: bool = False) -> str:
    validate_config(config)
    config.lock_file.touch(mode=0o600, exist_ok=True)
    with config.lock_file.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOGGER.info("Another deployment is already running")
            return "locked"

        ensure_source_checkout(config)
        target_sha = main_sha(config)
        old_sha = deployed_sha(config)
        old_release = current_target(config)

        if old_sha == target_sha and old_release == config.releases_dir / target_sha:
            LOGGER.info("Already deployed: %s", target_sha)
            return target_sha

        if old_sha:
            if not is_fast_forward(config, old_sha, target_sha):
                raise RuntimeError(
                    "Automatic deployment refused because origin/main is not a fast-forward"
                )
            changed_data = changed_mutable_data(config, old_sha, target_sha)
            if changed_data:
                raise RuntimeError(
                    "Automatic deployment refused because mutable dictionaries changed: "
                    + ", ".join(changed_data)
                )

        release = build_release(config, target_sha)
        activate_release(config, release)
        if prepare_only:
            LOGGER.info("Prepared release without restarting service: %s", target_sha)
            return target_sha

        try:
            restart_service(config)
            wait_for_service(config)
        except Exception:
            if old_release:
                LOGGER.exception("Deployment failed; restoring previous release")
                activate_release(config, old_release)
                restart_service(config)
                wait_for_service(config)
            raise

        write_state(config, target_sha)
        LOGGER.info("Deployment completed: %s", target_sha)
        return target_sha


def adopt_current_release(config: Config) -> str:
    """Record an already-running initial release without restarting it."""
    validate_config(config)
    ensure_source_checkout(config)
    target_sha = main_sha(config)
    expected_release = config.releases_dir / target_sha
    if current_target(config) != expected_release:
        raise RuntimeError("Current release does not match origin/main")
    wait_for_service(config)
    write_state(config, target_sha)
    LOGGER.info("Adopted running release: %s", target_sha)
    return target_sha


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build and activate origin/main without restarting the service",
    )
    modes.add_argument(
        "--adopt-current",
        action="store_true",
        help="Record an already-running initial release without restarting it",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    try:
        config = Config.from_env()
        if args.adopt_current:
            adopt_current_release(config)
        else:
            deploy(config, prepare_only=args.prepare_only)
    except Exception:
        LOGGER.exception("Automatic deployment failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
