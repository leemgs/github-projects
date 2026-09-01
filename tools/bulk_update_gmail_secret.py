#!/usr/bin/env python3
"""Bulk-update the GMAIL_APP_PASSWORD GitHub Actions secret across many repos.

This tool rotates a single Actions secret (default: GMAIL_APP_PASSWORD) across a
list of repositories in one shot, so you never have to open each repo's
Settings -> Secrets and variables -> Actions page by hand.

By default it ONLY updates repositories that already have the secret, leaving
every other repository untouched. Use --create-missing to also add the secret to
repositories that don't have it yet.

Secrets are encrypted client-side with the repository's public key using a
libsodium sealed box (exactly as GitHub requires) before being uploaded, so the
plaintext value never travels to GitHub unencrypted.

--------------------------------------------------------------------------------
Requirements
--------------------------------------------------------------------------------
    python3 -m pip install -r requirements.txt   # installs PyNaCl

--------------------------------------------------------------------------------
Credentials (NEVER hard-code these)
--------------------------------------------------------------------------------
Provide a GitHub token with "repo" scope (classic) or the "Secrets" repository
write permission (fine-grained) via one of:

    export GITHUB_TOKEN=ghp_xxx
    # or place it in a gitignored .env file next to this script (see .env.example)

Provide the new secret value via one of (checked in this order):

    export GMAIL_APP_PASSWORD_NEW='new-app-password'
    --value-file /path/to/secret.txt
    interactive hidden prompt (default when neither is set)

--------------------------------------------------------------------------------
Examples
--------------------------------------------------------------------------------
    # Update every repo listed in docs/projects.json that already has the secret
    python3 bulk_update_gmail_secret.py

    # Preview what would change, without writing anything
    python3 bulk_update_gmail_secret.py --dry-run

    # Update an explicit set of repos
    python3 bulk_update_gmail_secret.py --repo leemgs/mymemo --repo leemgs/myoci

    # Update across ALL repos owned by a user/org (fetched live from the API)
    python3 bulk_update_gmail_secret.py --owner leemgs

    # Also create the secret where it is missing, using a different name
    python3 bulk_update_gmail_secret.py --secret-name GMAIL_APP_PASSWORD --create-missing
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

API_ROOT = "https://api.github.com"
DEFAULT_SECRET_NAME = "GMAIL_APP_PASSWORD"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECTS_JSON = SCRIPT_DIR.parent / "docs" / "projects.json"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, ignores comments/blank lines.

    Existing environment variables are never overwritten.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_pynacl():
    try:
        from nacl import encoding, public  # type: ignore
    except ImportError:
        eprint(
            "ERROR: PyNaCl is required for sealed-box encryption.\n"
            "       Install it with:  python3 -m pip install -r requirements.txt\n"
            "       (or:  python3 -m pip install pynacl)"
        )
        sys.exit(2)
    return encoding, public


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt `secret_value` for GitHub using the repo public key (sealed box)."""
    encoding, public = require_pynacl()
    pub = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(pub).encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(sealed).decode("utf-8")


# --------------------------------------------------------------------------- #
# GitHub REST client (stdlib only)
# --------------------------------------------------------------------------- #
class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "bulk-gmail-secret-updater")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                status = resp.status
                payload = json.loads(raw) if raw else {}
                return status, payload, resp.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                msg = json.loads(raw).get("message", raw)
            except json.JSONDecodeError:
                msg = raw
            raise GitHubError(exc.code, msg) from None

    # --- endpoints ---------------------------------------------------------- #
    def get_repo(self, full_name: str) -> dict:
        _, payload, _ = self._request("GET", f"/repos/{full_name}")
        return payload

    def list_owned_repos(self, owner: str) -> list[str]:
        """List repos for a user or org, following pagination."""
        # Try org first, fall back to user.
        for base in (f"/orgs/{owner}/repos", f"/users/{owner}/repos"):
            try:
                return self._paginate_repo_names(base)
            except GitHubError as exc:
                if exc.status == 404:
                    continue
                raise
        raise GitHubError(404, f"Owner '{owner}' not found as user or org")

    def _paginate_repo_names(self, base: str) -> list[str]:
        names: list[str] = []
        url = f"{base}?per_page=100&type=owner&sort=full_name"
        while url:
            _, payload, headers = self._request("GET", url)
            names.extend(r["full_name"] for r in payload)
            url = _next_link(headers.get("Link"))
        return names

    def secret_exists(self, full_name: str, secret_name: str) -> bool:
        try:
            self._request(
                "GET", f"/repos/{full_name}/actions/secrets/{secret_name}"
            )
            return True
        except GitHubError as exc:
            if exc.status == 404:
                return False
            raise

    def get_repo_public_key(self, full_name: str) -> tuple[str, str]:
        _, payload, _ = self._request(
            "GET", f"/repos/{full_name}/actions/secrets/public-key"
        )
        return payload["key_id"], payload["key"]

    def put_secret(
        self, full_name: str, secret_name: str, encrypted_value: str, key_id: str
    ) -> int:
        status, _, _ = self._request(
            "PUT",
            f"/repos/{full_name}/actions/secrets/{secret_name}",
            {"encrypted_value": encrypted_value, "key_id": key_id},
        )
        return status  # 201 = created, 204 = updated


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        url = section[0].strip().lstrip("<").rstrip(">")
        if 'rel="next"' in section[1]:
            return url
    return None


