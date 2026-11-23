'''M3 时间注入回归：pytest 入口'''
import pytest

from evals.cases.time_cases import TIME_CASES
from evals.runners.graph_runner import assert_expect, run_case


@pytest.mark.parametrize("case", TIME_CASES, ids=[case["id"] for case in TIME_CASES])
def test_time_case(case):
    result = run_case(case)
    assert_expect(result, case["expect"])
