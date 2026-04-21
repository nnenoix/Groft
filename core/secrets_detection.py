"""Rule #7 detectors: secrets, hard-deny paths, outbound commands, typosquat.

Pure-Python regex library — no external dependencies (gitleaks/trufflehog
would be better coverage, but they're binary; we cover the canonical 95%
and accept the tradeoff of shipping pure Python).

Callers (hooks) should import the specific detector they need; this
module itself does no I/O.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretMatch:
    kind: str
    sample: str  # truncated / redacted sample for the user-facing message
    line: int | None = None


_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(
        r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
    )),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_server_token", re.compile(r"\bghs_[A-Za-z0-9]{36}\b")),
    ("github_oauth", re.compile(r"\bgho_[A-Za-z0-9]{36}\b")),
    ("github_pat_fine", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("openai_proj_key", re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{40,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("stripe_live_secret", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b")),
    ("stripe_live_restricted", re.compile(r"\brk_live_[A-Za-z0-9]{24,}\b")),
    ("stripe_publishable_live", re.compile(r"\bpk_live_[A-Za-z0-9]{24,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("telegram_bot_token", re.compile(r"\b\d{9,10}:AA[A-Za-z0-9_\-]{32,35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{8,}\b")),
    ("private_key_pem", re.compile(
        r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----"
    )),
]


def _redact(sample: str, keep: int = 4) -> str:
    if len(sample) <= keep * 2:
        return "*" * len(sample)
    return f"{sample[:keep]}…{sample[-keep:]}"


def detect_secrets(text: str) -> list[SecretMatch]:
    """Return SecretMatch list for all hits in `text`. Empty list = clean."""
    hits: list[SecretMatch] = []
    if not text:
        return hits
    for kind, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            # line number of the match start
            line = text.count("\n", 0, m.start()) + 1
            sample = m.group(0)
            hits.append(SecretMatch(kind=kind, sample=_redact(sample), line=line))
    return hits


# --- hard-deny file paths (absolute or relative) ---------------------

_HARD_DENY_GLOBS: list[str] = [
    # SSH / GPG / AWS / cloud configs
    "**/.ssh/id_*",
    "**/.ssh/*_rsa",
    "**/.ssh/*_ed25519",
    "**/.ssh/*_ecdsa",
    "**/.ssh/*_dsa",
    "**/.ssh/known_hosts",
    "**/.ssh/authorized_keys",
    "**/.aws/credentials",
    "**/.aws/config",
    "**/.gnupg/**",
    "**/.netrc",
    # credential dumps / common .env/secret names
    "**/.env",
    "**/.env.*",
    "**/secrets.env",
    "**/secrets.json",
    "**/secrets.yaml",
    "**/secrets.yml",
    "**/credentials.json",
    "**/credentials.yaml",
    "**/credentials.yml",
    "**/service-account*.json",
    # key material
    "**/*.pem",
    "**/*.key",
    "**/*.p12",
    "**/*.pfx",
    "**/id_rsa",
    "**/id_ed25519",
    "**/id_ecdsa",
    "**/id_dsa",
]


def _normalize_path(path_str: str) -> str:
    """Expand ~, absolutize, forward-slash form for glob matching."""
    p = Path(os.path.expanduser(path_str))
    try:
        p = p.resolve(strict=False)
    except (OSError, RuntimeError):
        pass
    return p.as_posix()


def is_hard_deny_path(path_str: str) -> str | None:
    """Return the matching glob if path is hard-denied, else None."""
    if not path_str:
        return None
    normalized = _normalize_path(path_str)
    for pattern in _HARD_DENY_GLOBS:
        if fnmatch.fnmatchcase(normalized, pattern):
            return pattern
        # also match just the basename for short patterns like *.pem
        if fnmatch.fnmatchcase(Path(normalized).name, pattern.replace("**/", "")):
            return pattern
    return None


_READ_TOOLS: frozenset[str] = frozenset({
    "cat", "less", "more", "head", "tail", "bat", "xxd", "od", "strings",
    "view", "grep", "rg", "ack", "sed", "awk",
})


def bash_reads_sensitive_file(command: str) -> tuple[str, str] | None:
    """If Bash command reads a hard-denied path via cat/head/grep/etc,
    return (tool, path). Else None.

    Best-effort parse: split on shell separators (`;|&`), shlex-tokenize each
    sub-command, skip flags, and hard-deny-check every remaining argument.
    Catches `cat ~/.ssh/id_rsa`, `grep foo .env`, `head -5 .env`,
    `sed -n '1p' .env`.
    """
    if not command:
        return None
    for sub in re.split(r"[|;&]+", command):
        sub = sub.strip()
        if not sub:
            continue
        try:
            tokens = shlex.split(sub, posix=True)
        except ValueError:
            continue
        if not tokens:
            continue
        tool = tokens[0]
        if tool not in _READ_TOOLS:
            continue
        for tok in tokens[1:]:
            if tok.startswith("-"):
                continue
            if is_hard_deny_path(tok):
                return tool, tok
    return None


# --- outbound network commands ---------------------------------------

# Patterns are anchored at the start of a (sub-)command so we match
# `scp file host:` but not `git commit -m '… scp …'` — a word inside a
# quoted argument is not an invocation.
_OUTBOUND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("curl", re.compile(r"^\s*curl\b")),
    ("wget", re.compile(r"^\s*wget\b")),
    ("scp", re.compile(r"^\s*scp\b")),
    ("sftp", re.compile(r"^\s*sftp\b")),
    ("ssh_remote", re.compile(r"^\s*ssh\s+[\w.@\-]+")),
    ("rsync_remote", re.compile(r"^\s*rsync\b.*\b[\w.\-]+:")),
    ("nc", re.compile(r"^\s*nc\s+[\w.\-]+\s+\d+")),
    ("python_urlopen", re.compile(
        r"^\s*python[0-9.]*\s+-c\s+['\"].*(urlopen|requests\.|httpx\.|urllib)"
    )),
]

# URLs pointing to localhost are fine
_LOCAL_URL_RE = re.compile(
    r"\b(?:https?://)?(?:localhost|127\.0\.0\.1|0\.0\.0\.0|::1)\b"
)


def detect_outbound_command(command: str) -> str | None:
    """Return category if command sends data/request outside the host,
    else None. Localhost-only curl/wget calls are ignored.

    The command is split on shell separators (`;|&`) so only the first
    token of each sub-command is checked — avoids false positives when
    an outbound tool name appears inside a quoted argument.
    """
    if not command:
        return None
    for sub in re.split(r"[|;&]+", command):
        for kind, pattern in _OUTBOUND_PATTERNS:
            if pattern.search(sub):
                if kind in {"curl", "wget"} and _LOCAL_URL_RE.search(sub):
                    continue
                return kind
    return None


# --- package install commands ----------------------------------------

_PIP_INSTALL_RE = re.compile(
    r"\b(?:python[0-9.]*\s+-m\s+)?pip[0-9.]*\s+install\b([^|;&]*)"
)
_NPM_INSTALL_RE = re.compile(
    r"\bnpm\s+(?:install|i|add)\b([^|;&]*)"
)
_YARN_INSTALL_RE = re.compile(r"\byarn\s+(?:add)\b([^|;&]*)")


def _extract_packages(args: str) -> list[str]:
    """From the portion after `install`, extract non-flag tokens — these
    are the package names."""
    tokens = re.findall(r"(?<!\S)([A-Za-z0-9._@\-/=<>~]+)", args)
    packages = []
    for tok in tokens:
        if tok.startswith("-") or tok in {"install", "i", "add"}:
            continue
        # file paths / local installs are not package names we audit
        if tok.endswith(".tar.gz") or tok.endswith(".whl") or tok.startswith("."):
            continue
        packages.append(tok)
    return packages


def detect_package_install(command: str) -> tuple[str, list[str]] | None:
    """Return (ecosystem, [pkg_names]) if command is a package install
    (pip/npm/yarn), else None. Empty package list = install-from-lockfile
    (pip install -r requirements, npm install without args) — still flagged
    so the user has a chance to confirm that the lockfile is intentional."""
    if not command:
        return None
    m = _PIP_INSTALL_RE.search(command)
    if m:
        return "pip", _extract_packages(m.group(1))
    m = _NPM_INSTALL_RE.search(command)
    if m:
        return "npm", _extract_packages(m.group(1))
    m = _YARN_INSTALL_RE.search(command)
    if m:
        return "yarn", _extract_packages(m.group(1))
    return None


# --- typosquat heuristic --------------------------------------------

# Popular packages that attackers commonly typosquat. Not exhaustive —
# we cover the high-traffic library names whose near-misses have been
# documented historically (e.g. `axioss` for `axios`, `requets` for
# `requests`, `crossenv` for `cross-env`). A typosquat is an install
# target whose name is close-but-not-equal to a known-good name.
_POPULAR_PIP: frozenset[str] = frozenset({
    "requests", "urllib3", "numpy", "pandas", "pytest", "flask", "django",
    "fastapi", "pydantic", "sqlalchemy", "beautifulsoup4", "pillow",
    "tensorflow", "torch", "scikit-learn", "matplotlib", "scipy", "jinja2",
    "pyyaml", "cryptography", "setuptools", "wheel", "pip", "virtualenv",
    "boto3", "botocore", "openai", "anthropic", "httpx", "aiohttp",
    "click", "typer", "rich", "loguru", "python-dotenv", "redis",
    "psycopg2", "duckdb", "mcp", "pyjwt", "passlib",
})
_POPULAR_NPM: frozenset[str] = frozenset({
    "react", "react-dom", "vue", "angular", "next", "nuxt", "svelte",
    "express", "fastify", "koa", "nestjs", "axios", "lodash", "underscore",
    "moment", "dayjs", "date-fns", "jquery", "webpack", "vite", "rollup",
    "typescript", "eslint", "prettier", "jest", "mocha", "chai", "cypress",
    "playwright", "puppeteer", "cross-env", "dotenv", "chalk", "commander",
    "yargs", "ws", "socket.io", "node-fetch", "undici", "zod", "yup",
    "@types/node", "@types/react",
})


def _edit_distance_at_most(a: str, b: str, max_dist: int) -> int | None:
    """Levenshtein distance with early termination. Returns None if the
    distance exceeds `max_dist`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > max_dist:
        return None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        if min(curr) > max_dist:
            return None
        prev = curr
    return prev[lb] if prev[lb] <= max_dist else None