# --------------------------------------------------------------------------- #
# Repo resolution
# --------------------------------------------------------------------------- #
def repos_from_projects_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for entry in data:
        html_url = entry.get("html_url", "")
        # https://github.com/<owner>/<repo>
        parts = html_url.rstrip("/").split("/")
        if len(parts) >= 2:
            names.append(f"{parts[-2]}/{parts[-1]}")
    return names


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def resolve_target_repos(args, gh: GitHub) -> list[str]:
    if args.repo:
        return dedupe_preserve_order(args.repo)
    if args.owner:
        eprint(f"Fetching repositories owned by '{args.owner}' ...")
        return dedupe_preserve_order(gh.list_owned_repos(args.owner))
    projects_path = Path(args.projects_json)
    if not projects_path.is_file():
        eprint(f"ERROR: projects file not found: {projects_path}")
        sys.exit(2)
    return dedupe_preserve_order(repos_from_projects_json(projects_path))


# --------------------------------------------------------------------------- #
# Value & token resolution
# --------------------------------------------------------------------------- #
def resolve_secret_value(args) -> str:
    if args.value_file:
        value = Path(args.value_file).read_text(encoding="utf-8").strip("\n")
        if not value:
            eprint("ERROR: --value-file is empty")
            sys.exit(2)
        return value
    env_value = os.environ.get("GMAIL_APP_PASSWORD_NEW")
    if env_value:
        return env_value
    if not sys.stdin.isatty():
        eprint(
            "ERROR: no secret value provided. Set GMAIL_APP_PASSWORD_NEW, use "
            "--value-file, or run interactively."
        )
        sys.exit(2)
    value = getpass.getpass("New secret value (input hidden): ").strip()
    confirm = getpass.getpass("Confirm new secret value: ").strip()
    if value != confirm:
        eprint("ERROR: values did not match.")
        sys.exit(2)
    if not value:
        eprint("ERROR: empty secret value.")
        sys.exit(2)
    return value


def resolve_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        eprint(
            "ERROR: no GitHub token found. Set GITHUB_TOKEN (repo scope / Secrets "
            "write) in your environment or a gitignored .env file."
        )
        sys.exit(2)
    return token


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-update a GitHub Actions secret across many repos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--secret-name",
        default=DEFAULT_SECRET_NAME,
        help=f"Secret to update (default: {DEFAULT_SECRET_NAME}).",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "--repo",
        action="append",
        metavar="OWNER/REPO",
        help="Target repo (repeatable). Overrides projects.json / --owner.",
    )
    src.add_argument(
        "--owner",
        metavar="USER_OR_ORG",
        help="Update across ALL repos owned by this user/org (fetched via API).",
    )
    parser.add_argument(
        "--projects-json",
        default=str(DEFAULT_PROJECTS_JSON),
        help="Path to projects.json (default: repo docs/projects.json).",
    )
    parser.add_argument(
        "--value-file",
        metavar="PATH",
        help="Read the new secret value from this file instead of env/prompt.",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Also create the secret in repos that don't have it yet.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing anything.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt before writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    load_dotenv(SCRIPT_DIR / ".env")
    args = parse_args(argv)

    token = resolve_token()
    gh = GitHub(token)

    repos = resolve_target_repos(args, gh)
    if not repos:
        eprint("No target repositories resolved. Nothing to do.")
        return 1

    print(f"Secret name : {args.secret_name}")
    print(f"Targets     : {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}")
    print(f"Mode        : {'DRY-RUN (no writes)' if args.dry_run else 'LIVE'}")
    print(
        f"Missing     : {'create' if args.create_missing else 'skip'} "
        "repos without the secret\n"
    )

    # Resolve the value only when we may actually write.
    secret_value = None if args.dry_run else resolve_secret_value(args)

    if not args.dry_run and not args.yes:
        reply = input(
            f"About to write '{args.secret_name}' to up to {len(repos)} repos. "
            "Type 'yes' to continue: "
        ).strip().lower()
        if reply != "yes":
            print("Aborted.")
            return 1
        print()

    updated: list[str] = []
    created: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    for full_name in repos:
        try:
            exists = gh.secret_exists(full_name, args.secret_name)
            if not exists and not args.create_missing:
                print(f"  -  {full_name}: secret not present -> skip")
                skipped.append(full_name)
                continue

            action = "update" if exists else "create"
            if args.dry_run:
                print(f"  ~  {full_name}: would {action} '{args.secret_name}'")
                (updated if exists else created).append(full_name)
                continue

            key_id, public_key = gh.get_repo_public_key(full_name)
            encrypted = encrypt_secret(public_key, secret_value)
            status = gh.put_secret(full_name, args.secret_name, encrypted, key_id)
            if status == 201 or not exists:
                print(f"  +  {full_name}: created '{args.secret_name}'")
                created.append(full_name)
            else:
                print(f"  *  {full_name}: updated '{args.secret_name}'")
                updated.append(full_name)
        except GitHubError as exc:
            print(f"  !  {full_name}: {exc}")
            failed.append((full_name, str(exc)))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  !  {full_name}: {exc}")
            failed.append((full_name, str(exc)))

    print("\n--- Summary ---")
    print(f"  updated : {len(updated)}")
    print(f"  created : {len(created)}")
    print(f"  skipped : {len(skipped)}")
    print(f"  failed  : {len(failed)}")
    for name, err in failed:
        print(f"    - {name}: {err}")

    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        eprint("\nInterrupted.")
        sys.exit(130)
