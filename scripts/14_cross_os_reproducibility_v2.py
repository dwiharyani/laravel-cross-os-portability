#!/usr/bin/env python3
"""
Stage 4 v2 research-grade cross-OS execution.

Environment variables:
STAGE4_REPO, STAGE4_SHA, STAGE4_URL, STAGE4_OS, STAGE4_RUNNER
STAGE4_PHP, STAGE4_LARAVEL, STAGE4_TEST_COMMAND
STAGE4_EXECUTION_ID, STAGE4_OWNER, STAGE4_BATCH
STAGE4_PROJECT_ID, STAGE4_STARS, STAGE4_FORKS, STAGE4_POPULARITY_QUARTILE
STAGE4_DOCKER_STATUS
"""

import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ["STAGE4_REPO"]
SHA = os.environ["STAGE4_SHA"]
URL = os.environ["STAGE4_URL"]
OS_NAME = os.environ["STAGE4_OS"]
RUNNER = os.environ.get("STAGE4_RUNNER", "")
PHP_RUNTIME = os.environ.get("STAGE4_PHP", "")
LARAVEL_CONSTRAINT = os.environ.get("STAGE4_LARAVEL", "")
TEST_COMMAND = os.environ.get("STAGE4_TEST_COMMAND", "").strip()
EXECUTION_ID = os.environ.get("STAGE4_EXECUTION_ID", "")
OWNER = os.environ.get("STAGE4_OWNER", "")
BATCH = os.environ.get("STAGE4_BATCH", "")
PROJECT_ID = os.environ.get("STAGE4_PROJECT_ID", "")
STARS = os.environ.get("STAGE4_STARS", "")
FORKS = os.environ.get("STAGE4_FORKS", "")
POPULARITY_QUARTILE = os.environ.get("STAGE4_POPULARITY_QUARTILE", "")
DOCKER_STATUS = os.environ.get("STAGE4_DOCKER_STATUS", "")

ROOT = Path(tempfile.mkdtemp(prefix="stage4_v2_"))
TARGET = ROOT / REPO.replace("/", "_")
ARTIFACT = Path("stage4_execution")
LOGDIR = ARTIFACT / "logs"
ERRDIR = ARTIFACT / "errors"
DIAGDIR = ARTIFACT / "diagnostics"
LLMDIR = ARTIFACT / "llm"
for d in (ARTIFACT, LOGDIR, ERRDIR, DIAGDIR, LLMDIR):
    d.mkdir(parents=True, exist_ok=True)

started_at = datetime.now(timezone.utc)

result = {
    "schema_version": "stage4-v2",
    "execution_id": EXECUTION_ID,
    "execution_owner": OWNER,
    "execution_batch": BATCH,
    "project_id": PROJECT_ID,
    "repo_full_name": REPO,
    "url": URL,
    "latest_sha": SHA,
    "os": OS_NAME,
    "runner": RUNNER,
    "php_runtime_requested": PHP_RUNTIME,
    "php_runtime_constraint": os.environ.get("STAGE4_PHP_CONSTRAINT", ""),
    "php_runtime_source": os.environ.get("STAGE4_PHP_SOURCE", ""),
    "php_runtime_resolution": os.environ.get("STAGE4_PHP_RESOLUTION", ""),
    "php_runtime_confidence": os.environ.get("STAGE4_PHP_CONFIDENCE", ""),
    "php_version_actual": None,
    "composer_version": None,
    "git_version": None,
    "node_version": None,
    "laravel_version_constraint": LARAVEL_CONSTRAINT,
    "laravel_version_detected": None,
    "test_command": TEST_COMMAND,
    "test_command_source": "assignment" if TEST_COMMAND else "fallback",
    "test_framework": None,
    "stars_github": STARS,
    "forks_count": FORKS,
    "popularity_quartile": POPULARITY_QUARTILE,
    "docker_status": DOCKER_STATUS,
    "clone_status": "NOT_RUN",
    "checkout_status": "NOT_RUN",
    "composer_json": False,
    "composer_lock": False,
    "composer_lock_hash": None,
    "composer_validate_status": "NOT_RUN",
    "composer_install": "NOT_RUN",
    "composer_install_duration_seconds": None,
    "environment_preparation": "NOT_RUN",
    "database_preparation": "NOT_RUN",
    "test_discovery": "NOT_RUN",
    "test_execution": "NOT_RUN",
    "test_exit_code": None,
    "tests_total": None,
    "tests_passed": None,
    "tests_failed": None,
    "tests_skipped": None,
    "tests_incomplete": None,
    "failure_category": "NONE",
    "failure_stage": "NONE",
    "failure_detail": "",
    "failure_command": "",
    "failure_exit_code": None,
    "failure_duration_seconds": None,
    "execution_validity": "VALID",
    "reproducibility_status": "FAILED",
    "attempt": os.environ.get("STAGE4_ATTEMPT", "1"),
    "started_at": started_at.isoformat(),
    "finished_at": None,
    "duration_seconds": None,
}

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def now():
    return datetime.now(timezone.utc).isoformat()

