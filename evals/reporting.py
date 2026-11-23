'''评测报告：pytest 钩子收集结果并写出 JSON 摘要'''
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_PATH = REPORT_DIR / "latest.json"

_RESULTS: dict[str, dict] = {}
_RECORDED: set[str] = set()


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
        "failure": failure,
    }


def write_report() -> None:
    '''写 evals/reports/latest.json；没有用例结果时不生成'''
    if not _RESULTS:
        return
    items = sorted(_RESULTS.values(), key=lambda item: item["id"])
    by_category = Counter(item["category"] for item in items)
    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(items),
        "passed": sum(1 for item in items if item["outcome"] == "passed"),
        "failed": sum(1 for item in items if item["outcome"] == "failed"),
        "skipped": sum(1 for item in items if item["outcome"] == "skipped"),
        "by_category": dict(sorted(by_category.items())),
        "cases": items,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
