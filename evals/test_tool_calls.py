'''M1 工具正确性回归：pytest 入口'''
import pytest

from evals.cases.tool_cases import TOOL_CASES
from evals.runners.graph_runner import assert_expect, run_case


@pytest.mark.parametrize("case", TOOL_CASES, ids=[case["id"] for case in TOOL_CASES])
def test_tool_case(case):
    result = run_case(case)
    assert_expect(result, case["expect"])
