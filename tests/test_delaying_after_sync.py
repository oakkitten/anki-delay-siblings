from aqt import gui_hooks

from tests.conftest import try_with_all_schedulers
from tests.tools.collection import (
    EASY,
    do_some_historic_reviews,
    get_card,
    clock_set_forward_by,
)


def review_cards_in_0_5_10_days(setup):
    do_some_historic_reviews({
        0: {setup.card1_id: EASY, setup.card2_id: EASY},
        5: {setup.card1_id: EASY, setup.card2_id: EASY},
        10: {setup.card1_id: EASY, setup.card2_id: EASY},
    })


def review_card1_in_20_days(setup):
    do_some_historic_reviews({
        20: {setup.card1_id: EASY},
    })


@try_with_all_schedulers
def test_addon_reschedules_one_card_after_sync(setup):
    setup.delay_siblings.config.data[setup.delay_siblings.OFFER_TO_DELAY_AFTER_SYNC] = True

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    gui_hooks.sync_will_start()

    review_card1_in_20_days(setup)

    with clock_set_forward_by(days=20):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due != card2_new_due


@try_with_all_schedulers
def test_addon_does_not_reschedule_if_new_due_would_be_in_the_past(setup):
    setup.delay_siblings.config.data[setup.delay_siblings.OFFER_TO_DELAY_AFTER_SYNC] = True

    review_cards_in_0_5_10_days(setup)
    card2_old_due = get_card(setup.card2_id).due

    gui_hooks.sync_will_start()

    review_card1_in_20_days(setup)

    with clock_set_forward_by(days=30):
        gui_hooks.sync_did_finish()
        card2_new_due = get_card(setup.card2_id).due

        assert card2_old_due == card2_new_due
