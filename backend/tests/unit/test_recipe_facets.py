from __future__ import annotations

from decimal import Decimal

from cookfully.domain.decisions import Answers, ModelAnswers
from cookfully.domain.recipe_facets import interpret

D = Decimal


def _answers(**overrides: object) -> Answers:
    checks = {
        "diet_vegetarian": D("0.9"),
        "diet_vegan": D("0.2"),
        "diet_gluten_free": D("0.6"),
        "diet_dairy_free": D("0.1"),
        "keeps_4_days": D("0.85"),
        "freezes_well": D("0.3"),
        "reheats_well": D("0.7"),
        "needs_oven": D("0.05"),
    }
    choices = {
        "cuisine": {"italian": D("0.9"), "other": D("0.1")},
        "meal_type": {"main": D("0.8"), "side": D("0.2")},
    }
    scores = {"effort": D("0"), "active_time": D("0.3333")}
    for key, value in overrides.items():
        if key in checks:
            checks[key] = value  # type: ignore[assignment]
        elif key in choices:
            choices[key] = value  # type: ignore[assignment]
        else:
            scores[key] = value  # type: ignore[assignment]
    return Answers({"m1": ModelAnswers(choices, checks, scores)})


def test_answers_become_tags_above_the_show_threshold() -> None:
    tags = {tag.key: tag for tag in interpret(_answers(), ["200 g rice noodles", "2 tomatoes"])}
    assert set(tags) == {
        "vegetarian",
        "gluten_free",
        "cuisine:italian",
        "meal:main",
        "effort:minimal",
        "time:15_30",
        "keeps_4_days",
        "reheats_well",
        "weeknight",
    }
    assert tags["vegetarian"].confident
    assert not tags["gluten_free"].confident
    assert tags["effort:minimal"].probability == D(1)


def test_ingredients_override_diet_tags() -> None:
    answers = _answers(diet_vegan=D("0.9"), diet_dairy_free=D("0.9"))
    keys = {tag.key for tag in interpret(answers, ["2 chicken breasts", "1 cup cheddar cheese"])}
    assert not keys & {"vegetarian", "vegan", "dairy_free"}
    keys = {tag.key for tag in interpret(answers, ["1 cup flour", "2 eggs"])}
    assert "gluten_free" not in keys
    assert "vegan" not in keys
    assert "vegetarian" in keys and "dairy_free" in keys


def test_other_cuisine_and_unsure_choices_are_not_tagged() -> None:
    answers = _answers(
        cuisine={"other": D("0.9"), "italian": D("0.1")},
        meal_type={"main": D("0.4"), "side": D("0.35"), "snack": D("0.25")},
    )
    keys = {tag.key for tag in interpret(answers, [])}
    assert not any(key.startswith(("cuisine:", "meal:")) for key in keys)


def test_scores_map_to_the_nearest_level_and_weeknight_needs_low_effort() -> None:
    slow = {tag.key for tag in interpret(_answers(effort=D("1"), active_time=D("1")), [])}
    assert {"effort:involved", "time:over_60"} <= slow
    assert "weeknight" not in slow
    moderate = {tag.key for tag in interpret(_answers(effort=D("0.5"), active_time=D("0")), [])}
    assert {"effort:moderate", "time:under_15", "weeknight"} <= moderate
    half_hour = {
        tag.key for tag in interpret(_answers(effort=D("0.5"), active_time=D("0.3333")), [])
    }
    assert "weeknight" not in half_hour


def test_no_answers_give_no_tags() -> None:
    assert interpret(Answers(), ["1 cup rice"]) == ()


def test_a_diet_tag_needs_every_model_not_the_average() -> None:
    split = Answers(
        {
            "m1": ModelAnswers({}, {"diet_gluten_free": D("0.9")}, {}),
            "m2": ModelAnswers({}, {"diet_gluten_free": D("0.1")}, {}),
        }
    )
    assert "gluten_free" not in {tag.key for tag in interpret(split, ["1 cup rice"])}
    agreed = Answers(
        {
            "m1": ModelAnswers({}, {"diet_gluten_free": D("0.9")}, {}),
            "m2": ModelAnswers({}, {"diet_gluten_free": D("0.8")}, {}),
        }
    )
    assert "gluten_free" in {tag.key for tag in interpret(agreed, ["1 cup rice"])}
