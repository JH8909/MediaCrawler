from integrations.demand_report.keywords import (
    DEMAND_WORDS,
    DOMAIN_WORDS,
    generate_keyword_plans,
)


def test_generate_keyword_plans_uses_domain_and_demand_words():
    plans = generate_keyword_plans(count=3, offset=0)

    assert [plan.keyword for plan in plans] == [
        f"{DOMAIN_WORDS[0]} {DEMAND_WORDS[0]}",
        f"{DOMAIN_WORDS[1]} {DEMAND_WORDS[1]}",
        f"{DOMAIN_WORDS[2]} {DEMAND_WORDS[2]}",
    ]
    assert plans[0].domain == DOMAIN_WORDS[0]
    assert plans[0].demand_word == DEMAND_WORDS[0]


def test_generate_keyword_plans_supports_offset_rotation():
    plans = generate_keyword_plans(count=2, offset=14)

    assert len(plans) == 2
    assert plans[0].keyword == f"{DOMAIN_WORDS[14 % len(DOMAIN_WORDS)]} {DEMAND_WORDS[14 % len(DEMAND_WORDS)]}"


def test_generate_keyword_plans_rejects_invalid_count():
    try:
        generate_keyword_plans(count=0)
    except ValueError as exc:
        assert "count must be between 1 and 100" in str(exc)
    else:
        raise AssertionError("expected ValueError")
