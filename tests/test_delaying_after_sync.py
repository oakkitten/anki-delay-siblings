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
    clock_set_forward_by, get_scheduler,
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


@pytest.mark.parametrize(
    "sync_after_days",
    [20, 30],
    ids=[
        "delaying done as new due is in the future",
        "no delaying done as new due would be in the past"
    ]
)
@try_with_all_schedulers
def test_after_sync_that_brings_one_new_review(setup, on, sync_after_days):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.enabled_for_current_deck = True

    with syncing(for_days=sync_after_days):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    if sync_after_days == 20:
        assert card2_new_due > card2_old_due
        assert card2_new_due - card2_old_due < 10
    else:
        assert card2_old_due == card2_new_due


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


@pytest.mark.parametrize(
    "break_manual_review_detection",
    [False, pytest.param(True, marks=pytest.mark.xfail)],
    ids=[
        "manual review detection not broken",
        "manual review detection broken (sanity test)"
    ]
)
@try_with_all_schedulers
def test_addon_does_not_reschedule_if_user_manually_set_card_due(setup, on,
        break_manual_review_detection, monkeypatch):
    if break_manual_review_detection:
        original = setup.delay_siblings.get_card_id_to_last_review_time
        def patched(_skip_manual):  # noqa
            return original(skip_manual=False)
        monkeypatch.setattr(setup.delay_siblings, "get_card_id_to_last_review_time", patched)

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.enabled_for_current_deck = True

    with syncing(for_days=20):
        with clock_set_forward_by(days=20):
            get_scheduler().set_due_date(card_ids=[setup.card1_id], days="0")

    card2_new_due = get_card(setup.card2_id).due
    assert card2_old_due == card2_new_due
