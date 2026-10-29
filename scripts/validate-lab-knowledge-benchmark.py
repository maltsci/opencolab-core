#!/usr/bin/env python3
"""Validate a Lab Knowledge OS v1 benchmark without exposing its contents."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


EXPECTED_CATEGORY_COUNTS = {
    "people": 8,
    "research": 8,
    "resources": 8,
    "cross_entity": 6,
}
ALLOWED_EXPECTED_BEHAVIORS = {"answer", "no_answer", "permission_limited"}
ALLOWED_PERMISSION_PROFILES = {
    "admin",
    "pi",
    "member_with_project_access",
    "member_without_project_access",
}
ALLOWED_ENTITY_TYPES = {"person", "research_direction", "resource"}
QUESTION_ID_PATTERN = re.compile(r"^LK-[0-9]{3}$")


def add_error(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_date(value: Any, errors: list[str], path: str) -> None:
    if not isinstance(value, str):
        add_error(errors, path, "expected ISO date string")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        add_error(errors, path, "expected ISO date string")


def validate_string_list(
    value: Any,
    errors: list[str],
    path: str,
    allowed_values: set[str] | None = None,
    require_non_empty: bool = True,
) -> bool:
    if not isinstance(value, list):
        add_error(errors, path, "expected array")
        return False
    if require_non_empty and not value:
        add_error(errors, path, "expected non-empty array")
        return False

    valid = True
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not is_non_empty_string(item):
            add_error(errors, item_path, "expected non-empty string")
            valid = False
        elif allowed_values is not None and item not in allowed_values:
            add_error(errors, item_path, "contains unsupported value")
            valid = False
    return valid


def validate_question(question: Any, index: int, errors: list[str]) -> tuple[str | None, str | None, int]:
    path = f"questions[{index}]"
    if not isinstance(question, dict):
        add_error(errors, path, "expected object")
        return None, None, 0

    question_id = question.get("id")
    if not is_non_empty_string(question_id) or not QUESTION_ID_PATTERN.fullmatch(question_id):
        add_error(errors, f"{path}.id", "expected LK-NNN identifier")
        question_id = None

    category = question.get("category")
    if category not in EXPECTED_CATEGORY_COUNTS:
        add_error(errors, f"{path}.category", "contains unsupported value")
        category = None

    question_text = question.get("question")
    if not isinstance(question_text, str) or len(question_text) < 5:
        add_error(errors, f"{path}.question", "expected string with at least 5 characters")

    expected_behavior = question.get("expected_behavior")
    if expected_behavior not in ALLOWED_EXPECTED_BEHAVIORS:
        add_error(errors, f"{path}.expected_behavior", "contains unsupported value")
        expected_behavior = None

    permission_profiles = question.get("permission_profiles")
    multi_permission_count = 0
    if validate_string_list(
        permission_profiles,
        errors,
        f"{path}.permission_profiles",
        ALLOWED_PERMISSION_PROFILES,
    ):
        if len(set(permission_profiles)) != len(permission_profiles):
            add_error(errors, f"{path}.permission_profiles", "contains duplicate values")
        elif len(permission_profiles) >= 2:
            multi_permission_count = 1

    rubric = question.get("rubric")
    rubric_path = f"{path}.rubric"
    if not isinstance(rubric, dict):
        add_error(errors, rubric_path, "expected object")
    else:
        validate_string_list(
            rubric.get("required_entity_types"),
            errors,
            f"{rubric_path}.required_entity_types",
            ALLOWED_ENTITY_TYPES,
        )
        validate_string_list(
            rubric.get("required_source_titles"),
            errors,
            f"{rubric_path}.required_source_titles",
            require_non_empty=False,
        )
        if not is_non_empty_string(rubric.get("notes")):
            add_error(errors, f"{rubric_path}.notes", "expected non-empty string")

    return question_id, category, multi_permission_count if expected_behavior else 0


def validate_benchmark(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        add_error(errors, "$", "expected object")
        return errors

    validate_date(document.get("frozen_at"), errors, "frozen_at")
    questions = document.get("questions")
    if not isinstance(questions, list):
        add_error(errors, "questions", "expected array")
        return errors

    if len(questions) != 30:
        add_error(errors, "questions", "expected exactly 30 items")

    identifiers: set[str] = set()
    categories: Counter[str] = Counter()
    limited_or_no_answer_count = 0
    multi_permission_count = 0
    for index, question in enumerate(questions):
        question_id, category, is_multi_permission = validate_question(question, index, errors)
        if question_id:
            if question_id in identifiers:
                add_error(errors, f"questions[{index}].id", "duplicate identifier")
            identifiers.add(question_id)
        if category:
            categories[category] += 1
        if isinstance(question, dict) and question.get("expected_behavior") in {
            "no_answer",
            "permission_limited",
        }:
            limited_or_no_answer_count += 1
        multi_permission_count += is_multi_permission

    if dict(categories) != EXPECTED_CATEGORY_COUNTS:
        add_error(errors, "questions.category", "does not match required category counts")
    if limited_or_no_answer_count < 6:
        add_error(errors, "questions.expected_behavior", "requires at least 6 limited or no-answer cases")
    if multi_permission_count < 6:
        add_error(errors, "questions.permission_profiles", "requires at least 6 multi-permission cases")

    return errors


def format_success(digest: str, document: dict[str, Any]) -> str:
    categories = Counter(question["category"] for question in document["questions"])
    limited_or_no_answer_count = sum(
        question["expected_behavior"] in {"no_answer", "permission_limited"}
        for question in document["questions"]
    )
    multi_permission_count = sum(
        len(set(question["permission_profiles"])) >= 2
        for question in document["questions"]
    )
    return (
        f"sha256={digest} questions={len(document['questions'])} "
        f"people={categories['people']} research={categories['research']} "
        f"resources={categories['resources']} cross_entity={categories['cross_entity']} "
        f"limited_or_no_answer={limited_or_no_answer_count} "
        f"multi_permission={multi_permission_count}"
    )


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print("usage: validate-lab-knowledge-benchmark.py <benchmark.json>", file=sys.stderr)
        return 1

    try:
        content = Path(arguments[0]).read_bytes()
        document = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("input: unable to read valid JSON", file=sys.stderr)
        return 1

    errors = validate_benchmark(document)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(format_success(hashlib.sha256(content).hexdigest(), document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
