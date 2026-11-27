'''M2 路由回归：pytest 入口'''
import pytest

from evals.cases.routing_cases import ROUTING_CASES
from evals.runners.graph_runner import run_with_retry


@pytest.mark.parametrize("case", ROUTING_CASES, ids=[case["id"] for case in ROUTING_CASES])
def test_routing_case(case):
    run_with_retry(case)
