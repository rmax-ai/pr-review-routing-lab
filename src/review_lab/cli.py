"""Argparse command line interface for the offline routing lab."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .calibration import calibrate, sweep
from .corpus import (
    CaseLoadError,
    PrivateOverlayError,
    gold_warnings,
    load_case,
    load_cases,
    load_gold,
    scan_paths,
)
from .costing import model_scenarios
from .digests import case_digest, digest_obj
from .gates.deterministic import run_deterministic_gates
from .gates.jev import JevAdapter
from .harnesses.codex import CodexHarness
from .harnesses.mock import MockHarness
from .models import HarnessId
from .question_sets import CANONICAL_QUESTION_IDS
from .report import build_report, load_records
from .runner import PacketBuilder, Runner
from .util import canonical_bytes, is_path_under, read_yaml, write_json


def _add_output(parser: argparse.ArgumentParser, default: str = "runs") -> None:
    parser.add_argument("--out", "--output", dest="out", default=default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review-lab")
    sub = parser.add_subparsers(dest="command", required=True)

    cases = sub.add_parser("cases")
    case_sub = cases.add_subparsers(dest="action", required=True)
    validate = case_sub.add_parser("validate")
    validate.add_argument("directory", nargs="?")
    validate.add_argument("--root", dest="root")
    validate.add_argument("--public-only", action="store_true")
    scan = case_sub.add_parser("scan")
    scan.add_argument("directory", nargs="?")
    scan.add_argument("--root", dest="root")
    scan.add_argument("--public-only", action="store_true")

    experiment = sub.add_parser("experiment")
    experiment_sub = experiment.add_subparsers(dest="action", required=True)
    run = experiment_sub.add_parser("run")
    run.add_argument("--architectures", default="A0,A1,A2,A3,A4,A5,dual")
    run.add_argument("--cases", default="cases/public")
    run.add_argument("--split", choices=["train", "holdout", "all"], default="all")
    run.add_argument("--backend", choices=["mock", "live"], default="mock")
    run.add_argument("--allow-live", action="store_true")
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--public-only", action="store_true")
    _add_output(run)

    score = sub.add_parser("score")
    score.add_argument("--run", required=True)
    score.add_argument("--gold", required=True)
    score.add_argument("--out", "--output", dest="out")

    report = sub.add_parser("report")
    report_sub = report.add_subparsers(dest="action", required=True)
    build = report_sub.add_parser("build")
    build.add_argument("--run", required=True)
    build.add_argument("--gold")
    _add_output(build, "report.md")
    sweep_parser = report_sub.add_parser("sweep")
    sweep_parser.add_argument("--run", required=True)
    sweep_parser.add_argument("--gate", choices=["a", "b"], required=True)
    _add_output(sweep_parser, "sweep.csv")

    cost = sub.add_parser("cost")
    cost_sub = cost.add_subparsers(dest="action", required=True)
    model = cost_sub.add_parser("model")
    model.add_argument("--scenarios", required=True)
    _add_output(model, "")

    jev = sub.add_parser("jev")
    jev_sub = jev.add_subparsers(dest="action", required=True)
    evaluate = jev_sub.add_parser("evaluate")
    evaluate.add_argument("--question-set", choices=["gate-a", "gate-b"], required=True)
    source = evaluate.add_mutually_exclusive_group(required=True)
    source.add_argument("--case")
    source.add_argument("--input")
    backend = evaluate.add_mutually_exclusive_group()
    backend.add_argument("--mock", action="store_true")
    backend.add_argument("--live", action="store_true")
    evaluate.add_argument("--allow-live", action="store_true")

    reviewer = sub.add_parser("reviewer")
    reviewer_sub = reviewer.add_subparsers(dest="action", required=True)
    review_run = reviewer_sub.add_parser("run")
    review_run.add_argument(
        "--harness", choices=["codex", "mock_codex", "mock_droid"], required=True
    )
    review_run.add_argument("--model", default="gpt-6-sol")
    review_run.add_argument("--effort", default="low")
    review_run.add_argument("--case", required=True)
    backend = review_run.add_mutually_exclusive_group()
    backend.add_argument("--mock", action="store_true")
    backend.add_argument("--live", action="store_true")
    review_run.add_argument("--allow-live", action="store_true")

    return parser


def _root(args: argparse.Namespace, default: str) -> str:
    return str(args.directory or args.root or default)


def _ensure_live(args: argparse.Namespace) -> None:
    if not args.allow_live:
        raise PrivateOverlayError("live backend requires --allow-live")
    if not os.environ.get("REVIEW_LAB_JEV_BIN"):
        raise PrivateOverlayError("live backend requires REVIEW_LAB_JEV_BIN")


def _ensure_experiment_live(args: argparse.Namespace) -> None:
    _ensure_live(args)
    if not os.environ.get("REVIEW_LAB_CODEX_CMD") and shutil.which("codex") is None:
        raise PrivateOverlayError("live experiment requires Codex command configuration")


def _ensure_reviewer_live(args: argparse.Namespace) -> None:
    if not args.allow_live:
        raise PrivateOverlayError("live reviewer requires --allow-live")
    if not os.environ.get("REVIEW_LAB_CODEX_CMD") and shutil.which("codex") is None:
        raise PrivateOverlayError("live reviewer requires Codex command configuration")


def _jev_questions(gate: str, *, mock: bool) -> dict[str, Any]:
    ids = sorted(CANONICAL_QUESTION_IDS[gate])
    if mock:
        return {
            "ok": True,
            "answers": [
                {
                    "id": question,
                    "type": "boolean",
                    "value": False,
                    "probabilities": {"true": 0.0, "false": 1.0},
                }
                for question in ids
            ],
            "usage": {},
        }
    return {
        "id": gate,
        "instructions": "Answer each narrow boolean independently.",
        "questions": [{"id": question, "type": "boolean"} for question in ids],
    }


def _run_cases(args: argparse.Namespace) -> int:
    if args.backend != "live" and args.allow_live:
        print("warning: --allow-live is unused with the mock backend", file=sys.stderr)
    if args.backend == "live":
        _ensure_experiment_live(args)
    cases = load_cases(args.cases, public_only=args.public_only)
    if args.split != "all":
        # The split is a workflow rehearsal.  Hashing the case ID keeps
        # membership stable when cases are added or removed.
        parity = 0 if args.split == "train" else 1
        cases = [case for case in cases if int(digest_obj(case.id)[0], 16) % 2 == parity]
    if args.concurrency < 1:
        raise ValueError("concurrency must be positive")
    output = Path(args.out)
    if any(case.provenance == "private_replay" for case in cases) and is_path_under(
        output, Path.cwd()
    ):
        raise PrivateOverlayError("private outputs must be outside checkout")
    runner = Runner(
        output_dir=output,
        backend=args.backend,
        harness=CodexHarness() if args.backend == "live" else None,
    )
    records = runner.run(
        cases,
        [item.strip() for item in args.architectures.split(",") if item.strip()],
        concurrency=args.concurrency,
    )
    print(f"wrote {len(records)} records to {output}")
    return 0


def _score_record_rows(
    records: list[Any],
    gold_root: Path,
    run_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .models import ReviewVerdict
    from .scoring import required_but_unmentioned, score_metrics, score_verdict

    rows: list[dict[str, Any]] = []
    gold_by_case: dict[str, Any] = {}
    for record in records:
        source = gold_root / (record.case_id or "") / "expected.yaml"
        if not source.exists():
            continue
        gold = load_gold(source)
        if record.case_id:
            gold_by_case[record.case_id] = gold
        if (
            record.error
            or getattr(getattr(record, "terminal", None), "value", record.terminal)
            == "error_terminal"
        ):
            continue
        run_root = run_path
        if (run_root / record.run_id).is_dir():
            run_root = run_root / record.run_id
        verdict_path = run_root / "verdicts" / f"{record.case_id}-{record.architecture}.json"
        if not verdict_path.exists():
            continue
        verdict = ReviewVerdict.model_validate_json(verdict_path.read_text(encoding="utf-8"))
        if (
            verdict.error
            or verdict.verdict == "human_decision"
            or (
                not verdict.findings
                and not verdict.requirement_coverage
                and bool(gold.expected_findings)
            )
        ):
            continue
        score = score_verdict(verdict, gold)
        requirements = _requirements_for_record(record.case_id, gold_root, run_path)
        rows.append(
            {
                "case_id": record.case_id,
                "architecture": record.architecture,
                "matches": score.exact_matches,
                "misses": score.misses,
                "spurious_blockers": score.spurious_blockers,
                "advisory_noise": score.advisory_noise,
                **score_metrics(score),
                "required_but_unmentioned": required_but_unmentioned(
                    gold, verdict.findings, requirements
                ),
                "source": "simulated" if record.backend == "mock" else "measured",
            }
        )
    return rows, gold_by_case


def _requirements_for_record(
    case_id: str | None,
    gold_root: Path,
    run_path: Path,
) -> list[Any]:
    if not case_id:
        return []
    candidates = [
        Path.cwd() / "cases" / "public" / case_id,
        gold_root.parent / "cases" / "public" / case_id,
        run_path.parent / "cases" / "public" / case_id,
    ]
    for candidate in candidates:
        if (candidate / "case.yaml").is_file():
            try:
                return load_case(candidate).requirements
            except CaseLoadError:
                return []
    return []


def _score(args: argparse.Namespace) -> int:
    records = load_records(args.run)
    rows, _ = _score_record_rows(records, Path(args.gold), Path(args.run))
    output = Path(args.out) if args.out else Path(args.run) / "metrics.json"
    if any(
        str(record.artifacts.get("provenance", "")) == "private_replay" for record in records
    ) and is_path_under(output, Path.cwd()):
        raise PrivateOverlayError("private metrics must be outside checkout")
    write_json(output, rows)
    print(output)
    return 0


def _sweep(args: argparse.Namespace) -> int:
    records = load_records(args.run)
    predictions: list[float] = []
    truths: list[bool] = []
    for record in records:
        for stage in record.stages:
            if stage.name != f"gate_{args.gate}":
                continue
            decision = stage.data.get("decision", {})
            for answer in decision.get("answers", []):
                probabilities = answer.get("probabilities", {})
                if "true" in probabilities:
                    predictions.append(float(probabilities["true"]))
                    truths.append(False)
    rows = sweep(predictions, truths)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(rows[0]) if rows else ["n"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        calibration = (
            calibrate(f"gate_{args.gate}", predictions, truths).as_dict()
            if predictions and len(set(truths)) > 1
            else None
        )
        output.write_bytes(
            canonical_bytes(
                {
                    "gate": args.gate,
                    "n": len(predictions),
                    "calibration": calibration,
                    "sweep": rows,
                    "claims": ["arithmetic demonstration only", "no best threshold"],
                }
            )
            + b"\n"
        )
    print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "cases":
            directory = _root(args, "cases/public")
            if args.action == "scan":
                if not Path(directory).exists():
                    raise FileNotFoundError(directory)
                if args.public_only and os.environ.get("REVIEW_LAB_PRIVATE_CASES"):
                    raise PrivateOverlayError(
                        "public-only runs refuse a configured private overlay"
                    )
                findings = scan_paths(directory)
                print(json.dumps({"findings": findings, "n": len(findings)}, sort_keys=True))
                return 3 if findings else 0
            cases = load_cases(directory, public_only=args.public_only)
            gold_root = Path(directory).parent / "gold"
            if not gold_root.is_dir():
                gold_root = Path(directory).parent.parent / "gold"
            if gold_root.is_dir():
                for case in cases:
                    gold_path = gold_root / case.id / "expected.yaml"
                    if gold_path.is_file():
                        for warning in gold_warnings(load_gold(gold_path)):
                            print(f"warning: {warning}")
            print(f"validated {len(cases)} cases")
            return 0
        if args.command == "experiment":
            return _run_cases(args)
        if args.command == "score":
            return _score(args)
        if args.command == "report":
            if args.action == "build":
                records = load_records(args.run)
                registry = read_yaml(
                    Path(__file__).resolve().parents[2] / "configs" / "metrics.yaml"
                )
                metric_rows = registry.get("metrics", [])
                if args.gold:
                    from .metrics import benchmark_metrics

                    score_rows, gold_by_case = _score_record_rows(
                        records, Path(args.gold), Path(args.run)
                    )
                    observed = {
                        row["id"]: row
                        for row in benchmark_metrics(
                            records,
                            gold_by_case=gold_by_case,
                            score_rows=score_rows,
                        )
                    }
                    metric_rows = [
                        {
                            **definition,
                            "value": observed.get(definition["id"], {}).get("value"),
                            "numerator_value": observed.get(definition["id"], {}).get(
                                "numerator_value"
                            ),
                            "denominator_value": observed.get(definition["id"], {}).get(
                                "denominator_value"
                            ),
                            "unavailable_reason": observed.get(definition["id"], {}).get(
                                "unavailable_reason"
                            ),
                        }
                        for definition in metric_rows
                    ]
                build_report(
                    records,
                    args.out,
                    metrics=metric_rows,
                    csv_destination=Path(args.out).with_suffix(".csv"),
                )
                print(args.out)
                return 0
            return _sweep(args)
        if args.command == "cost":
            rows = model_scenarios(args.scenarios)
            if args.out:
                write_json(args.out, rows)
            else:
                for row in rows:
                    print(json.dumps(row, sort_keys=True))
            return 0
        if args.command == "jev":
            backend = "live" if args.live else "mock"
            if backend == "mock" and args.allow_live:
                print("warning: --allow-live is unused with the mock backend", file=sys.stderr)
            if args.live:
                _ensure_live(args)
            state: dict[str, Any] = {}
            tag = "cli"
            if args.case:
                case = load_case(args.case)
                state = {
                    "case_digest": case_digest(case),
                    "head_digest": case.head_digest,
                }
                tag = case.id
            elif args.input:
                records = load_records(args.input)
                state = {"records": [record.model_dump(mode="json") for record in records]}
            fixture_root = Path(args.case) / "fixtures" if args.case else None
            gate = f"gate_{args.question_set[-1]}"
            result = JevAdapter(fixture_root=fixture_root).evaluate(
                backend,
                gate,
                state,
                _jev_questions(gate, mock=backend == "mock"),
                tag,
            )
            print(
                json.dumps(
                    {
                        "answers": [answer.model_dump(mode="json") for answer in result.answers],
                        "usage": result.usage.model_dump(mode="json") if result.usage else None,
                        "latency_ms": result.latency_ms,
                        "error": result.error,
                    },
                    sort_keys=True,
                )
            )
            return 0 if result.error is None else 3
        if args.command == "reviewer":
            if args.live:
                _ensure_reviewer_live(args)
                if args.harness != "codex":
                    raise PrivateOverlayError("live mode is only available for the codex harness")
            use_mock = not args.live
            harness = (
                CodexHarness()
                if not use_mock
                else MockHarness(
                    lane=HarnessId("mock_codex" if args.harness == "codex" else args.harness)
                )
            )
            case_path = Path(args.case)
            temporary: tempfile.TemporaryDirectory[str] | None = None
            if (case_path / "packet_manifest.json").exists():
                packet = case_path
            else:
                case = load_case(case_path)
                case_root = Path(case.case_dir or case_path)
                head = case_root / "head"
                repo = head if head.is_dir() else case_root / case.base_ref
                patch_path = Path(case.case_dir or case_path) / case.patch_ref
                patch = patch_path.read_text(encoding="utf-8") if patch_path.exists() else ""
                temporary = tempfile.TemporaryDirectory(prefix="review-lab-reviewer-")
                packet = PacketBuilder(Path(temporary.name)).build(
                    case,
                    run_deterministic_gates(repo, patch, case),
                    arm="reviewer",
                    patch=patch,
                    repo=repo,
                    head_digest=case.head_digest,
                )
            try:
                verdict = harness.run(packet, model=args.model, effort=args.effort)
            finally:
                if temporary is not None:
                    temporary.cleanup()
            print(verdict.model_dump_json())
            return 0 if verdict.error is None else 3
        return 2
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    except FileNotFoundError:
        return 5
    except (PrivateOverlayError, PermissionError):
        return 4
    except (CaseLoadError, ValidationError, ValueError, TypeError):
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
