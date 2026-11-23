'''M6 记忆回归：pytest 入口'''
import pytest

from evals.cases.memory_cases import MEMORY_CASES
from evals.runners.graph_runner import assert_expect, run_memory_case


@pytest.mark.parametrize(
    "case", MEMORY_CASES, ids=[case["id"] for case in MEMORY_CASES]
)
def test_memory_case(case, tmp_path):
    result = run_memory_case(case, str(tmp_path / "history.json"))
    assert_expect(result, case["expect"])
