import aqt
from anki.consts import QUEUE_TYPE_REV, QUEUE_TYPE_LRN
from pytest import approx

from tests.anki_helpers import (get_scheduler_card, answer_card, EASY, clock_set_back,
                                minutes)


def test_sanity(setup):
    card = get_scheduler_card()

    with clock_set_back(by_days=10) as epoch:
        answer_card(card, EASY)

    assert card.queue == QUEUE_TYPE_LRN
    assert card.due == approx(epoch + minutes(10), abs=minutes(2))

    with clock_set_back(by_days=5):
        answer_card(card, EASY)

    assert card.queue == QUEUE_TYPE_REV
    assert card.due == aqt.mw.col.sched.today - 5
