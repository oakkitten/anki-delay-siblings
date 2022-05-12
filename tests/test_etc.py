from unittest.mock import MagicMock

import aqt
import pytest

from tests.conftest import (
    try_with_all_schedulers,
    review_cards_in_0_5_10_days,
    show_answer_of_card1_in_20_days,
)

from tests.tools.collection import move_main_window_to_state


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

    setup.delay_siblings.config.enabled_for_current_deck = True
    setup.delay_siblings.config.quiet = quiet

    show_answer_of_card1_in_20_days(setup)

    assert setup.delay_siblings.tooltip.call_count == (0 if quiet else 1)  # noqa


def test_menus_get_disabled_enabled(setup):
    import delay_siblings

    def get_menu_status():
        return (
            delay_siblings.menu_enabled_for_this_deck.isEnabled(),
            delay_siblings.menu_enabled_for_this_deck.isChecked(),
            delay_siblings.menu_quiet.isChecked(),
            delay_siblings.menu_delay_without_asking.isChecked(),
            delay_siblings.menu_ask_every_time.isChecked(),
            delay_siblings.menu_do_not_delay.isChecked(),
        )

    move_main_window_to_state("deckBrowser")
    assert get_menu_status() == (False, False, False, False, True, False)

    move_main_window_to_state("overview")
    assert get_menu_status() == (True, False, False, False, True, False)

    delay_siblings.menu_enabled_for_this_deck.trigger()
    assert get_menu_status() == (True, True, False, False, True, False)
    assert delay_siblings.config.enabled_for_current_deck is True

    delay_siblings.config.enabled_for_current_deck = True
    delay_siblings.config.quiet = True
    delay_siblings.config.delay_after_sync = delay_siblings.configuration.DO_NOT_DELAY
    move_main_window_to_state("overview")
    assert get_menu_status() == (True, True, True, False, False, True)

    delay_siblings.menu_delay_without_asking.trigger()
    move_main_window_to_state("overview")
    print(delay_siblings.config.data)
    assert get_menu_status() == (True, True, True, True, False, False)


def test_epoch_to_anki_days(setup):
    from delay_siblings.tools import get_anki_today, epoch_to_anki_days
    next_day_at = aqt.mw.col.sched._timing_today().next_day_at

    assert epoch_to_anki_days(next_day_at - 100) == get_anki_today()
    assert epoch_to_anki_days(next_day_at + 100) == get_anki_today() + 1


class TestConfigMigration:
    def test_v0_default_config_migration(self, setup):
        data = {"version": 0}
        setup.delay_siblings.configuration.migrate(data)

    def test_v0_changed_config_migration(self, setup):
        data = {"version": 0, "123": {"enabled": False, "quiet": True}}
        setup.delay_siblings.configuration.migrate(data)

    def test_v0_migration_fails_with_bad_config(self, setup):
        with pytest.raises(Exception):
            data = {"version": 0, 123: {"a": "b"}}
            setup.delay_siblings.configuration.migrate(data)

    def test_default_configuration_restored_on_failure(self, setup, monkeypatch):
        monkeypatch.setattr(setup.delay_siblings.configuration, "showWarning", MagicMock())
        data = {"version": 0, 123: {"a": "b"}}
        data = setup.delay_siblings.configuration.migrate_data_restoring_default_config_on_error(data)
        assert data == setup.delay_siblings.configuration.load_default_config()
