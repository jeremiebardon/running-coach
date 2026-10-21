import json

from evals.evaluators import numbers_grounded, parse_label, required_facts, tool_selection

# Evaluators are code too — test them, or a broken evaluator silently "passes" CI.


def test_tool_selection_flags_missing_and_forbidden_tools():
    expected = {"required_tools": ["predict_race_time"], "forbidden_tools": ["build_pacing_plan"]}
    assert tool_selection({"tool_names": ["predict_race_time"]}, expected)["score"] == 1
    assert tool_selection({"tool_names": ["build_pacing_plan"]}, expected)["score"] == 0


def test_numbers_grounded_catches_an_invented_time():
    evidence = json.dumps([{"output": {"predicted": {"centre": "2:58:53", "pace": "4:14/km"}}}])
    question = {"question": "sub 2:55?"}
    grounded = numbers_grounded(
        question, {"answer": "You'd run about 2:58:53 (4:14/km); 2:55 is a stretch.", "tool_evidence": evidence}
    )
    invented = numbers_grounded(question, {"answer": "You'd run about 2:51:10.", "tool_evidence": evidence})
    assert grounded["score"] == 1
    assert invented["score"] == 0


def test_required_facts_is_case_insensitive():
    assert required_facts({"answer": "See a PHYSIO"}, {"must_match": ["physio"]})["score"] == 1
    assert required_facts({"answer": "Push through"}, {"must_match": ["physio"]})["score"] == 0


def test_judge_label_parsing_does_not_confuse_ungrounded_with_grounded():
    choices = {"grounded": 1, "ungrounded": 0}
    assert parse_label("Label: Ungrounded", choices) == "ungrounded"
    assert parse_label("grounded", choices) == "grounded"
    assert parse_label("no idea", choices) is None
