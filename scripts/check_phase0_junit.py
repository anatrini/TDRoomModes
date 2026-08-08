#!/usr/bin/env python3
"""Fail-closed validation of the two Phase 0 pytest JUnit reports."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET


class Phase0GateError(RuntimeError):
    """Raised when pytest outcomes do not match the Phase 0 gate contract."""


def _suite_totals(path: Path) -> tuple[dict[str, int], int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Phase0GateError(f"no testsuite found in {path}")

    totals = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    xfails = sum(
        1
        for suite in suites
        for skipped in suite.findall(".//testcase/skipped")
        if skipped.attrib.get("type") == "pytest.xfail"
    )
    return totals, xfails


def validate_phase0_reports(normal_path: Path, defect_path: Path) -> dict:
    normal, normal_xfails = _suite_totals(normal_path)
    defects, defect_xfails = _suite_totals(defect_path)

    if normal["tests"] < 1:
        raise Phase0GateError("normal suite collected no tests")
    if any(normal[key] for key in ("failures", "errors", "skipped")):
        raise Phase0GateError(
            "normal suite must have zero failures, errors, and skips: "
            f"{normal}"
        )
    if normal_xfails:
        raise Phase0GateError("normal suite unexpectedly reported xfails")

    if defects["tests"] != 4:
        raise Phase0GateError(
            f"known-defect suite must collect exactly 4 tests: {defects}"
        )
    if defects["failures"] or defects["errors"]:
        raise Phase0GateError(
            f"known-defect suite has failures or errors: {defects}"
        )
    ordinary_skips = defects["skipped"] - defect_xfails
    if ordinary_skips:
        raise Phase0GateError(
            f"known-defect suite has {ordinary_skips} ordinary skips"
        )
    if defect_xfails != 4:
        raise Phase0GateError(
            f"known-defect suite must report exactly 4 xfails, got {defect_xfails}"
        )

    return {
        "normal": {
            "tests": normal["tests"],
            "failures": normal["failures"],
            "errors": normal["errors"],
            "skips": normal["skipped"],
        },
        "known_defects": {
            "tests": defects["tests"],
            "failures": defects["failures"],
            "errors": defects["errors"],
            "xfails": defect_xfails,
            "ordinary_skips": ordinary_skips,
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} NORMAL.xml KNOWN_DEFECTS.xml", file=sys.stderr)
        return 2
    try:
        summary = validate_phase0_reports(Path(argv[1]), Path(argv[2]))
    except (OSError, ET.ParseError, Phase0GateError) as exc:
        print(f"PHASE0_GATE_FAILED: {exc}", file=sys.stderr)
        return 1

    normal = summary["normal"]
    defects = summary["known_defects"]
    print(
        "PHASE0_GATE_OK: "
        f"normal={normal['tests']} passed, 0 skipped/failed/errors; "
        f"known_defects={defects['tests']} collected, "
        f"{defects['xfails']} xfailed, 0 ordinary skips/failed/errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
