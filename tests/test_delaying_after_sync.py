from contextlib import contextmanager

import pytest
from aqt import gui_hooks

from tests.conftest import (
    try_with_all_schedulers,
    review_cards_in_0_5_10_days,
    review_card1_in_20_days
)

from tests.tools.collection import (
    get_card,
    clock_set_forward_by,
)


@contextmanager
def reviewing_on_another_device():
    import delay_siblings
    from delay_siblings.configuration import load_default_config

    old_config_data = delay_siblings.config.data
    delay_siblings.config.data = load_default_config()

    try:
        yield
    finally:
        delay_siblings.config.data = old_config_data


@contextmanager
def syncing(for_days: int):
    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        yield

    with clock_set_forward_by(days=for_days):
        gui_hooks.sync_did_finish()


@pytest.fixture
def on(setup):
    from delay_siblings import config, ASK_EVERY_TIME
    config.delay_after_sync = ASK_EVERY_TIME


@pytest.fixture(autouse=True)
def automatically_accept_the_delay_after_sync_dialog(monkeypatch):
    from delay_siblings.delay_after_sync_dialog import DelayAfterSyncDialog

    def new_exec(self):
        self.show()
        self.accept()
        return self.result()

    monkeypatch.setattr(DelayAfterSyncDialog, "exec", new_exec)


########################################################################################


@try_with_all_schedulers
def test_addon_does_not_reschedule_cards_if_not_enabled_for_deck(setup, on):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    with syncing(for_days=20):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    assert card2_old_due == card2_new_due


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_one_new_review(setup, on):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.enabled_for_current_deck = True

    with syncing(for_days=20):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    assert card2_new_due > card2_old_due
    assert card2_new_due - card2_old_due < 10


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_many_new_reviews(setup, on):
    setup.delay_siblings.config.enabled_for_current_deck = True

    with syncing(for_days=20):
        review_cards_in_0_5_10_days(setup)
        review_card1_in_20_days(setup)
        card2_old_due = get_card(setup.card2_id).due

    card2_new_due = get_card(setup.card2_id).due
    assert card2_new_due > card2_old_due
    assert card2_new_due - card2_old_due < 10


# same as test_addon_reschedules_one_card_after_sync_that_brings_one_new_review, but more days
@try_with_all_schedulers
def test_addon_does_not_reschedule_if_new_due_would_be_in_the_past(setup, on):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.enabled_for_current_deck = True

    with syncing(for_days=30):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    assert card2_old_due == card2_new_due
