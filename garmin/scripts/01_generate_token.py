#!/usr/bin/env python3
"""Generate Garmin Connect OAuth token for an athlete.

Usage:
    python scripts/01_generate_token.py

Interactive — prompts for athlete name, email, and password (via getpass).
Saves token to tokens/<name>/garmin_tokens.json
Password is NEVER stored anywhere.
"""

import os
import re
import subprocess
import sys
from getpass import getpass
from pathlib import Path

# Resolve project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACL_SCRIPT = PROJECT_ROOT.parent / "scripts" / "harden_private_acl.ps1"
_ATHLETE_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9_'-]{0,62}[a-z0-9])?\Z")


def validate_athlete_slug(value: str) -> str:
    """Return a safe token-directory slug while preserving legacy apostrophes."""
    slug = value.strip().lower()
    if not _ATHLETE_SLUG.fullmatch(slug):
        raise ValueError(
            "use 1-64 lowercase English letters/numbers with internal _, - or ' only"
        )
    return slug


def harden_garmin_private_dirs() -> None:
    """Fail closed if Windows cannot make token/data roots owner-only."""
    if os.name != "nt":
        return
    if not ACL_SCRIPT.is_file():
        raise RuntimeError(f"ACL hardening script not found: {ACL_SCRIPT}")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ACL_SCRIPT),
            "-Scope",
            "Garmin",
            "-Recurse",
        ],
        capture_output=True,
        text=False,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Windows ACL hardening failed; token creation stopped before credentials were written"
        )

def main():
    print("=" * 50)
    print("  Garmin Connect — Token Generator")
    print("=" * 50)
    print()

    # 1. Athlete name
    try:
        athlete_name = validate_athlete_slug(input("Athlete slug (e.g. dan or p'kao): "))
    except ValueError as exc:
        print(f"❌ Invalid athlete slug: {exc}.")
        sys.exit(1)

    try:
        harden_garmin_private_dirs()
    except Exception as exc:
        print(f"❌ Cannot secure the token directory: {exc}")
        sys.exit(1)

    token_dir = PROJECT_ROOT / "tokens" / athlete_name
    token_dir.mkdir(parents=True, exist_ok=True)

    # Check if token already exists
    token_file = token_dir / "garmin_tokens.json"
    if token_file.exists():
        overwrite = input(f"⚠️  Token already exists at {token_file}. Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)

    # 2. Credentials (interactive, never stored)
    print()
    email = input("Garmin Connect email: ").strip()
    password = getpass("Garmin Connect password (hidden): ")

    if not email or not password:
        print("❌ Email and password are required.")
        sys.exit(1)

    # 3. Set token storage path via env var
    os.environ["GARMINTOKENS"] = str(token_dir)

    # 4. Login
    print()
    print(f"🔐 Logging in as {email}...")
    print("   (If MFA is enabled, check your phone/email for the code)")
    print()

    try:
        from garminconnect import Garmin

        garmin = Garmin(
            email,
            password,
            prompt_mfa=lambda: input("Enter MFA/2FA code from your phone: ").strip(),
        )
        garmin.login(str(token_dir))

        # 5. Verify
        full_name = garmin.get_full_name()
        print(f"✅ Login successful! Welcome, {full_name}")
        print(f"📁 Token saved to: {token_dir}")
        print()
        print("You can now run the other scripts without entering your password again.")

    except Exception as e:
        print(f"❌ Login failed: {e}")
        print()
        print("Common issues:")
        print("  - Wrong email/password")
        print("  - MFA code not entered in time")
        print("  - Too many login attempts (wait 15 min)")
        sys.exit(1)


if __name__ == "__main__":
    main()
