'''M4 容错回归：pytest 入口'''
import pytest

from evals.cases.resilience_cases import RESILIENCE_CASES
from evals.runners.graph_runner import assert_expect, run_case


@pytest.mark.parametrize(
    "case", RESILIENCE_CASES, ids=[case["id"] for case in RESILIENCE_CASES]
)
def test_resilience_case(case):
    result = run_case(case)
    assert_expect(result, case["expect"])
