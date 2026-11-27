'''评测报告：pytest 钩子收集结果并写出 JSON 摘要'''
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_PATH = REPORT_DIR / "latest.json"

_RESULTS: dict[str, dict] = {}
_RECORDED: set[str] = set()
# 用例实际重试次数（由 runners 写入），用于让非确定性用例暴露出来
_RETRY_COUNTS: dict[str, int] = {}


def record_retry(case_id: str, count: int) -> None:
    '''记录一条用例的实际重试次数'''
    _RETRY_COUNTS[case_id] = count


def get_retry_count(case_id: str) -> int:
    '''读取一条用例的实际重试次数；未记录时为 0'''
    return _RETRY_COUNTS.get(case_id, 0)


def record_report(nodeid: str, case: dict, report) -> None:
    '''记录一条用例结果；同一 nodeid 只记录一次'''
    if nodeid in _RECORDED:
        return
    _RECORDED.add(nodeid)

    outcome = "passed"
    if report.failed:
        outcome = "failed"
    elif report.skipped:
        outcome = "skipped"

    failure = ""
    if report.failed:
        failure = str(getattr(report, "longreprtext", ""))[:2000]

    _RESULTS[nodeid] = {
        "id": case.get("id", nodeid),
        "category": case.get("category", "unknown"),
        "description": case.get("description", ""),
        "outcome": outcome,
        "passed": outcome == "passed",
        "duration_ms": round(report.duration * 1000, 1),
        "retry_count": get_retry_count(case.get("id", nodeid)),
        "failure": failure,
    }


def write_report() -> None:
    '''写 evals/reports/latest.json；没有用例结果时不生成'''
    if not _RESULTS:
        return
    items = sorted(_RESULTS.values(), key=lambda item: item["id"])
    by_category = Counter(item["category"] for item in items)
    passed = sum(1 for item in items if item["outcome"] == "passed")
    slowest = sorted(items, key=lambda item: item["duration_ms"], reverse=True)[:5]
    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(items),
        "passed": passed,
        "failed": sum(1 for item in items if item["outcome"] == "failed"),
        "skipped": sum(1 for item in items if item["outcome"] == "skipped"),
        "pass_rate": round(passed * 100 / len(items), 1),
        "by_category": dict(sorted(by_category.items())),
        "total_retries": sum(item["retry_count"] for item in items),
        "retried_cases": [item["id"] for item in items if item["retry_count"] > 0],
        "slowest": [
            {
                "id": item["id"],
                "category": item["category"],
                "duration_ms": item["duration_ms"],
            }
            for item in slowest
        ],
        "cases": items,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
