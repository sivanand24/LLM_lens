import logging

from checks.rules import (
    check_empty,
    check_error,
    check_format,
    check_latency,
    check_length,
    check_pii,
    check_refusal,
    check_truncation,
)

log = logging.getLogger(__name__)

CHECKS = [
    check_error, check_empty, check_refusal, check_truncation,
    check_format, check_length, check_latency, check_pii,
]

SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def run_checks(call: dict, ctx: dict) -> dict:
    """Run every check. Returns {flags, severity, is_failure} for the call document."""
    flags = []
    for check in CHECKS:
        try:
            flag = check(call, ctx)
        except Exception:
            # One broken check must not hide the others.
            log.exception("check %s failed on %s", check.__name__, call.get("request_id"))
            continue
        if flag:
            flags.append(flag)

    severity = max((f["severity"] for f in flags), key=SEVERITY_RANK.__getitem__, default="none")
    is_failure = call.get("status") != "success" or severity == "high"
    return {"flags": flags, "severity": severity, "is_failure": is_failure}
