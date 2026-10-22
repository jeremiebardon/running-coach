"""Offline evaluation = the agent's "test suite".

- Data: fixtures + frozen clock → identical inputs on every run, so a score
  change means the AGENT changed (prompt, model, tools), not the data.
- Phoenix stores the dataset, each experiment, every task trace and every
  evaluator result → compare experiments side by side in the UI.
- Exit code is the CI gate (thresholds.json).

Usage: uv run python -m evals.run [--code-only] [--repetitions N]
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from phoenix.client import AsyncClient

from evals.dataset import DATASET_NAME, EXAMPLES
from evals.evaluators import CODE_EVALUATORS, llm_judges
from running_coach.agent.graph import build_graph
from running_coach.agent.llm import build_model
from running_coach.agent.prompts import COACH_PROMPT_VERSION
from running_coach.agent.runner import run_turn
from running_coach.data.base import FixedClock
from running_coach.data.fixtures import DEFAULT_FIXTURE, FixtureData
from running_coach.observability import init_telemetry, shutdown_telemetry
from running_coach.settings import get_settings

THRESHOLDS = json.loads((Path(__file__).parent / "thresholds.json").read_text(encoding="utf-8"))


async def get_or_create_dataset(client: AsyncClient):
    try:
        return await client.datasets.get_dataset(dataset=DATASET_NAME)
    except (httpx.HTTPStatusError, ValueError):
        return await client.datasets.create_dataset(
            name=DATASET_NAME,
            examples=EXAMPLES,
            dataset_description="Golden questions for the running coach (fixture athlete, frozen clock)",
        )


async def main(code_only: bool, repetitions: int) -> int:
    settings = get_settings()
    init_telemetry("running-coach-evals")  # LangGraph spans are re-tagged into the experiment by Phoenix

    clock = FixedClock("2026-10-17")
    graph = build_graph(
        build_model(settings.coach_model),
        FixtureData(settings.fixture_path or DEFAULT_FIXTURE, clock),
        clock,
        InMemorySaver(),
    )

    async def task(input: dict, example: dict) -> dict:
        turn = await run_turn(
            graph,
            input["question"],
            session_id=f"eval-{example['id']}-{os.urandom(3).hex()}",
            metadata={"surface": "eval", "category": example.get("metadata", {}).get("category")},
        )
        return {
            "answer": turn.answer,
            "tool_names": [t.name for t in turn.tool_calls],
            "tool_evidence": json.dumps(
                [{"name": t.name, "input": t.input, "output": t.output} for t in turn.tool_calls]
            ),
            "steps": turn.steps,
        }

    evaluators = CODE_EVALUATORS | ({} if code_only else llm_judges(build_model(settings.judge_model)))
    sha = (os.environ.get("GITHUB_SHA") or "local")[:7]
    client = AsyncClient()
    experiment = await client.experiments.run_experiment(
        dataset=await get_or_create_dataset(client),
        task=task,
        evaluators=evaluators,
        experiment_name=f"{COACH_PROMPT_VERSION}-{settings.coach_model}-{sha}",
        experiment_description=f"prompt={COACH_PROMPT_VERSION} model={settings.coach_model} sha={sha}",
        experiment_metadata={
            "promptVersion": COACH_PROMPT_VERSION,
            "model": settings.coach_model,
            "judge": None if code_only else settings.judge_model,
            "sha": sha,
            "branch": os.environ.get("GITHUB_HEAD_REF", "local"),
        },
        concurrency=1 if settings.coach_model.startswith("ollama:") else 3,  # one local GPU → no gain in parallel
        timeout=600,
        repetitions=repetitions,
    )
    shutdown_telemetry()
    return gate(experiment)


def gate(experiment) -> int:
    """CI gate: mean score per evaluator must be >= its threshold, and no task may fail."""
    scores: dict[str, list[float]] = defaultdict(list)
    evaluator_errors = 0
    for run in experiment["evaluation_runs"]:
        if run.error or run.result is None or run.result.get("score") is None:
            evaluator_errors += 1
            continue
        scores[run.name].append(run.result["score"])
    task_runs = experiment["task_runs"]
    task_errors = sum(1 for r in task_runs if r.get("error"))

    rows = []
    for name, values in scores.items():
        mean = sum(values) / len(values)
        minimum = THRESHOLDS.get(name)
        rows.append((name, mean, minimum, len(values), minimum is None or mean >= minimum))
    passed = all(r[4] for r in rows) and task_errors == 0

    report = "\n".join(
        [
            f"## 🏃 Coach evals — {'✅ passed' if passed else '❌ failed'}",
            f"Experiment `{experiment['experiment_id']}` · prompt `{COACH_PROMPT_VERSION}` · {len(task_runs)} runs"
            f" · task errors: {task_errors} · evaluator errors: {evaluator_errors}",
            "",
            "| evaluator | mean | threshold | n | |",
            "|---|---|---|---|---|",
            *(
                f"| {name} | {mean:.2f} | {'—' if minimum is None else minimum} | {n} | {'✅' if ok else '❌'} |"
                for name, mean, minimum, n, ok in rows
            ),
        ]
    )
    print(f"\n{report}\n")
    Path("eval-report.md").write_text(report + "\n", encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; reports use emoji
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code-only", action="store_true", help="skip the LLM judges (cheaper, faster)")
    parser.add_argument("--repetitions", type=int, default=1, help="runs per example, to measure variance")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.code_only, args.repetitions)))
