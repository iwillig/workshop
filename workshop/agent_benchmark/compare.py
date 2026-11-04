"""Compare two stored reports of the same suite version."""

from workshop.agent_eval.contracts import RunResult
from workshop.agent_eval.reviews import load_report


def compare_reports(storage_root, run_id_a, run_id_b):
    """Return structured differences; never an overall quality verdict."""
    if run_id_a == run_id_b:
        raise ValueError("Select two different runs to compare")
    report_a = load_report(storage_root, run_id_a)
    report_b = load_report(storage_root, run_id_b)
    run_a = RunResult.model_validate(report_a["run"])
    run_b = RunResult.model_validate(report_b["run"])
    if run_a.suite_id != run_b.suite_id:
        raise ValueError("Runs used different suites")
    if run_a.suite_sha256 != run_b.suite_sha256:
        raise ValueError(
            "Runs used different versions of the same suite; compare only "
            "identical suite versions"
        )

    def summary(report, run):
        return {
            "id": run.id,
            "agent_id": run.agent_id,
            "model": report.get("model"),
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "cost": run.cost,
            "counts": report["counts"],
            "review_counts": report.get("review_counts"),
        }

    cases_a = {
        (case.case_id, case.case_version): case for case in run_a.results
    }
    cases_b = {
        (case.case_id, case.case_version): case for case in run_b.results
    }
    cases = []
    for key in sorted(set(cases_a) | set(cases_b), key=lambda item: item[0]):
        case_a, case_b = cases_a.get(key), cases_b.get(key)
        outcome_a = case_a.outcome.value if case_a else None
        outcome_b = case_b.outcome.value if case_b else None
        cases.append(
            {
                "case_id": key[0],
                "case_version": key[1],
                "outcome_a": outcome_a,
                "outcome_b": outcome_b,
                "changed": outcome_a != outcome_b,
                "diagnostic_a": case_a.diagnostic if case_a else None,
                "diagnostic_b": case_b.diagnostic if case_b else None,
            }
        )
    return {
        "suite": {
            "id": run_a.suite_id,
            "version": run_a.suite_version,
            "sha256": run_a.suite_sha256,
        },
        "runs": {"a": summary(report_a, run_a), "b": summary(report_b, run_b)},
        "cases": cases,
        "changed_cases": sum(1 for case in cases if case["changed"]),
    }
