# github-projects

A small GitHub Pages site that lists the web projects published under
[github.com/leemgs](https://github.com/leemgs/), **plus a bulk updater** for the
`GMAIL_APP_PASSWORD` GitHub Actions secret so you can rotate it across every
repository at once instead of editing each repo's settings page by hand.

- **Live site:** https://leemgs.github.io/github-projects/
- **Bulk secret updater (web):** https://leemgs.github.io/github-projects/secrets.html

> 한국어 설명은 [아래쪽](#한국어)에 있습니다.

---

## Contents

```
docs/
  index.html       # the project listing page (GitHub Pages root)
  secrets.html     # browser-based bulk secret updater (no console needed)
  projects.json    # bundled repository list, also the source of truth for targets
tools/
  bulk_update_gmail_secret.py      # Python CLI (self-contained, needs PyNaCl)
  bulk_update_gmail_secret_gh.sh   # gh-CLI alternative
  requirements.txt / .env.example / README.md
```

---

## Rotating `GMAIL_APP_PASSWORD`

There are two ways to do the same thing. Both update **only repositories that
already have the secret** by default, and both encrypt the value client-side
with each repository's public key (libsodium *sealed box*) exactly as the GitHub
API requires — the plaintext never reaches GitHub unencrypted.

### Option 1 — From the website (no console)

Open **[secrets.html](https://leemgs.github.io/github-projects/secrets.html)**
and:

1. Paste a **GitHub token** (see scopes below). It is held only in the page's
   memory for the duration of the tab — never saved, never sent anywhere except
   `api.github.com` over HTTPS.
2. Enter and confirm the **new secret value**.
3. Click **Load repositories** → the list is read from `projects.json`.
4. *(optional)* Click **Check which have the secret** to see, per repo, whether
   `GMAIL_APP_PASSWORD` is present (`has secret`) or not (`not set`).
5. *(optional)* Click **Preview (dry-run)** to see exactly what *would* happen —
   `would update` / `would create` / `would skip` per repo — **without writing
   anything**. This mirrors the CLI's `--dry-run`.
6. Select the repos you want (or use *Only those with the secret*) and click
   **Update selected repos**.

A progress bar and per-repo log show `updated` / `created` / `skipped` /
`failed` for each repository. The page is bilingual (English / 한국어).

**How it works technically.** GitHub's REST API supports CORS, so the browser
calls it directly. For each repo the page does
`GET /repos/{owner}/{repo}/actions/secrets/GMAIL_APP_PASSWORD` (200 = present,
404 = not set), fetches the repo public key, encrypts the value with
[libsodium](https://github.com/jedisct1/libsodium.js) loaded from a CDN, then
`PUT`s the encrypted value. No server, no build step.

### Option 2 — From the command line

See **[`tools/README.md`](tools/README.md)** for full details. Quick version:

```bash
cd tools
python3 -m pip install -r requirements.txt          # PyNaCl
export GITHUB_TOKEN=ghp_xxx
export GMAIL_APP_PASSWORD_NEW='the-new-app-password'

python3 bulk_update_gmail_secret.py --dry-run       # preview
python3 bulk_update_gmail_secret.py                 # update existing only
python3 bulk_update_gmail_secret.py --create-missing
```

Or, if you already use the GitHub CLI:

```bash
export GMAIL_APP_PASSWORD_NEW='the-new-app-password'
tools/bulk_update_gmail_secret_gh.sh --dry-run
tools/bulk_update_gmail_secret_gh.sh
```

### Token scopes

| Token type | Permission needed |
| --- | --- |
| Classic PAT | `repo` scope |
| Fine-grained PAT | **Secrets** repository permission = *Read and write* on the target repos |

Create tokens at <https://github.com/settings/tokens>. You must be an admin of
each repository whose secret you change.

---

## ⚠️ Security

- **Never commit tokens or passwords.** The root `.gitignore` ignores `.env`;
  keep credentials there or in environment variables only.
- The web page keeps your token in memory only and talks solely to
  `api.github.com`. It does not persist the token or the secret value.
- **If a token has ever been exposed** (pasted into chat, a commit, an issue, or
  a log), revoke it immediately at <https://github.com/settings/tokens> and
  generate a new one.

---

## Editing the project list

`docs/projects.json` is both the fallback list rendered by `index.html` and the
set of targets used by the bulk updater. Each entry's `html_url` determines the
`owner/repo` that gets updated, so keep that field accurate when adding or
removing projects.

---

<a name="한국어"></a>

## 한국어

`github.com/leemgs` 계정에서 공개한 웹 프로젝트 목록을 보여 주는 GitHub Pages
사이트이며, 여기에 더해 모든 저장소의 `GMAIL_APP_PASSWORD` GitHub Actions
시크릿을 **한 번에 일괄 변경**하는 기능이 포함되어 있습니다. 저장소마다 설정
페이지에 들어가 일일이 바꿀 필요가 없습니다.

- **사이트:** https://leemgs.github.io/github-projects/
- **일괄 시크릿 변경기(웹):** https://leemgs.github.io/github-projects/secrets.html

### 방법 1 — 웹사이트에서 (콘솔 불필요)

**[secrets.html](https://leemgs.github.io/github-projects/secrets.html)** 을 열고:

1. **GitHub 토큰**을 붙여넣습니다. 토큰은 탭이 열려 있는 동안 페이지 메모리에만
   존재하며, 저장되지 않고 `api.github.com`(HTTPS) 외에는 어디에도 전송되지
   않습니다.
2. **새 시크릿 값**을 입력하고 확인란에 한 번 더 입력합니다.
3. **저장소 불러오기**를 누르면 `projects.json`에서 목록을 읽어옵니다.
4. *(선택)* **시크릿 보유 여부 확인**으로 각 저장소에 `GMAIL_APP_PASSWORD`가
   있는지(`시크릿 있음`) 없는지(`없음`) 확인합니다.
5. *(선택)* **미리보기 (변경 안 함)** 를 누르면 실제로 아무것도 바꾸지 않고
   각 저장소에 대해 `갱신 예정` / `생성 예정` / `건너뜀 예정`을 보여 줍니다.
   CLI의 `--dry-run`과 동일합니다.
6. 원하는 저장소를 선택(또는 *시크릿 있는 것만*)한 뒤 **선택 저장소 갱신**을
   누릅니다.

진행률 표시줄과 저장소별 로그에 `갱신됨` / `생성됨` / `건너뜀` / `실패`가
표시됩니다. 페이지는 한국어·영어를 지원합니다.

**동작 원리.** GitHub REST API는 CORS를 지원하므로 브라우저에서 직접 호출합니다.
저장소마다 `GET .../actions/secrets/GMAIL_APP_PASSWORD`(200=있음, 404=없음)로
확인하고, 공개키를 받아 libsodium sealed box로 값을 암호화한 뒤 `PUT`으로
업로드합니다. 기본값으로는 **이미 시크릿이 있는 저장소만** 갱신합니다.

### 방법 2 — 명령줄에서

자세한 내용은 **[`tools/README.md`](tools/README.md)** 를 참고하세요.

```bash
cd tools
python3 -m pip install -r requirements.txt
export GITHUB_TOKEN=ghp_xxx
export GMAIL_APP_PASSWORD_NEW='새-비밀번호'
python3 bulk_update_gmail_secret.py --dry-run   # 미리보기
python3 bulk_update_gmail_secret.py             # 기존 저장소만 갱신
```

### 토큰 권한

- Classic 토큰: `repo` 범위
- Fine-grained 토큰: 대상 저장소에 **Secrets = 읽기·쓰기** 권한

<https://github.com/settings/tokens> 에서 발급하며, 변경 대상 저장소의 관리자여야
합니다.

### ⚠️ 보안

- **토큰·비밀번호를 커밋하지 마세요.** `.gitignore`가 `.env`를 무시합니다.
- 웹 페이지는 토큰을 메모리에만 두고 `api.github.com`하고만 통신하며 저장하지
  않습니다.
- 토큰이 채팅·커밋·이슈·로그 등에 노출된 적이 있다면 즉시
  <https://github.com/settings/tokens> 에서 폐기하고 새로 발급하세요.