def save_step_log(name, command, rc, duration, output):
    text = (
        "=" * 72 + "\n"
        f"STEP: {name}\n"
        f"TIMESTAMP: {now()}\n"
        f"COMMAND: {command}\n"
        f"EXIT_CODE: {rc}\n"
        f"DURATION_SECONDS: {duration:.3f}\n"
        + "=" * 72 + "\n\n"
        + (output or "")
    )
    (LOGDIR / f"{name}.log").write_text(text, encoding="utf-8", errors="replace")

def run(cmd, cwd=None, timeout=1800, shell=True, step=None):
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = p.stdout or ""
        dur = time.time() - t0
        if step:
            save_step_log(step, cmd, p.returncode, dur, out)
        return p.returncode, out, dur
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        out += "\nTIMEOUT\n"
        dur = time.time() - t0
        if step:
            save_step_log(step, cmd, 124, dur, out)
        return 124, out, dur
    except Exception as e:
        out = f"EXCEPTION: {repr(e)}\n"
        dur = time.time() - t0
        if step:
            save_step_log(step, cmd, 1, dur, out)
        return 1, out, dur

def set_failure(
    category,
    stage,
    detail,
    valid=True,
    command="",
    exit_code=None,
    duration_seconds=None,
):
    result["failure_category"] = category
    result["failure_stage"] = stage
    result["failure_detail"] = detail[-12000:]
    result["failure_command"] = command
    result["failure_exit_code"] = exit_code
    result["failure_duration_seconds"] = duration_seconds

    if not valid:
        result["execution_validity"] = "INVALID_INFRASTRUCTURE"

def capture_diag():
    commands = {
        "php_version.txt": "php --version",
        "composer_version.txt": "composer --version",
        "git_version.txt": "git --version",
        "node_version.txt": "node --version",
    }
    for filename, cmd in commands.items():
        rc, out, _ = run(cmd, timeout=60)
        (DIAGDIR / filename).write_text(out, encoding="utf-8", errors="replace")
        if filename == "php_version.txt":
            m = re.search(r"PHP\s+(\d+\.\d+\.\d+)", out)
            if m:
                result["php_version_actual"] = m.group(1)
        elif filename == "composer_version.txt":
            m = re.search(r"Composer version\s+([^\s]+)", out, re.I)
            result["composer_version"] = m.group(1) if m else out.strip().splitlines()[0] if out.strip() else None
        elif filename == "git_version.txt":
            result["git_version"] = out.strip().splitlines()[0] if out.strip() else None
        elif filename == "node_version.txt":
            result["node_version"] = out.strip().splitlines()[0] if out.strip() else None

    osinfo = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "runner": RUNNER,
        "github_os": OS_NAME,
    }
    write_json(DIAGDIR / "os_info.json", osinfo)
    write_json(ARTIFACT / "environment.json", {
        **osinfo,
        "php_runtime_requested": PHP_RUNTIME,
        "php_version_actual": result["php_version_actual"],
        "composer_version": result["composer_version"],
        "git_version": result["git_version"],
        "node_version": result["node_version"],
    })

