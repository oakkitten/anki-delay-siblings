from unittest.mock import MagicMock

import pytest

from tests.conftest import (
    try_with_all_schedulers,
    review_cards_in_0_5_10_days,
    show_answer_of_card1_in_20_days,
)

from tests.tools.collection import (
    move_main_window_to_state,
)


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

    show_answer_of_card1_in_20_days(setup)

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

    move_main_window_to_state("deckBrowser")
    assert get_menu_status() == (False, False, False, False)

    move_main_window_to_state("overview")
    assert get_menu_status() == (True, False, False, False)

    delay_siblings.menu_enabled.trigger()
    assert get_menu_status() == (True, True, True, False)

    delay_siblings.menu_quiet.trigger()
    assert get_menu_status() == (True, True, True, True)

    move_main_window_to_state("deckBrowser")
    assert get_menu_status() == (False, False, False, False)

    move_main_window_to_state("overview")
    assert get_menu_status() == (True, True, True, True)
    assert delay_siblings.config.current_deck.enabled is True
    assert delay_siblings.config.current_deck.quiet is True
