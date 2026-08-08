from pathlib import Path

import pytest

from scripts.check_phase0_junit import Phase0GateError, validate_phase0_reports


def write_junit(path: Path, *, tests: int, failures: int = 0, errors: int = 0,
                skipped: int = 0, xfails: int = 0) -> None:
    skipped_nodes = "".join(
        '<testcase name="xfail"><skipped type="pytest.xfail" /></testcase>'
        for _ in range(xfails)
    )
    skipped_nodes += "".join(
        '<testcase name="skip"><skipped type="pytest.skip" /></testcase>'
        for _ in range(skipped - xfails)
    )
    passing_nodes = "".join(
        '<testcase name="pass" />' for _ in range(tests - skipped - failures - errors)
    )
    path.write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}">'
        f"{passing_nodes}{skipped_nodes}</testsuite></testsuites>"
    )


def test_gate_accepts_zero_skip_normal_and_exactly_four_xfails(tmp_path):
    normal = tmp_path / "normal.xml"
    defects = tmp_path / "defects.xml"
    write_junit(normal, tests=23)
    write_junit(defects, tests=4, skipped=4, xfails=4)

    summary = validate_phase0_reports(normal, defects)

    assert summary == {
        "normal": {"tests": 23, "failures": 0, "errors": 0, "skips": 0},
        "known_defects": {
            "tests": 4,
            "failures": 0,
            "errors": 0,
            "xfails": 4,
            "ordinary_skips": 0,
        },
    }


@pytest.mark.parametrize(
    ("normal_values", "defect_values", "message"),
    [
        ({"tests": 23, "skipped": 1}, {"tests": 4, "skipped": 4, "xfails": 4}, "normal suite"),
        ({"tests": 23}, {"tests": 3, "skipped": 3, "xfails": 3}, "exactly 4"),
        ({"tests": 23}, {"tests": 4, "skipped": 4, "xfails": 3}, "ordinary skips"),
        ({"tests": 23}, {"tests": 4, "failures": 1, "skipped": 3, "xfails": 3}, "known-defect suite"),
    ],
)
def test_gate_rejects_non_phase0_outcome_counts(
    tmp_path, normal_values, defect_values, message
):
    normal = tmp_path / "normal.xml"
    defects = tmp_path / "defects.xml"
    write_junit(normal, **normal_values)
    write_junit(defects, **defect_values)

    with pytest.raises(Phase0GateError, match=message):
        validate_phase0_reports(normal, defects)