def extract_test_counts(output):
    patterns = {
        "tests_total": [
            r"Tests:\s+(\d+)",
            r"(\d+)\s+tests?\b",
        ],
        "tests_failed": [r"(\d+)\s+fail(?:ed|ures?)\b", r"Failures:\s+(\d+)"],
        "tests_skipped": [r"(\d+)\s+skipped\b"],
        "tests_incomplete": [r"(\d+)\s+incomplete\b"],
    }
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, output, re.I)
            if m:
                result[key] = int(m.group(1))
                break
    if result["tests_total"] is not None and result["tests_failed"] is not None:
        result["tests_passed"] = max(
            0,
            result["tests_total"]
            - (result["tests_failed"] or 0)
            - (result["tests_skipped"] or 0)
            - (result["tests_incomplete"] or 0),
        )

def classify_failure(output, stage):
    low = output.lower()
    if "repository not found" in low or "could not read from remote repository" in low:
        return "REPOSITORY", "CLONE"
    if "could not resolve host" in low or "connection timed out" in low or "remote end closed" in low:
        return "INFRASTRUCTURE", stage
    if "requires php" in low or "platform requirement" in low or "your php version" in low:
        return "PHP_VERSION_DEPENDENCY_MISMATCH", stage
    if "requires ext-" in low or "extension" in low and "missing" in low:
        return "EXTENSION_MISSING", stage
    if "lock file does not contain a compatible set" in low:
        return "LOCKFILE_PHP_VERSION_MISMATCH", stage
    if "sqlstate" in low or "connection refused" in low or "could not connect" in low:
        return "DATABASE_FAILURE", stage
    if "permission denied" in low or "access is denied" in low:
        return "PERMISSION_FAILURE", stage
    if "no such file or directory" in low or "cannot find the path" in low:
        return "FILESYSTEM_FAILURE", stage
    if "command not found" in low or "is not recognized as an internal or external command" in low:
        return "TEST_COMMAND_UNAVAILABLE", stage
    if "timeout" in low:
        return "TEST_TIMEOUT", stage
    return "TEST_EXECUTION_FAILURE" if stage == "TEST_EXECUTION" else "COMPOSER_FAILURE", stage

