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


@pytest.fixture(autouse=True)
def automatically_accept_the_delay_after_sync_dialog(monkeypatch):
    from delay_siblings.delay_after_sync_dialog import DelayAfterSyncDialog
    original_show = DelayAfterSyncDialog.show

    def new_show(self):
        original_show(self)
        self.accept()

    monkeypatch.setattr(DelayAfterSyncDialog, "show", new_show)


########################################################################################

@pytest.mark.parametrize(
    "only_enabled",
    ["for_deck", "globally"],
    ids=[
        "delaying enabled for deck; delaying after sync disabled",
        "delaying disabled for deck; delaying after sync enabled"
    ]
)
@try_with_all_schedulers
def test_addon_does_not_reschedule_cards_if_not_enabled(setup, only_enabled):
    if only_enabled == "for_deck":
        setup.delay_siblings.config.enabled_for_current_deck = True
        setup.delay_siblings.config.delay_after_sync = setup.delay_siblings.DO_NOT_DELAY
    elif only_enabled == "globally":
        # delay after sync is enabled by default
        assert setup.delay_siblings.config.delay_after_sync == setup.delay_siblings.ASK_EVERY_TIME

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
def test_after_sync_that_brings_one_new_review(setup, sync_after_days):
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
def test_addon_reschedules_one_card_after_sync_that_brings_many_new_reviews(setup):
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
def test_addon_does_not_reschedule_if_user_manually_set_card_due(setup,
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
