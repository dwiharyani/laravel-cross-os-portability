#!/usr/bin/env python3
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = os.environ["STAGE4_REPO"]
SHA = os.environ["STAGE4_SHA"]
PHP_RUNTIME = os.environ["STAGE4_PHP"]
LARAVEL_CONSTRAINT = os.environ.get("STAGE4_LARAVEL", "")
TEST_COMMAND = os.environ.get("STAGE4_TEST_COMMAND", "").strip()
OS_NAME = os.environ["STAGE4_OS"]
RUNNER = os.environ.get("STAGE4_RUNNER", "")
URL = os.environ["STAGE4_URL"]

ROOT = Path(tempfile.mkdtemp(prefix="stage4_"))
TARGET = ROOT / REPO.replace("/", "_")
LOG = ROOT / "execution.log"

result = {
    "repo_full_name": REPO,
    "url": URL,
    "latest_sha": SHA,
    "os": OS_NAME,
    "runner": RUNNER,
    "php_runtime_requested": PHP_RUNTIME,
    "laravel_version_constraint": LARAVEL_CONSTRAINT,
    "test_command": TEST_COMMAND,
    "clone_status": "NOT_RUN",
    "checkout_status": "NOT_RUN",
    "composer_json": False,
    "composer_lock": False,
    "composer_install": "NOT_RUN",
    "test_environment_preparation": "NOT_RUN",
    "database_preparation": "NOT_RUN",
    "test_execution": "NOT_RUN",
    "failure_category": "NONE",
    "failure_stage": "NONE",
    "failure_detail": "",
    "reproducibility_status": "FAILED",
}

def run(cmd, cwd=None, timeout=1800):
    started = time.time()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = p.stdout or ""
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n$ {cmd}\n{output}\n")
        return p.returncode, output, time.time() - started
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "") if isinstance(e.stdout, str) else ""
        output += "\nTIMEOUT\n"
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n$ {cmd}\n{output}\n")
        return 124, output, time.time() - started

def set_failure(category, stage, detail):
    result["failure_category"] = category
    result["failure_stage"] = stage
    result["failure_detail"] = detail[-12000:]

def main():
    # Clone exact repository and commit.
    rc, out, _ = run(f'git clone --no-tags --depth 1 "{URL}" "{TARGET}"', timeout=600)
    if rc != 0:
        set_failure("REPOSITORY", "CLONE", out)
        return finish()

    result["clone_status"] = "PASS"

    rc, out, _ = run(f'git fetch --depth 1 origin {SHA}', cwd=TARGET, timeout=600)
    if rc != 0:
        set_failure("REPOSITORY", "CHECKOUT", out)
        return finish()

    rc, out, _ = run(f'git checkout --detach {SHA}', cwd=TARGET, timeout=300)
    if rc != 0:
        set_failure("REPOSITORY", "CHECKOUT", out)
        return finish()

    result["checkout_status"] = "PASS"

    composer_json = TARGET / "composer.json"
    composer_lock = TARGET / "composer.lock"
    result["composer_json"] = composer_json.exists()
    result["composer_lock"] = composer_lock.exists()

    if not composer_json.exists():
        set_failure("COMPOSER", "COMPOSER_INSTALL", "composer.json was not found after checkout.")
        return finish()

    # Install dependencies using the same Composer protocol on every OS.
    rc, out, _ = run(
        "composer install --no-interaction --prefer-dist --no-progress --optimize-autoloader",
        cwd=TARGET,
        timeout=1800,
    )
    if rc != 0:
        low = out.lower()
        if "your lock file does not contain a compatible set of packages" in low or "requires php" in low:
            cat = "LOCKFILE_PHP_VERSION_MISMATCH"
        elif "could not resolve" in low or "conflict" in low or "requires ext-" in low:
            cat = "COMPOSER_DEPENDENCY_FAILURE"
        else:
            cat = "COMPOSER"
        result["composer_install"] = "FAIL"
        set_failure(cat, "COMPOSER_INSTALL", out)
        return finish()
    result["composer_install"] = "PASS"

    # Prepare .env using the repository's own example where available.
    env = TARGET / ".env"
    env_example = TARGET / ".env.example"
    prep_messages = []

    if not env.exists() and env_example.exists():
        env.write_text(env_example.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        prep_messages.append(".env created from .env.example")

    # Use PHP/Artisan only when present; do not overwrite an existing application DB design.
    artisan = TARGET / "artisan"
    if artisan.exists():
        rc, out, _ = run("php artisan key:generate --force", cwd=TARGET, timeout=300)
        if rc != 0:
            result["test_environment_preparation"] = "FAIL"
            set_failure("APPLICATION_CONFIGURATION", "TEST_ENVIRONMENT_PREPARATION", out)
            return finish()
        prep_messages.append("APP_KEY generated")

        run("php artisan config:clear", cwd=TARGET, timeout=300)
        prep_messages.append("Laravel config cleared")

    result["test_environment_preparation"] = "; ".join(prep_messages) if prep_messages else "No environment preparation required"

    # Do not silently replace an application's database configuration.
    # If an existing test database preparation command is declared, use it.
    result["database_preparation"] = "Repository database configuration preserved"

    command = TEST_COMMAND or "php artisan test"
    rc, out, _ = run(command, cwd=TARGET, timeout=1800)

    if rc == 0:
        result["test_execution"] = "PASS"
        result["reproducibility_status"] = "REPRODUCIBLE"
        result["failure_category"] = "NONE"
        result["failure_stage"] = "NONE"
        result["failure_detail"] = ""
    else:
        result["test_execution"] = "FAIL"
        low = out.lower()
        if "connection refused" in low or "sqlstate" in low or "database" in low and ("connect" in low or "connection" in low):
            cat = "DATABASE_FAILURE"
            stage = "DATABASE_OR_TEST_EXECUTION"
        elif "command not found" in low or "command is not defined" in low:
            cat = "TEST_COMMAND_UNAVAILABLE"
            stage = "TEST_EXECUTION"
        elif "requires php" in low or "platform requirement" in low:
            cat = "PHP_VERSION_DEPENDENCY_MISMATCH"
            stage = "TEST_EXECUTION"
        else:
            cat = "TEST_EXECUTION_FAILURE"
            stage = "TEST_EXECUTION"
        set_failure(cat, stage, out)

    finish()

def finish():
    out = Path("stage4_result.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