def main():
    capture_diag()

    write_json(ARTIFACT / "repository.json", {
        "repo_full_name": REPO,
        "url": URL,
        "latest_sha": SHA,
        "project_id": PROJECT_ID,
        "default_branch": os.environ.get("STAGE4_BRANCH", ""),
    })
    write_json(ARTIFACT / "metadata.json", {
        "execution_id": EXECUTION_ID,
        "execution_owner": OWNER,
        "execution_batch": BATCH,
        "stars_github": STARS,
        "forks_count": FORKS,
        "popularity_quartile": POPULARITY_QUARTILE,
        "docker_status": DOCKER_STATUS,
        "php_version_constraint": os.environ.get("STAGE4_PHP_CONSTRAINT", ""),
        "php_runtime_source": os.environ.get("STAGE4_PHP_SOURCE", ""),
    })

    rc, out, _ = run(
        f'git clone --no-tags --depth 1 "{URL}" "{TARGET}"',
        timeout=600,
        step="clone",
    )
    if rc != 0:
        set_failure(*classify_failure(out, "CLONE"), valid=False)
        return finish()

    result["clone_status"] = "PASS"

    rc, out, _ = run(
        f'git fetch --depth 1 origin {SHA}',
        cwd=TARGET,
        timeout=600,
        step="checkout",
    )
    if rc != 0:
        set_failure(*classify_failure(out, "CHECKOUT"), valid=False)
        return finish()

    rc, out, _ = run(
        f'git checkout --detach {SHA}',
        cwd=TARGET,
        timeout=300,
        step="checkout_detach",
    )
    if rc != 0:
        set_failure(*classify_failure(out, "CHECKOUT"), valid=False)
        return finish()

    result["checkout_status"] = "PASS"

    composer_json = TARGET / "composer.json"
    composer_lock = TARGET / "composer.lock"
    result["composer_json"] = composer_json.exists()
    result["composer_lock"] = composer_lock.exists()

    if composer_lock.exists():
        import hashlib
        result["composer_lock_hash"] = hashlib.sha256(
            composer_lock.read_bytes()
        ).hexdigest()

    if not composer_json.exists():
        set_failure("COMPOSER_FAILURE", "COMPOSER_INSTALL",
                    "composer.json was not found after checkout.")
        return finish()

    rc, out, _ = run("composer validate --no-check-publish",
                     cwd=TARGET, timeout=300, step="composer_validate")
    result["composer_validate_status"] = "PASS" if rc == 0 else "FAIL"
    if rc != 0:
        set_failure(*classify_failure(out, "COMPOSER_VALIDATE"))

    t0 = time.time()
    rc, out, dur = run(
        "composer install --no-interaction --prefer-dist --no-progress --optimize-autoloader",
        cwd=TARGET, timeout=1800, step="composer_install",
    )
    result["composer_install_duration_seconds"] = round(dur, 3)
    if rc != 0:
        result["composer_install"] = "FAIL"

        composer_command = (
            "composer install --no-interaction "
            "--prefer-dist --no-progress --optimize-autoloader"
        )

        cat, stage = classify_failure(
            out,
            "COMPOSER_INSTALL"
        )

        set_failure(
            cat,
            stage,
            out,
            command=composer_command,
            exit_code=rc,
            duration_seconds=dur,
        )

        (ERRDIR / "composer_error.log").write_text(
            out,
            encoding="utf-8",
            errors="replace"
        )

        return finish()
    result["composer_install"] = "PASS"

    env = TARGET / ".env"
    env_example = TARGET / ".env.example"
    prep = []
    if not env.exists() and env_example.exists():
        env.write_text(env_example.read_text(encoding="utf-8", errors="replace"),
                       encoding="utf-8")
        prep.append(".env created from .env.example")

    artisan = TARGET / "artisan"
    if artisan.exists():
        rc, out, _ = run("php artisan key:generate --force",
                         cwd=TARGET, timeout=300, step="environment")
        if rc != 0:
            result["environment_preparation"] = "FAIL"
            (ERRDIR / "artisan_error.log").write_text(out, encoding="utf-8", errors="replace")
            set_failure("APPLICATION_CONFIGURATION", "TEST_ENVIRONMENT_PREPARATION", out)
            return finish()
        prep.append("APP_KEY generated")
        run("php artisan config:clear", cwd=TARGET, timeout=300, step="environment_config_clear")
        prep.append("Laravel config cleared")
    result["environment_preparation"] = "; ".join(prep) if prep else "No environment preparation required"

    result["database_preparation"] = "Repository database configuration preserved"
    (LOGDIR / "database.log").write_text(
        "No database configuration was silently replaced by the protocol.\n",
        encoding="utf-8",
    )

    # Lightweight framework/test discovery evidence.
    test_dir = TARGET / "tests"
    phpunit = TARGET / "phpunit.xml"
    phpunit_dist = TARGET / "phpunit.xml.dist"
    composer_data = json.loads(composer_json.read_text(encoding="utf-8"))
    dev = composer_data.get("require-dev", {})
    if "pestphp/pest" in dev:
        result["test_framework"] = "Pest"
    elif "phpunit/phpunit" in dev:
        result["test_framework"] = "PHPUnit"

    if TEST_COMMAND:
        command = TEST_COMMAND
        result["test_discovery"] = "Assignment command"
    elif artisan.exists():
        command = "php artisan test"
        result["test_discovery"] = "Fallback: php artisan test"
    elif (TARGET / "vendor/bin/phpunit").exists():
        command = "vendor/bin/phpunit"
        result["test_discovery"] = "Fallback: vendor/bin/phpunit"
    else:
        command = ""
        result["test_discovery"] = "NO_TEST_COMMAND"

    (LOGDIR / "test_discovery.log").write_text(
        json.dumps({
            "tests_directory": test_dir.is_dir(),
            "phpunit_config": phpunit.exists() or phpunit_dist.exists(),
            "test_framework": result["test_framework"],
            "selected_command": command,
        }, indent=2),
        encoding="utf-8",
    )

    if not command:
        set_failure("TEST_COMMAND_UNAVAILABLE", "TEST_DISCOVERY",
                    "No executable test command was discovered.")
        return finish()

    result["test_command"] = command

    rc, out, dur = run(command, cwd=TARGET, timeout=1800, step="test_execution")
    result["test_exit_code"] = rc
    extract_test_counts(out)

    if rc == 0:
        result["test_execution"] = "PASS"
        result["reproducibility_status"] = "REPRODUCIBLE"
    else:
        result["test_execution"] = "FAIL"

        cat, stage = classify_failure(
            out,
            "TEST_EXECUTION"
        )

        set_failure(
            cat,
            stage,
            out,
            command=command,
            exit_code=rc,
            duration_seconds=dur,
        )

        (ERRDIR / "test_error.log").write_text(
            out,
            encoding="utf-8",
            errors="replace"
        )

    finish()

