import aqt
import pytest

from tests.conftest import try_with_all_schedulers, review_cards_in_0_5_10_days, \
    show_answer_of_card1_in_20_days
from tests.tools.collection import (
    EASY,
    get_card,
    filtered_deck_created,
    show_deck_overview,
    CardInfo,
    clock_set_forward_by,
    reset_window_to_review_state,
    reviewer_show_question,
    reviewer_show_answer,
    reviewer_answer_card,
)


@try_with_all_schedulers
def test_addon_has_no_effect_if_not_enabled(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    show_answer_of_card1_in_20_days(setup)
    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due == card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_if_enabled(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.enabled_for_current_deck = True

    show_answer_of_card1_in_20_days(setup)
    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_in_a_filtered_deck(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    with filtered_deck_created(f"cid:{setup.card2_id}"):
        show_deck_overview(setup.deck_id)
        setup.delay_siblings.config.enabled_for_current_deck = True
        show_answer_of_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_when_ran_in_a_filtered_deck(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    with filtered_deck_created(f"cid:{setup.card1_id}") as filtered_deck_id:
        show_deck_overview(filtered_deck_id)
        setup.delay_siblings.config.enabled_for_current_deck = True
        show_answer_of_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_new_due_falls_within_calculated_range(setup):
    review_cards_in_0_5_10_days(setup)

    card2_info = CardInfo.from_card(get_card(setup.card2_id))
    card2_interval = card2_info.reviews[-1].interval
    new_due_min, new_due_max = \
        setup.delay_siblings.calculate_new_relative_due_range(card2_interval, 2)

    setup.delay_siblings.config.enabled_for_current_deck = True

    show_answer_of_card1_in_20_days(setup)
    card2_new_due = get_card(setup.card2_id).due

    assert new_due_min <= card2_new_due - 20 <= new_due_max


@pytest.mark.parametrize(
    "enabled, expected_state_after_answer",
    [(False, "review"), (True, "overview")],
    ids=["stays if not enabled", "removed if enabled"]
)
@try_with_all_schedulers
def test_card_gets_removed_from_review_queue(setup, enabled, expected_state_after_answer):
    review_cards_in_0_5_10_days(setup)

    setup.delay_siblings.config.enabled_for_current_deck = enabled

    with clock_set_forward_by(days=20):
        reset_window_to_review_state()
        reviewer_show_question()
        reviewer_show_answer()
        reviewer_answer_card(EASY)

        assert aqt.mw.state == expected_state_after_answer
