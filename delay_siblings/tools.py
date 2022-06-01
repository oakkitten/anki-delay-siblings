from contextlib import suppress
from datetime import datetime, timedelta
from typing import Sequence, Callable

from anki.cards import Card
from anki.consts import QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV as CARD_TYPE_REVIEWING
from aqt import mw
from aqt.qt import QAction

try:
    from anki.utils import html_to_text_line
except ImportError:
    from anki.utils import htmlToTextLine as html_to_text_line  # noqa


def sorted_by_value(dictionary):
    return dict(sorted(dictionary.items(), key=lambda item: item[1]))


########################################################################################


def get_current_deck_id() -> int:
    return mw.col.decks.get_current_id()


def is_card_suspended(card: Card) -> bool:
    return card.queue == QUEUE_TYPE_SUSPENDED


def is_card_reviewing(card: Card) -> bool:
    return card.type == CARD_TYPE_REVIEWING


def is_card_in_a_filtered_deck(card: Card) -> bool:
    return card.odue != 0 and card.odid != 0


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


# A tiny helper for menu items, since type checking is broken there
def checkable(title: str, on_click: Callable[[bool], None]) -> QAction:
    action = QAction(title, mw, checkable=True)  # noqa
    action.triggered.connect(on_click)  # noqa
    return action


########################################################################################


# Anki keeps track of time as follows:
#  * learning cards have due in epoch;
#  * reviewing card have due in days, 0 being deck creation day
#    (called “Anki days” in this project)
#  * revlog stores review times in epoch regardless
#
# Days don't start at midnight, but by the hour of the “Next day starts at” setting.
# It seems that since user can change it,
# it is not possible to entirely reliably map historic precise time to Anki time.


def get_anki_today() -> int:
    return mw.col.sched.today


# This is based on the most recent “next day starts at” setting,
# otherwise nearly the same as the result of `select crt from col`.
def get_collection_genesis_datetime() -> datetime:
    scheduler_timing = mw.col.sched._timing_today()
    next_day_starts_at = datetime.fromtimestamp(scheduler_timing.next_day_at)
    days_elapsed_since_genesis = timedelta(days=scheduler_timing.days_elapsed)
    today_started_at = next_day_starts_at - timedelta(days=1)
    return today_started_at - days_elapsed_since_genesis


def epoch_to_anki_days(epoch: float) -> int:
    delta = datetime.fromtimestamp(epoch) - get_collection_genesis_datetime()
    return delta.days
