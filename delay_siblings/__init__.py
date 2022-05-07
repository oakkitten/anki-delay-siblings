# When reviewing a card, reschedule siblings of the current card if they appear too close.
# Especially useful when reviewing a deck that wasn't touched for a while.

# For reference: https://github.com/ankidroid/Anki-Android/wiki/Database-Structure


import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Sequence, Iterator

from anki.cards import Card
from anki.utils import stripHTML as strip_html  # Anki 2.1.49 doesn't have the new name
from anki.consts import QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV as CARD_TYPE_REVIEWING
from aqt.qt import QAction
from aqt import mw, gui_hooks
from aqt.utils import tooltip


# interval → ranges for 2; 3 cards per note:
#    0 →    0-0;   0-0
#    1 →    0-0;   0-0
#    2 →    1-1;   0-0
#    3 →    1-1;   1-1
#    4 →    1-1;   1-1
#    5 →    1-2;   1-1
#    6 →    2-2;   1-1
#    7 →    2-2;   1-2
#    8 →    2-3;   1-2
#    9 →    2-3;   2-2
#   10 →    2-3;   2-2
#   12 →    3-4;   2-3
#   14 →    3-4;   2-3
#   16 →    4-5;   2-3
#   18 →    4-5;   3-4
#   20 →    4-6;   3-4
#   30 →    6-8;   4-5
#   60 →  10-13;   7-9
#   90 →  13-17;  9-11
#  180 →  19-25; 13-17
#  360 →  28-37; 19-24
#  720 →  40-52; 27-35
# 1500 →  57-74; 38-49
# 3000 → 78-101; 52-67
# https://www.desmos.com/calculator/fnh882qnd1
def calculate_new_relative_due_range(interval: int, cards_per_note: int) -> (int, int):
    f = (24.0 * interval + 310) ** 0.4 - 10
    f = f * 2 / cards_per_note
    return int(round(f)), int(round(f * 1.3))


def is_card_suspended(card: Card) -> bool:
    return card.queue == QUEUE_TYPE_SUSPENDED

# todo also reschedule learning/relearning cards?
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


# see https://github.com/ankitects/anki/blob/6ecf2ffa/pylib/anki/sched.py#L985-L986
def get_siblings(card: Card) -> "list[Card]":
    card_ids = card.col.db.list("select id from cards where nid=? and id!=?",
                                card.nid, card.id)
    return [mw.col.get_card(card_id) for card_id in card_ids]


@dataclass
class Reschedule:
    sibling: Card
    old_absolute_due: int
    new_absolute_due: int


def get_pending_reschedules(siblings: Sequence[Card], last_review_day: int) -> Iterator[Reschedule]:
    cards_per_note = len(siblings) + 1

    for sibling in siblings:
        if not is_card_reviewing(sibling) or is_card_suspended(sibling):
            continue

        sibling_interval = sibling.ivl
        old_absolute_due = get_card_absolute_due(sibling)
        old_relative_due = old_absolute_due - last_review_day
        new_relative_due_min, new_relative_due_max = \
            calculate_new_relative_due_range(sibling_interval, cards_per_note)

        if new_relative_due_min > 0 and new_relative_due_min > old_relative_due:
            new_relative_due = random.randint(new_relative_due_min, new_relative_due_max)
            new_absolute_due = last_review_day + new_relative_due
            yield Reschedule(sibling, old_absolute_due, new_absolute_due)


def get_reschedule_message(reschedule: Reschedule):
    question = strip_html(reschedule.sibling.question())
    today = get_today()
    interval = reschedule.sibling.ivl

    return (
        f"Sibling: {question} (interval: <b>{interval}</b> days)<br>"
        f"Rescheduling: <b>{reschedule.old_absolute_due - today}</b> → "
        f"<span style='color: crimson'><b>{reschedule.new_absolute_due - today}</b></span> "
        f"days after today"
    )


def reviewer_did_show_answer(card: Card):
    if not config.current_deck.enabled:
        return

    today = get_today()
    siblings = get_siblings(card)
    messages = []

    for reschedule in get_pending_reschedules(siblings, last_review_day=today):
        set_card_absolute_due(reschedule.sibling, reschedule.new_absolute_due)
        remove_card_from_current_review_queue(reschedule.sibling)

        if (
            reschedule.new_absolute_due - max(reschedule.old_absolute_due, today) >= 14
            or not config.current_deck.quiet
        ):
            messages.append(get_reschedule_message(reschedule))

    if messages:
        tooltip(f"<span style='color: green'>{'<hr>'.join(messages)}</span>")


########################################################################################
####################################################################### delay after sync
########################################################################################


@dataclass
class AnkiDate:
    epoch: int
    anki_days: int

    @classmethod
    def from_epoch(cls, epoch_timestamp):
        from datetime import datetime, timedelta
        timing = mw.col.sched._timing_today()

        today_started_at = datetime.fromtimestamp(timing.next_day_at) - timedelta(days=1)
        genesis = today_started_at - timedelta(days=timing.days_elapsed)
        delta = datetime.fromtimestamp(epoch_timestamp) - genesis

        return cls(epoch_timestamp, delta.days)


# card id to last review time, the latter in epoch milliseconds
IdToLastReview = "dict[int, int]"


def sorted_by_value(dictionary):
    return dict(sorted(dictionary.items(), key=lambda item: item[1]))


