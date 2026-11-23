'''M5 流式契约回归：pytest 入口'''
import pytest

from evals.cases.stream_cases import STREAM_CASES
from evals.runners.graph_runner import assert_expect, run_case


@pytest.mark.parametrize(
    "case", STREAM_CASES, ids=[case["id"] for case in STREAM_CASES]
)
def test_stream_case(case):
    result = run_case(case)
    assert_expect(result, case["expect"])
