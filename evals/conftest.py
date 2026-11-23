'''评测全局配置：隔离 MCP、收集报告'''
import pytest

from evals.reporting import record_report, write_report


@pytest.fixture(autouse=True)
def isolate_mcp(monkeypatch, tmp_path):
    '''确定性评测不加载真实 MCP 配置，避免网络与外部进程'''
    monkeypatch.setenv("MCP_CONFIG_PATH", str(tmp_path / "missing_mcp.json"))
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when not in ("setup", "call"):
        return

    case = getattr(getattr(item, "callspec", None), "params", {}).get("case")
    if not isinstance(case, dict):
        return
    if report.when == "setup" and not (report.failed or report.skipped):
        return

    record_report(item.nodeid, case, report)


def pytest_sessionfinish(session, exitstatus):
    write_report()