def calculate_sync_diff(before: IdToLastReview, after: IdToLastReview) -> IdToLastReview:
    result = {}

    for card_id, last_review_after in after.items():
        if card_id in before:
            last_review_before = before[card_id]
            if last_review_before == last_review_after:
                continue
            if last_review_before > last_review_after:
                raise Exception(
                    f"After sync, mod of card {card_id} unexpectedly changed"
                    f" from {last_review_before} to a lower value {last_review_before}"
                )
        result[card_id] = last_review_after

    return result


def get_pending_sync_diff_reschedules(sync_diff: IdToLastReview):
    sync_diff = sorted_by_value(sync_diff)

    today = get_today()
    result = []

    while sync_diff:
        card_id, last_review_time = sync_diff.popitem()  # last, most recent review
        siblings = get_siblings(mw.col.get_card(card_id))

        reschedules = get_pending_reschedules(
            siblings=siblings,
            last_review_day=AnkiDate.from_epoch(last_review_time / 1000).anki_days,
        )

        for reschedule in reschedules:
            if reschedule.new_absolute_due > today:
                result.append(reschedule)

        for sibling in siblings:
            with suppress(KeyError):
                sync_diff.pop(sibling.id)

    return result


def run_reschedules(reschedules: Sequence[Reschedule]):
    for reschedule in reschedules:
        set_card_absolute_due(reschedule.sibling, reschedule.new_absolute_due)


def perform_historic_delaying(before: IdToLastReview, after: IdToLastReview):
    sync_diff = calculate_sync_diff(before, after)
    reschedules = list(get_pending_sync_diff_reschedules(sync_diff))
    run_reschedules(reschedules)

    print(f">> before {before}")
    print(f">> after {after}")
    print(f">> sync_diff {sync_diff}")
    print(f">> reschedules {reschedules}")


########################################################################################


# noinspection PyTypeChecker
def get_card_id_to_last_review_time_for_all_cards() -> IdToLastReview:
    return dict(mw.col.db.all("""
        select revlog.cid, max(revlog.id)
        from (revlog inner join cards on cards.id = revlog.cid)
        group by revlog.cid
    """))


id_to_last_review_before: IdToLastReview = {}


@gui_hooks.sync_will_start.append
def sync_will_start():
    if config.offer_to_delay_after_sync:
        global id_to_last_review_before
        id_to_last_review_before = get_card_id_to_last_review_time_for_all_cards()


@gui_hooks.sync_did_finish.append
def sync_did_finish():
    if config.offer_to_delay_after_sync:
        global id_to_last_review_before
        id_to_last_review_after = get_card_id_to_last_review_time_for_all_cards()
        perform_historic_delaying(id_to_last_review_before, id_to_last_review_after)
        id_to_last_review_before = {}


########################################################################################
########################################################################## configuration
########################################################################################


ENABLED = "enabled"
QUIET = "quiet"
OFFER_TO_DELAY_AFTER_SYNC = "offer_to_delay_after_sync"


def make_property(name):
    def getter(self):
        return self.deck_data[name]

    def setter(self, value):
        self.deck_data[name] = value
        self.config.save()

    return property(getter, setter)

class DeckConfig:
    def __init__(self, cfg, deck_id):
        self.config = cfg
        self.deck_data = cfg.data.setdefault(str(deck_id), {ENABLED: False, QUIET: False})

    enabled = make_property(ENABLED)
    quiet = make_property(QUIET)


class Config:
    def __init__(self):
        self.data = mw.addonManager.getConfig(__name__) or {}
        self.current_deck = DeckConfig(self, 0)

    def save(self):
        mw.addonManager.writeConfig(__name__, self.data)

    def set_current_deck_id(self, deck_id):
        self.current_deck = DeckConfig(self, deck_id)

    @property
    def offer_to_delay_after_sync(self):
        return self.data.get(OFFER_TO_DELAY_AFTER_SYNC, False)

config = Config()


######################################################################## menus and hooks


def flip_enabled(_key):
    config.current_deck.enabled = not config.current_deck.enabled
    menu_quiet.setEnabled(config.current_deck.enabled)


def flip_quiet(_key):
    config.current_deck.quiet = not config.current_deck.quiet


menu_enabled = QAction("Enable sibling delaying",  # noqa
                       mw, checkable=True, enabled=False)  # noqa
menu_enabled.triggered.connect(flip_enabled)  # noqa

menu_quiet = QAction("Don’t notify if a card is delayed by less than 2 weeks",  # noqa
                     mw, checkable=True, enabled=False)  # noqa
menu_quiet.triggered.connect(flip_quiet)  # noqa

mw.form.menuTools.addSeparator()
mw.form.menuTools.addAction(menu_enabled)
mw.form.menuTools.addAction(menu_quiet)


def state_did_change(next_state: str, _previous_state):
    if next_state in ["overview", "review"]:
        config.set_current_deck_id(mw.col.decks.get_current_id())
        menu_enabled.setEnabled(True)
    else:
        config.set_current_deck_id(0)
        menu_enabled.setEnabled(False)
    menu_enabled.setChecked(config.current_deck.enabled)
    menu_quiet.setChecked(config.current_deck.quiet)
    menu_quiet.setEnabled(config.current_deck.enabled)


gui_hooks.reviewer_did_show_answer.append(reviewer_did_show_answer)
gui_hooks.state_did_change.append(state_did_change)
