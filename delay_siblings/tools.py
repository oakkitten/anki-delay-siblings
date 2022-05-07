from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from anki.cards import Card
from anki.consts import QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV as CARD_TYPE_REVIEWING
from aqt import mw


def sorted_by_value(dictionary):
    return dict(sorted(dictionary.items(), key=lambda item: item[1]))


########################################################################################


def is_card_suspended(card: Card) -> bool:
    return card.queue == QUEUE_TYPE_SUSPENDED


def is_card_reviewing(card: Card) -> bool:
    return card.type == CARD_TYPE_REVIEWING


def is_card_in_a_filtered_deck(card: Card) -> bool:
    return card.odue != 0 and card.odid != 0


# card due is stored in days, starting at some abstract date; this gets today's due
def get_today() -> int:
    return mw.col.sched.today


def get_card_absolute_due(card: Card) -> int:
    return card.odue if is_card_in_a_filtered_deck(card) else card.due


def set_card_absolute_due(card: Card, absolute_due: int):
    if is_card_in_a_filtered_deck(card):
        card.odue = absolute_due
    else:
        card.due = absolute_due
    card.flush()


def remove_card_from_current_review_queue(card: Card):
    with suppress(AttributeError, ValueError):
        mw.col.sched._revQueue.remove(card.id)  # noqa


def get_siblings(card: Card) -> Sequence[Card]:
    card_ids = card.col.db.list("select id from cards where nid=? and id!=?",
                                card.nid, card.id)
    return [mw.col.get_card(card_id) for card_id in card_ids]


########################################################################################


def get_genesis():
    scheduler_timing = mw.col.sched._timing_today()
    next_day_starts_at = datetime.fromtimestamp(scheduler_timing.next_day_at)
    days_elapsed_since_genesis = timedelta(days=scheduler_timing.days_elapsed)
    today_started_at = next_day_starts_at - timedelta(days=1)
    return today_started_at - days_elapsed_since_genesis


@dataclass
class AnkiDate:
    epoch: float
    anki_days: int

    @classmethod
    def from_epoch(cls, epoch: float):
        delta = datetime.fromtimestamp(epoch) - get_genesis()
        return cls(epoch, delta.days)
