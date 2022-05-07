from contextlib import contextmanager

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


def turn_on_offer_to_disabled_after_sync():
    import delay_siblings
    from delay_siblings.configuration import OFFER_TO_DELAY_AFTER_SYNC
    delay_siblings.config.data[OFFER_TO_DELAY_AFTER_SYNC] = True


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


########################################################################################


@try_with_all_schedulers
def test_addon_does_not_reschedule_cards_if_not_enabled_for_deck(setup):
    turn_on_offer_to_disabled_after_sync()

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        review_card1_in_20_days(setup)

    with clock_set_forward_by(days=20):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due == card2_new_due


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_one_new_review(setup):
    turn_on_offer_to_disabled_after_sync()

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.current_deck.enabled = True
    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        review_card1_in_20_days(setup)

    with clock_set_forward_by(days=20):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync_that_brings_many_new_reviews(setup):
    turn_on_offer_to_disabled_after_sync()

    setup.delay_siblings.config.current_deck.enabled = True
    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        review_cards_in_0_5_10_days(setup)
        card2_old_due = get_card(setup.card2_id).due

        review_card1_in_20_days(setup)

    with clock_set_forward_by(days=20):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due != card2_new_due


# same as test_addon_reschedules_one_card_after_sync_that_brings_one_new_review, but more days
@try_with_all_schedulers
def test_addon_does_not_reschedule_if_new_due_would_be_in_the_past(setup):
    turn_on_offer_to_disabled_after_sync()

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    setup.delay_siblings.config.current_deck.enabled = True
    gui_hooks.sync_will_start()

    with reviewing_on_another_device():
        review_card1_in_20_days(setup)

    with clock_set_forward_by(days=30):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due == card2_new_due