def _normalize_pkg(name: str) -> str:
    # strip version spec and extras: `flask==2.0` → `flask`, `package[extra]` → `package`
    name = re.split(r"[=<>~!\[]", name, maxsplit=1)[0]
    return name.strip().lower()


def typosquat_candidates(ecosystem: str, packages: list[str]) -> list[tuple[str, str]]:
    """Return [(installed_name, suspected_target)] for packages that look
    like typosquats of a popular name (edit distance 1, not equal).

    An empty list means nothing suspicious. Exact-match of a popular name
    is never flagged — that is the real library.
    """
    reference = _POPULAR_PIP if ecosystem == "pip" else _POPULAR_NPM
    hits: list[tuple[str, str]] = []
    for raw in packages:
        name = _normalize_pkg(raw)
        if not name or name in reference:
            continue
        for target in reference:
            if _edit_distance_at_most(name, target, 1) is not None:
                hits.append((raw, target))
                break
    return hits


# --- gitignore audit -------------------------------------------------

# Things that commonly leak if .gitignore is sloppy.
_RECOMMENDED_GITIGNORE: list[str] = [
    ".env",
    "*.env",
    "*.pem",
    "*.key",
    "secrets.json",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "*.log",
    ".DS_Store",
]


def gitignore_gaps(gitignore_text: str) -> list[str]:
    """Return a list of recommended patterns missing from .gitignore.

    Matching is line-prefix based; this is a heuristic, not a lint
    rule. If `.env` is covered by `*.env`, both count as covered.
    """
    if gitignore_text is None:
        return list(_RECOMMENDED_GITIGNORE)
    lines = {line.strip() for line in gitignore_text.splitlines() if line.strip() and not line.strip().startswith("#")}
    gaps: list[str] = []
    for rec in _RECOMMENDED_GITIGNORE:
        # A pattern is covered if its literal is present OR a wildcard form covers it.
        # Cheapest honest check: substring match after stripping trailing slash.
        rec_key = rec.rstrip("/")
        if any(rec_key in line or rec in line for line in lines):
            continue
        # wildcard .env covers *.env and vice versa
        if rec == ".env" and ("*.env" in lines or ".env*" in lines):
            continue
        if rec == "*.env" and ".env" in lines:
            continue
        gaps.append(rec)
    return gaps