def finish():
    finished = datetime.now(timezone.utc)
    result["finished_at"] = finished.isoformat()
    result["duration_seconds"] = round(
        (finished - started_at).total_seconds(), 3
    )

    raw = result.get("failure_detail", "")
    if raw:
        (ERRDIR / "raw_error.log").write_text(raw, encoding="utf-8", errors="replace")

    write_json(ARTIFACT / "result.json", result)

    # ------------------------------------------------------------
    # Artifact completeness audit
    # ------------------------------------------------------------

    required_artifacts = [
        ARTIFACT / "result.json",
        ARTIFACT / "environment.json",
        DIAGDIR / "php_version.txt",
        DIAGDIR / "composer_version.txt",
        DIAGDIR / "git_version.txt",
        DIAGDIR / "node_version.txt",
    ]

    missing_artifacts = [
        str(x)
        for x in required_artifacts
        if not x.exists()
    ]

    result["artifact_completeness"] = {
        "required_files": [
            str(x)
            for x in required_artifacts
        ],
        "missing_files": missing_artifacts,
        "complete": len(missing_artifacts) == 0,
    }

    # Rewrite result.json after completeness information is added.
    write_json(ARTIFACT / "result.json", result)

    llm_bundle = {
        "schema_version": "stage4-llm-v2",
        "repository": {
            "project_id": PROJECT_ID,
            "repo_full_name": REPO,
            "url": URL,
            "sha": SHA,
        },
        "sampling": {
            "stars": STARS,
            "forks": FORKS,
            "popularity_quartile": POPULARITY_QUARTILE,
            "docker_status": DOCKER_STATUS,
        },
        "environment": {
            "os": OS_NAME,
            "runner": RUNNER,
            "php_requested": PHP_RUNTIME,
            "php_constraint": result["php_runtime_constraint"],
            "php_source": result["php_runtime_source"],
            "php_resolution": result["php_runtime_resolution"],
            "php_confidence": result["php_runtime_confidence"],
            "php_actual": result["php_version_actual"],
            "composer": result["composer_version"],
        },
        "execution": {
            "command": result["test_command"],
            "exit_code": result["test_exit_code"],
            "status": result["reproducibility_status"],
            "failure_category": result["failure_category"],
            "failure_stage": result["failure_stage"],
            "failure_command": result["failure_command"],
            "failure_exit_code": result["failure_exit_code"],
            "failure_duration_seconds": result["failure_duration_seconds"],
        },
        "evidence": {
            "failure_detail": result["failure_detail"],
            "raw_error": raw,
            "artifact_completeness": result["artifact_completeness"],
        },
    }
    write_json(LLMDIR / "execution_bundle.json", llm_bundle)
    write_json(LLMDIR / "error_bundle.json", {
        "repo_full_name": REPO,
        "sha": SHA,
        "os": OS_NAME,
        "failure_category": result["failure_category"],
        "failure_stage": result["failure_stage"],
        "failure_detail": result["failure_detail"],
        "test_exit_code": result["test_exit_code"],
    })

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
