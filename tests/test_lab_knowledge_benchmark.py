import json
import subprocess
import sys
from pathlib import Path


VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validate-lab-knowledge-benchmark.py"
)


def build_valid_benchmark() -> dict:
    categories = [
        *(["people"] * 8),
        *(["research"] * 8),
        *(["resources"] * 8),
        *(["cross_entity"] * 6),
    ]
    questions = []
    for index, category in enumerate(categories, start=1):
        expected_behavior = "answer"
        if index <= 3:
            expected_behavior = "no_answer"
        elif index <= 6:
            expected_behavior = "permission_limited"

        permission_profiles = ["admin"]
        if index <= 6:
            permission_profiles.append("member_without_project_access")

        questions.append(
            {
                "id": f"LK-{index:03d}",
                "category": category,
                "question": f"Question number {index}",
                "expected_behavior": expected_behavior,
                "permission_profiles": permission_profiles,
                "rubric": {
                    "required_entity_types": ["person"],
                    "required_source_titles": [f"Source {index}"],
                    "notes": "Evaluation notes",
                },
            }
        )
    return {"frozen_at": "2026-08-09", "questions": questions}


def run_validator(tmp_path: Path, benchmark: dict) -> subprocess.CompletedProcess[str]:
    dataset_path = tmp_path / "benchmark.json"
    dataset_path.write_text(json.dumps(benchmark), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(dataset_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validator_accepts_compliant_benchmark_without_disclosing_content(tmp_path: Path):
    result = run_validator(tmp_path, build_valid_benchmark())

    assert result.returncode == 0
    assert "sha256=" in result.stdout
    assert "people=8" in result.stdout
    assert "research=8" in result.stdout
    assert "resources=8" in result.stdout
    assert "cross_entity=6" in result.stdout
    assert "Question number 1" not in result.stdout
    assert result.stderr == ""


def test_validator_rejects_benchmark_with_fewer_than_thirty_questions(tmp_path: Path):
    benchmark = build_valid_benchmark()
    benchmark["questions"].pop()

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions" in result.stderr


def test_validator_rejects_wrong_category_distribution(tmp_path: Path):
    benchmark = build_valid_benchmark()
    benchmark["questions"][0]["category"] = "research"

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions.category" in result.stderr


def test_validator_rejects_duplicate_question_ids(tmp_path: Path):
    benchmark = build_valid_benchmark()
    benchmark["questions"][1]["id"] = benchmark["questions"][0]["id"]

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions[1].id" in result.stderr


def test_validator_rejects_too_few_limited_or_no_answer_questions(tmp_path: Path):
    benchmark = build_valid_benchmark()
    for question in benchmark["questions"]:
        question["expected_behavior"] = "answer"

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions.expected_behavior" in result.stderr


def test_validator_rejects_too_few_multi_permission_questions(tmp_path: Path):
    benchmark = build_valid_benchmark()
    for question in benchmark["questions"]:
        question["permission_profiles"] = ["admin"]

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions.permission_profiles" in result.stderr


def test_validator_accepts_empty_required_sources_for_no_answer_case(tmp_path: Path):
    benchmark = build_valid_benchmark()
    benchmark["questions"][0]["rubric"]["required_source_titles"] = []

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 0


def test_validator_reports_only_paths_for_invalid_question_content(tmp_path: Path):
    benchmark = build_valid_benchmark()
    private_question = "Private research question that must not appear in validation output"
    benchmark["questions"][0]["question"] = private_question
    benchmark["questions"][0]["id"] = "invalid-id"

    result = run_validator(tmp_path, benchmark)

    assert result.returncode == 1
    assert "questions[0].id" in result.stderr
    assert private_question not in result.stderr
    assert private_question not in result.stdout
