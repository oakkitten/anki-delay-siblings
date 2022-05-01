from unittest.mock import MagicMock

import aqt
import pytest

from tests.conftest import try_with_all_schedulers
from tests.anki_tools import (
    EASY,
    DO_NOT_ANSWER,
    do_some_historic_reviews,
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


def review_cards_in_0_5_10_days(setup):
    do_some_historic_reviews({
        0: {setup.card1_id: EASY, setup.card2_id: EASY},
        5: {setup.card1_id: EASY, setup.card2_id: EASY},
        10: {setup.card1_id: EASY, setup.card2_id: EASY},
    })


def review_card1_in_20_days(setup):
    do_some_historic_reviews({
        20: {setup.card1_id: DO_NOT_ANSWER},
    })


########################################################################################


@try_with_all_schedulers
def test_addon_has_no_effect_if_not_enabled(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    review_card1_in_20_days(setup)
    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due == card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_if_enabled(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.current_deck.enabled = True

    review_card1_in_20_days(setup)
    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_in_a_filtered_deck(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    with filtered_deck_created(f"cid:{setup.card2_id}"):
        show_deck_overview(setup.deck_id)
        setup.delay_siblings.config.current_deck.enabled = True
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_changes_one_card_due_when_ran_in_a_filtered_deck(setup):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    with filtered_deck_created(f"cid:{setup.card1_id}") as filtered_deck_id:
        show_deck_overview(filtered_deck_id)
        setup.delay_siblings.config.current_deck.enabled = True
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due

    assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_new_due_falls_within_calculated_range(setup):
    review_cards_in_0_5_10_days(setup)

    card2_info = CardInfo.from_card(get_card(setup.card2_id))
    card2_interval = card2_info.reviews[-1].interval
    new_due_min, new_due_max = \
        setup.delay_siblings.calculate_new_relative_due_range(card2_interval, 2)

    setup.delay_siblings.config.current_deck.enabled = True

    review_card1_in_20_days(setup)
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

    setup.delay_siblings.config.current_deck.enabled = enabled

    with clock_set_forward_by(days=20):
        reset_window_to_review_state()
        reviewer_show_question()
        reviewer_show_answer()
        reviewer_answer_card(EASY)

        assert aqt.mw.state == expected_state_after_answer


########################################################################################


@pytest.mark.parametrize(
    "interval, cards_per_note, result",
    [
        (0, 2, (0, 0)),
        (0, 3, (0, 0)),
        (2, 2, (1, 1)),
        (2, 3, (0, 0)),
        (16, 2, (4, 5)),
        (16, 3, (2, 3)),
        (360, 2, (28, 37)),
        (360, 3, (19, 24)),
    ],
    ids=lambda argument: repr(argument)
)
def test_new_due_range_function(setup, interval, cards_per_note, result):
    assert setup.delay_siblings \
               .calculate_new_relative_due_range(interval, cards_per_note) == result


@try_with_all_schedulers
@pytest.mark.parametrize("quiet", [False, True], ids=["not quiet", "quiet"])
def test_tooltip_not_called_if_quiet(setup, quiet, monkeypatch):
    monkeypatch.setattr(setup.delay_siblings, "tooltip", MagicMock())
    review_cards_in_0_5_10_days(setup)

    setup.delay_siblings.config.current_deck.enabled = True
    setup.delay_siblings.config.current_deck.quiet = quiet

    review_card1_in_20_days(setup)

    assert setup.delay_siblings.tooltip.call_count == (0 if quiet else 1)  # noqa


def test_menus_get_disabled_enabled(setup):
    import delay_siblings

    def get_menu_status():
        return (
            delay_siblings.menu_enabled.isEnabled(),
            delay_siblings.menu_enabled.isChecked(),
            delay_siblings.menu_quiet.isEnabled(),
            delay_siblings.menu_quiet.isChecked(),
        )

    aqt.mw.moveToState("deckBrowser")
    assert get_menu_status() == (False, False, False, False)

    aqt.mw.moveToState("overview")
    assert get_menu_status() == (True, False, False, False)

    delay_siblings.menu_enabled.trigger()
    assert get_menu_status() == (True, True, True, False)

    delay_siblings.menu_quiet.trigger()
    assert get_menu_status() == (True, True, True, True)

    aqt.mw.moveToState("deckBrowser")
    assert get_menu_status() == (False, False, False, False)

    aqt.mw.moveToState("overview")
    assert get_menu_status() == (True, True, True, True)
    assert delay_siblings.config.current_deck.enabled is True
    assert delay_siblings.config.current_deck.quiet is True
