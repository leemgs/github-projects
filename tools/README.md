# Bulk secret updater — `GMAIL_APP_PASSWORD`

Rotate the `GMAIL_APP_PASSWORD` GitHub Actions secret across **all listed
repositories** in one command, instead of opening every repo's
`Settings → Secrets and variables → Actions` page by hand.

By default the tool **only updates repositories that already have the secret** —
every other repo is left untouched. Values are encrypted client-side with each
repository's public key (libsodium *sealed box*, exactly as the GitHub API
requires), so the plaintext password never reaches GitHub unencrypted.

The repository list is derived from [`../docs/projects.json`](../docs/projects.json)
(the same list powering the project site), so it stays in sync automatically.

---

## ⚠️ Security first

- **Never hard-code tokens or passwords** in any file. The token is read from the
  `GITHUB_TOKEN` environment variable or a **gitignored** `.env` file.
- If a token has ever been pasted into chat, an issue, a commit, or a log,
  **revoke it** at <https://github.com/settings/tokens> and generate a new one.
- The `.env` file is ignored by git (root `.gitignore` ignores `.env`). Keep it
  that way.

---

## Option A — Python (no `gh` CLI needed)

### 1. Install the one dependency

```bash
cd tools
python3 -m pip install -r requirements.txt   # PyNaCl
```

### 2. Provide credentials

```bash
cp .env.example .env       # then edit .env
# .env:
#   GITHUB_TOKEN=ghp_xxxxxxxx
#   GMAIL_APP_PASSWORD_NEW=the-new-app-password
```

You can also export them instead of using `.env`, or omit
`GMAIL_APP_PASSWORD_NEW` to be prompted (hidden input) at runtime.

**Token scope:** classic token needs the `repo` scope; a fine-grained token
needs *Secrets* repository permission = **Read and write** on the target repos.

### 3. Run

```bash
# Preview only — writes nothing
python3 bulk_update_gmail_secret.py --dry-run

# Update every listed repo that already has the secret
python3 bulk_update_gmail_secret.py

# Skip the confirmation prompt (for automation)
python3 bulk_update_gmail_secret.py --yes
```

### Useful flags

| Flag | Purpose |
| --- | --- |
| `--dry-run` | Show what would change; write nothing. |
| `--create-missing` | Also create the secret where it does not exist yet. |
| `--secret-name NAME` | Update a different secret (default `GMAIL_APP_PASSWORD`). |
| `--repo OWNER/REPO` | Target explicit repos (repeatable); overrides the JSON list. |
| `--owner USER_OR_ORG` | Target **all** repos owned by a user/org (fetched via API). |
| `--value-file PATH` | Read the new value from a file instead of env/prompt. |
| `--projects-json PATH` | Use a different project list file. |
| `--yes` | Skip the "type yes to continue" confirmation. |

Exit code is non-zero if any repository failed, so it is CI-friendly.

---

## Option B — GitHub CLI (`gh`)

If you already have [`gh`](https://cli.github.com/) and `jq` installed and are
authenticated (`gh auth login`), use the shell wrapper — `gh` performs the
encryption for you:

```bash
export GMAIL_APP_PASSWORD_NEW='the-new-app-password'
./bulk_update_gmail_secret_gh.sh --dry-run     # preview
./bulk_update_gmail_secret_gh.sh               # update existing only
./bulk_update_gmail_secret_gh.sh --create-missing
```

---

## How "already has the secret" is detected

For each repo the tool calls
`GET /repos/{owner}/{repo}/actions/secrets/GMAIL_APP_PASSWORD`.
`200` → the secret exists (update it); `404` → it does not (skip, unless
`--create-missing`). GitHub never returns secret *values*, only their presence
and metadata, so nothing sensitive is read back.

## Sample output

```
Secret name : GMAIL_APP_PASSWORD
Targets     : 16 repositories
Mode        : LIVE
Missing     : skip repos without the secret

  *  leemgs/mymemo: updated 'GMAIL_APP_PASSWORD'
  *  leemgs/used-notifier: updated 'GMAIL_APP_PASSWORD'
  -  leemgs/github-projects: secret not present -> skip
  ...

--- Summary ---
  updated : 7
  created : 0
  skipped : 9
  failed  : 0
```
