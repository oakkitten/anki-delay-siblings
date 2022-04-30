from tests.anki_helpers import EASY, DO_NOT_ANSWER, do_some_historic_reviews, get_card, \
    CardInfo


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


def test_foo(setup):
    card1_id, card2_id = setup.note1_card_ids

    do_some_historic_reviews({
        -20: {card1_id: EASY, card2_id: EASY},
        -15: {card1_id: EASY, card2_id: EASY},
        -10: {card1_id: EASY, card2_id: EASY},
    })
    print(CardInfo.from_card(get_card(card1_id)).to_string())
