"""Encrypted off-device backup and recovery-drill orchestration."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import backup_db
from validate_sqlite_backup import validate as validate_sqlite

try:  # รันปกติ (scripts/ อยู่ใน sys.path)
    import win_process
except ModuleNotFoundError:  # ถูกโหลดตรงด้วย importlib จาก cwd ไหนก็ได้
    _wp_spec = importlib.util.spec_from_file_location(
        "garmin_win_process", Path(__file__).with_name("win_process.py")
    )
    win_process = importlib.util.module_from_spec(_wp_spec)
    _wp_spec.loader.exec_module(win_process)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GARMIN_ROOT = PROJECT_ROOT / "garmin"
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", GARMIN_ROOT / "data"))
PASSWORD_DPAPI_FILE = DATA_DIR / "restic_repository_password.dpapi"
OFFSITE_STATUS_FILE = DATA_DIR / "sync_lane" / "offsite_backup.json"
RESTORE_STATUS_FILE = DATA_DIR / "sync_lane" / "restore_drill.json"
LOCAL_REPOSITORY = Path(r"C:\Backup\run-performance-restic")
SOURCES = (
    Path(r"C:\Backup\garmin-db-daily"),
    Path(r"C:\Backup\Run-Performance"),
)
RELEASE_TAG = "offsite-backup"
RETENTION = {"daily": 7, "weekly": 8, "monthly": 12, "release_assets": 3}
ASSET_PREFIX = "restic-repository-"
EXCLUDES = ("**/.git/**", "**/.venv*/**", "**/__pycache__/**")


def _cleanup_restore_tree(root: Path) -> None:
    resolved = root.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if temp_root not in resolved.parents or not resolved.name.startswith(
        "run-performance-restore-drill-"
    ):
        raise OffsiteBackupError("unsafe_cleanup_target")

    shutil.rmtree(resolved, ignore_errors=True)
    if not resolved.exists():
        return
    if os.name != "nt":
        raise OffsiteBackupError("temp_cleanup_failed")

    environment = os.environ.copy()
    environment["RUN_PERF_RESTORE_CLEANUP_TARGET"] = str(resolved)
    completed = win_process.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            "$p=$env:RUN_PERF_RESTORE_CLEANUP_TARGET; "
            "if (-not $p) { exit 2 }; "
            "Get-ChildItem -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue | "
            "ForEach-Object { if ($_.IsReadOnly) { $_.IsReadOnly=$false } }; "
            "[IO.Directory]::Delete($p,$true)",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0 or resolved.exists():
        raise OffsiteBackupError("temp_cleanup_failed")


def plan() -> dict:
    return {
        "repository": str(LOCAL_REPOSITORY),
        "sources": [str(source) for source in SOURCES],
        "release_tag": RELEASE_TAG,
        "retention": RETENTION,
        "excludes": list(EXCLUDES),
    }


class OffsiteBackupError(RuntimeError):
    pass


def _write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"run_at": datetime.now(timezone.utc).isoformat(), **payload}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _find_executable(name: str) -> str:
    override = os.environ.get(f"RUN_PERF_{name.upper()}_EXECUTABLE")
    if override and Path(override).is_file():
        return override
    found = shutil.which(name)
    if found:
        return found
    if name == "restic":
        package_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        candidates = sorted(package_root.glob("restic.restic_*/*restic*_windows_amd64.exe"))
        if candidates:
            return str(candidates[-1])
    raise OffsiteBackupError(f"{name}_missing")


def _run(
    command: list[str], *, env=None, cwd=None, timeout=14_400,
    allow_failure=False,
):
    completed = win_process.run(
        command,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        # ระบุให้ได้ว่า "พังตอนทำอะไร" (gh release upload ≠ gh repo view) และแยก
        # "โดนสั่งจบจากข้างนอก" ออกจาก "คำสั่งตอบว่าล้มเหลว" — รอบที่โดนฆ่ามัก
        # ไม่มี stderr เลย ถ้าไม่บอกตรง ๆ จะเหลือแค่ตัวเลข exit ที่อ่านไม่ออก
        label = win_process.command_label(command)
        if win_process.was_terminated(completed.returncode):
            suffix = win_process.exit_reason(completed.returncode)
        else:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            suffix = (
                detail[-1][:300] if detail
                else win_process.exit_reason(completed.returncode)
            )
        raise OffsiteBackupError(f"command_failed:{label}:{suffix}")
    return completed


def _restic_environment(password: str) -> dict:
    environment = os.environ.copy()
    environment["RESTIC_REPOSITORY"] = str(LOCAL_REPOSITORY)
    environment["RESTIC_PASSWORD"] = password
    return environment


def _get_password() -> str:
    if not PASSWORD_DPAPI_FILE.is_file() or PASSWORD_DPAPI_FILE.stat().st_size == 0:
        raise OffsiteBackupError("secret_missing")
    try:
        password = backup_db._dpapi_unprotect(PASSWORD_DPAPI_FILE.read_bytes()).strip()
    except Exception as exc:
        raise OffsiteBackupError("secret_unprotect_failed") from exc
    if len(password) < 20:
        raise OffsiteBackupError("secret_invalid")
    return password


def _latest_verified_daily_database() -> Path:
    candidates = sorted(SOURCES[0].glob("garmin-*.db"))
    if not candidates:
        raise OffsiteBackupError("daily_backup_missing")
    latest = candidates[-1]
    result = validate_sqlite(latest)
    if not result["ok"]:
        raise OffsiteBackupError("daily_backup_invalid")
    return latest


def _ensure_release(gh: str, repo: str) -> None:
    existing = _run(
        [gh, "release", "view", RELEASE_TAG, "--repo", repo],
        allow_failure=True,
        timeout=60,
    )
    if existing.returncode == 0:
        return
    _run(
        [
            gh, "release", "create", RELEASE_TAG, "--repo", repo,
            "--title", "Encrypted offsite backup",
            "--notes", "Automated encrypted Restic repository snapshots. Restore via the guarded recovery workflow.",
            "--latest=false", "--target", "main",
        ],
        timeout=120,
    )


def _archive_repository(destination: Path) -> tuple[Path, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    archive = destination / f"{ASSET_PREFIX}{stamp}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for path in sorted(LOCAL_REPOSITORY.rglob("*")):
            if path.is_file() and path.parent.name != "locks":
                bundle.write(path, path.relative_to(LOCAL_REPOSITORY))
    digest = _sha256_file(archive)
    return archive, digest


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _upload_and_rotate_assets(gh: str, repo: str, archive: Path) -> None:
    _ensure_release(gh, repo)
    _run(
        [gh, "release", "upload", RELEASE_TAG, str(archive), "--repo", repo],
        timeout=14_400,
    )
    result = _run(
        [gh, "release", "view", RELEASE_TAG, "--repo", repo, "--json", "assets"],
        timeout=60,
    )
    assets = json.loads(result.stdout).get("assets", [])
    managed = sorted(
        (asset for asset in assets if asset.get("name", "").startswith(ASSET_PREFIX)),
        key=lambda asset: (asset.get("createdAt", ""), asset.get("name", "")),
    )
    for old in managed[:-RETENTION["release_assets"]]:
        _run(
            [gh, "release", "delete-asset", RELEASE_TAG, old["name"], "--repo", repo, "--yes"],
            timeout=120,
        )


def _repository_name(gh: str) -> str:
    result = _run(
        [gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    repository = result.stdout.strip()
    if "/" not in repository:
        raise OffsiteBackupError("github_repository_unknown")
    return repository


def run_backup() -> dict:
    try:
        password = _get_password()
        restic = _find_executable("restic")
        gh = _find_executable("gh")
        if not LOCAL_REPOSITORY.joinpath("config").is_file():
            raise OffsiteBackupError("repository_not_initialized")
        for source in SOURCES:
            if not source.is_dir():
                raise OffsiteBackupError(f"source_missing:{source.name}")
        verified_database = _latest_verified_daily_database()
        environment = _restic_environment(password)
        backup_command = [
            restic, "backup", *map(str, SOURCES), "--host", platform.node(), "--tag", "run-performance",
        ]
        for pattern in EXCLUDES:
            backup_command.extend(["--exclude", pattern])
        _run(
            backup_command,
            env=environment,
        )
        _run(
            [
                restic, "forget", "--keep-daily", str(RETENTION["daily"]),
                "--keep-weekly", str(RETENTION["weekly"]),
                "--keep-monthly", str(RETENTION["monthly"]), "--prune",
            ],
            env=environment,
        )
        _run([restic, "check"], env=environment)

        repo = _repository_name(gh)
        with tempfile.TemporaryDirectory(prefix="run-performance-offsite-") as raw:
            archive, digest = _archive_repository(Path(raw))
            asset_name = archive.name
            size_bytes = archive.stat().st_size
            _upload_and_rotate_assets(gh, repo, archive)

        payload = {
            "ok": True,
            "reason": "ok",
            "asset": asset_name,
            "archive_sha256": digest,
            "archive_size_bytes": size_bytes,
            "verified_database": verified_database.name,
        }
    except (OffsiteBackupError, OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        reason = str(exc) or exc.__class__.__name__
        payload = {"ok": False, "reason": reason[:400]}
    _write_status(OFFSITE_STATUS_FILE, payload)
    return payload


def _latest_asset(gh: str, repo: str) -> str:
    result = _run(
        [gh, "release", "view", RELEASE_TAG, "--repo", repo, "--json", "assets"],
        timeout=60,
    )
    assets = [
        asset for asset in json.loads(result.stdout).get("assets", [])
        if asset.get("name", "").startswith(ASSET_PREFIX)
    ]
    if not assets:
        raise OffsiteBackupError("offsite_asset_missing")
    return max(assets, key=lambda asset: (asset.get("createdAt", ""), asset["name"]))["name"]


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise OffsiteBackupError("unsafe_archive_path")
        bundle.extractall(destination)


def run_restore_drill() -> dict:
    root = Path(tempfile.mkdtemp(prefix="run-performance-restore-drill-"))
    try:
        password = _get_password()
        restic = _find_executable("restic")
        gh = _find_executable("gh")
        repo = _repository_name(gh)
        asset_name = _latest_asset(gh, repo)

        _run(
            [
                gh, "release", "download", RELEASE_TAG, "--repo", repo,
                "--pattern", asset_name, "--dir", str(root),
            ],
            timeout=14_400,
        )
        archive = root / asset_name
        repository = root / "repository"
        repository.mkdir()
        _safe_extract(archive, repository)
        environment = os.environ.copy()
        environment["RESTIC_REPOSITORY"] = str(repository)
        environment["RESTIC_PASSWORD"] = password
        snapshots = _run([restic, "snapshots", "--json"], env=environment)
        snapshot_rows = json.loads(snapshots.stdout)
        if not snapshot_rows:
            raise OffsiteBackupError("snapshot_missing")
        target = root / "restored"
        _run([restic, "restore", "latest", "--target", str(target)], env=environment)
        databases = sorted(target.rglob("garmin-*.db"))
        if not databases:
            databases = sorted(target.rglob("garmin.db"))
        if not databases:
            raise OffsiteBackupError("restored_database_missing")
        restored_database = databases[-1]
        validation = validate_sqlite(restored_database)
        if not validation["ok"]:
            raise OffsiteBackupError("restored_database_invalid")

        payload = {
            "ok": True,
            "reason": "ok",
            "asset": asset_name,
            "snapshot_count": len(snapshot_rows),
            "restored_database": restored_database.name,
            "restored_size_bytes": validation["size_bytes"],
        }
    except (OffsiteBackupError, OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        reason = str(exc) or exc.__class__.__name__
        payload = {"ok": False, "reason": reason[:400]}
    try:
        _cleanup_restore_tree(root)
    except (OffsiteBackupError, OSError, subprocess.SubprocessError) as exc:
        payload = {"ok": False, "reason": str(exc)[:400] or "temp_cleanup_failed"}
    _write_status(RESTORE_STATUS_FILE, payload)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="show the non-secret backup plan")
    plan_parser.add_argument("--json", action="store_true")
    backup_parser = subparsers.add_parser("backup", help="create and upload an encrypted snapshot")
    backup_parser.add_argument("--json", action="store_true")
    restore_parser = subparsers.add_parser("restore-drill", help="download and prove the newest offsite snapshot")
    restore_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "plan":
        payload = plan()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "backup":
        payload = run_backup()
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    if args.command == "restore-drill":
        payload = run_restore_drill()
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
