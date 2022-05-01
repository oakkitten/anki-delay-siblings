from unittest.mock import MagicMock

import aqt
import pytest

from tests.anki_helpers import (
    EASY,
    DO_NOT_ANSWER,
    do_some_historic_reviews,
    get_card,
    filtered_deck_created,
    show_deck_overview,
    CardInfo,
)


def test_addon_has_no_effect_if_not_enabled(setup):
    import delay_siblings  # noqa

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    card2_old_due = get_card(card2_id).due

    do_some_historic_reviews({
        0: {card1_id: DO_NOT_ANSWER},
    })

    card2_new_due = get_card(card2_id).due
    assert card2_old_due == card2_new_due


def test_addon_changes_one_card_due_if_enabled(setup):
    import delay_siblings

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    card2_old_due = get_card(card2_id).due

    delay_siblings.config.current_deck.enabled = True

    do_some_historic_reviews({
        0: {card1_id: DO_NOT_ANSWER},
    })

    card2_new_due = get_card(card2_id).due
    assert card2_old_due != card2_new_due


def test_addon_changes_one_card_due_in_a_filtered_deck(setup):
    import delay_siblings

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    card2_old_due = get_card(card2_id).due

    with filtered_deck_created(f"cid:{card2_id}"):
        show_deck_overview(setup.deck_id)
        delay_siblings.config.current_deck.enabled = True

        do_some_historic_reviews({
            0: {card1_id: DO_NOT_ANSWER},
        })

    card2_new_due = get_card(card2_id).due
    assert card2_old_due != card2_new_due


def test_addon_changes_one_card_due_when_ran_in_a_filtered_deck(setup):
    import delay_siblings

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    card2_old_due = get_card(card2_id).due

    with filtered_deck_created(f"cid:{card1_id}") as filtered_deck_id:
        show_deck_overview(filtered_deck_id)
        delay_siblings.config.current_deck.enabled = True

        do_some_historic_reviews({
            0: {card1_id: DO_NOT_ANSWER},
        })

    card2_new_due = get_card(card2_id).due
    assert card2_old_due != card2_new_due


def test_new_due_falls_within_change_range(setup):
    import delay_siblings

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    card2_info = CardInfo.from_card(get_card(card2_id))
    card2_interval = card2_info.reviews[-1].interval
    new_due_min, new_due_max = \
        delay_siblings.calculate_new_relative_due_range(card2_interval, 2)

    delay_siblings.config.current_deck.enabled = True

    do_some_historic_reviews({
        0: {card1_id: DO_NOT_ANSWER},
    })

    card2_new_due = get_card(card2_id).due
    assert new_due_min <= card2_new_due <= new_due_max


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
    ]
)
def test_new_due_range_function(setup, interval, cards_per_note, result):
    from delay_siblings import calculate_new_relative_due_range

    assert calculate_new_relative_due_range(interval, cards_per_note) == result


@pytest.mark.parametrize("quiet", [False, True])
def test_tooltip_not_called_if_quiet(setup, quiet, monkeypatch):
    import delay_siblings

    monkeypatch.setattr(delay_siblings, "tooltip", MagicMock())

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    delay_siblings.config.current_deck.enabled = True
    delay_siblings.config.current_deck.quiet = quiet

    do_some_historic_reviews({
        0: {card1_id: DO_NOT_ANSWER},
    })

    assert delay_siblings.tooltip.call_count == (0 if quiet else 1)  # noqa


def test_card_gets_removed_from_review_queue(setup):
    import delay_siblings  # noqa

    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })

    delay_siblings.config.current_deck.enabled = True

    do_some_historic_reviews({
        0: {card1_id: DO_NOT_ANSWER}
    })

    with pytest.raises(Exception, match=f"(?s)didn't show.*id: {card2_id}"):
        do_some_historic_reviews({
            0: {card2_id: EASY},
        })


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

