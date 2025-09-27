# ──────────────────────────────────────────────────────────────────────────────
# File: utils/env_audit.py
# Purpose: Comprehensive environment variable audit for Relay pipeline
#
# Validates:
#   • Required environment variables for each service
#   • API key presence and format validation
#   • Database connection strings
#   • Service endpoint configurations
#   • Critical path dependencies
# ──────────────────────────────────────────────────────────────────────────────

import os
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


def validate_api_key(key: Optional[str], name: str) -> Tuple[bool, str]:
    """Validate API key format and presence."""
    if not key:
        return False, f"{name} is missing"

    if len(key.strip()) < 8:
        return False, f"{name} is too short (< 8 chars)"

    # Check for common placeholder values
    if key.lower() in {"your_key_here", "replace_me", "example", "test"}:
        return False, f"{name} appears to be a placeholder"

    return True, "valid"


def validate_url(url: Optional[str], name: str) -> Tuple[bool, str]:
    """Validate URL format."""
    if not url:
        return False, f"{name} is missing"

    if not re.match(r'^https?://', url):
        return False, f"{name} must start with http:// or https://"

    return True, "valid"


def validate_database_url(url: Optional[str], name: str) -> Tuple[bool, str]:
    """Validate PostgreSQL connection string."""
    if not url:
        return False, f"{name} is missing"

    # Check for PostgreSQL URL format
    if not any(url.startswith(prefix) for prefix in ["postgres://", "postgresql://"]):
        # Check for individual components
        required_components = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"]
        missing = [comp for comp in required_components if not os.getenv(comp)]
        if missing:
            return False, f"{name} URL or components missing: {missing}"

    return True, "valid"


def audit_environment() -> Dict[str, Any]:
    """Perform comprehensive environment audit."""

    results = {
        "status": "unknown",
        "critical_issues": [],
        "warnings": [],
        "validated": {},
        "summary": {}
    }

    # Critical API Keys
    critical_keys = {
        "OPENAI_API_KEY": "OpenAI API access",
        "API_KEY": "Relay authentication",
        "RELAY_API_KEY": "Relay internal auth"
    }

    for key_name, description in critical_keys.items():
        key_value = os.getenv(key_name)
        is_valid, message = validate_api_key(key_value, key_name)

        results["validated"][key_name] = {
            "present": key_value is not None,
            "valid": is_valid,
            "message": message,
            "description": description
        }

        if not is_valid:
            results["critical_issues"].append(f"{key_name}: {message}")

    # Service URLs
    service_urls = {
        "RELAY_URL": "Relay backend URL",
        "NEXT_PUBLIC_API_URL": "Frontend API URL",
        "FRONTEND_ORIGIN": "CORS frontend origin"
    }

    for url_name, description in service_urls.items():
        url_value = os.getenv(url_name)
        is_valid, message = validate_url(url_value, url_name)

        results["validated"][url_name] = {
            "present": url_value is not None,
            "valid": is_valid,
            "message": message,
            "description": description
        }

        if not is_valid and url_name in ["RELAY_URL", "NEXT_PUBLIC_API_URL"]:
            results["critical_issues"].append(f"{url_name}: {message}")
        elif not is_valid:
            results["warnings"].append(f"{url_name}: {message}")

    # Database Configuration
    db_url = os.getenv("DATABASE_URL")
    is_valid, message = validate_database_url(db_url, "DATABASE_URL")

    results["validated"]["DATABASE_URL"] = {
        "present": db_url is not None,
        "valid": is_valid,
        "message": message,
        "description": "PostgreSQL database connection"
    }

    if not is_valid:
        results["warnings"].append(f"DATABASE_URL: {message}")

    # LlamaIndex/Context Engine Configuration
    context_vars = {
        "KB_EMBED_MODEL": "Knowledge base embedding model",
        "INDEX_ROOT": "Search index root directory",
        "TOPK_GLOBAL": "Global retrieval count",
        "RERANK_MIN_SCORE_GLOBAL": "Global rerank threshold"
    }

    for var_name, description in context_vars.items():
        var_value = os.getenv(var_name)
        results["validated"][var_name] = {
            "present": var_value is not None,
            "value": var_value,
            "description": description
        }

        if not var_value:
            results["warnings"].append(f"{var_name}: missing (using defaults)")

    # File Path Validation
    index_root = Path(os.getenv("INDEX_ROOT", "./data/index"))
    try:
        index_root.mkdir(parents=True, exist_ok=True)
        test_file = index_root / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        index_writable = True
    except Exception:
        index_writable = False

    results["validated"]["INDEX_ROOT_WRITABLE"] = {
        "present": True,
        "valid": index_writable,
        "message": "writable" if index_writable else "not writable",
        "description": "Index directory write permissions"
    }

    if not index_writable:
        results["critical_issues"].append("INDEX_ROOT: directory not writable")

    # Summary
    critical_count = len(results["critical_issues"])
    warning_count = len(results["warnings"])

    if critical_count > 0:
        results["status"] = "critical"
    elif warning_count > 0:
        results["status"] = "warnings"
    else:
        results["status"] = "healthy"

    results["summary"] = {
        "status": results["status"],
        "critical_issues": critical_count,
        "warnings": warning_count,
        "total_validated": len(results["validated"])
    }

    return results


def print_audit_report():
    """Print human-readable audit report."""
    audit = audit_environment()

    print(f"🔍 Environment Audit Report")
    print(f"Status: {audit['status'].upper()}")
    print(f"Critical Issues: {audit['summary']['critical_issues']}")
    print(f"Warnings: {audit['summary']['warnings']}")
    print()

    if audit["critical_issues"]:
        print("❌ CRITICAL ISSUES:")
        for issue in audit["critical_issues"]:
            print(f"   • {issue}")
        print()

    if audit["warnings"]:
        print("⚠️  WARNINGS:")
        for warning in audit["warnings"]:
            print(f"   • {warning}")
        print()

    print("📋 VALIDATION DETAILS:")
    for var_name, details in audit["validated"].items():
        status = "✅" if details.get("valid", details["present"]) else "❌"
        message = details.get("message", details.get("description", "no message"))
        print(f"   {status} {var_name}: {message}")

    return audit


if __name__ == "__main__":
    print_audit_report()