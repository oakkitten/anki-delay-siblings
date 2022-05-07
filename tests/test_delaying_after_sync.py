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
    from delay_siblings.configuration import Config

    old_config = delay_siblings.config
    delay_siblings.config = Config()

    try:
        yield
    finally:
        delay_siblings.config = old_config


@contextmanager
def syncing(for_days: int):
    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        yield

    with clock_set_forward_by(days=for_days):
        gui_hooks.sync_did_finish()


@pytest.fixture
def on(setup):
    import delay_siblings
    from delay_siblings.configuration import OFFER_TO_DELAY_AFTER_SYNC
    delay_siblings.config.data[OFFER_TO_DELAY_AFTER_SYNC] = True


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

    setup.delay_siblings.config.current_deck.enabled = True

    with syncing(for_days=20):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    assert card2_new_due > card2_old_due
    assert card2_new_due - card2_old_due < 10


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_many_new_reviews(setup, on):
    setup.delay_siblings.config.current_deck.enabled = True

    with syncing(for_days=20):
        review_cards_in_0_5_10_days(setup)
        review_card1_in_20_days(setup)
        card2_old_due = get_card(setup.card2_id).due

    card2_new_due = get_card(setup.card2_id).due
    assert card2_new_due > card2_old_due
    assert card2_new_due - card2_old_due < 10


# same as test_addon_reschedules_one_card_after_sync_that_brings_one_new_review, but more days
@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_one_new_review(setup, on):
    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.current_deck.enabled = True

    with syncing(for_days=30):
        review_card1_in_20_days(setup)

    card2_new_due = get_card(setup.card2_id).due
    assert card2_old_due == card2_new_due
