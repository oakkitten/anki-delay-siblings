# When reviewing a card, reschedule siblings of the current card if they appear too close.
# Especially useful when reviewing a deck that wasn't touched for a while.

# For reference: https://github.com/ankidroid/Anki-Android/wiki/Database-Structure


import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Sequence, Iterator

from anki.cards import Card
from anki.utils import stripHTML as strip_html  # Anki 2.1.49 doesn't have the new name
from aqt.qt import QAction, QDialog
from aqt import mw, gui_hooks
from aqt.utils import tooltip

from .configuration import Config, run_on_configuration_change
from .delay_after_sync_dialog import DelayAfterSyncDialog
from .tools import (
    is_card_reviewing,
    is_card_suspended,
    get_card_absolute_due,
    get_anki_today,
    get_siblings,
    set_card_absolute_due,
    remove_card_from_current_review_queue,
    epoch_to_anki_days,
    sorted_by_value,
)


# Interval → ranges for 2; 3 cards per note:
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


@dataclass
class Delay:
    sibling: Card
    old_absolute_due: int
    new_absolute_due: int


def get_delays(siblings: Sequence[Card], rescheduling_day: int) -> Iterator[Delay]:
    cards_per_note = len(siblings) + 1

    for sibling in siblings:
        if not is_card_reviewing(sibling) or is_card_suspended(sibling):
            continue

        sibling_interval = sibling.ivl
        old_absolute_due = get_card_absolute_due(sibling)
        old_relative_due = old_absolute_due - rescheduling_day
        new_relative_due_min, new_relative_due_max = \
            calculate_new_relative_due_range(sibling_interval, cards_per_note)

        if new_relative_due_min > 0 and new_relative_due_min > old_relative_due:
            new_relative_due = random.randint(new_relative_due_min, new_relative_due_max)
            new_absolute_due = rescheduling_day + new_relative_due
            yield Delay(sibling, old_absolute_due, new_absolute_due)


########################################################################################
############################################################################### reviewer
########################################################################################


def get_delayed_message(delay: Delay):
    question = strip_html(delay.sibling.question())
    today = get_anki_today()
    interval = delay.sibling.ivl

    return (
        f"Sibling: {question} (interval: <b>{interval}</b> days)<br>"
        f"Rescheduling: <b>{delay.old_absolute_due - today}</b> → "
        f"<span style='color: crimson'><b>{delay.new_absolute_due - today}</b></span> "
        f"days after today"
    )


@gui_hooks.reviewer_did_show_answer.append
def reviewer_did_show_answer(card: Card):
    if not config.enabled_for_current_deck:
        return

    today = get_anki_today()
    siblings = get_siblings(card)
    messages = []

    for delay in get_delays(siblings, rescheduling_day=today):
        set_card_absolute_due(delay.sibling, delay.new_absolute_due)
        remove_card_from_current_review_queue(delay.sibling)

        if (
            delay.new_absolute_due - max(delay.old_absolute_due, today) >= 14
            or not config.quiet
        ):
            messages.append(get_delayed_message(delay))

    if messages:
        tooltip(f"<span style='color: green'>{'<hr>'.join(messages)}</span>")


########################################################################################
####################################################################### delay after sync
########################################################################################


# Card id to last review time, the latter in epoch milliseconds
IdToLastReview = "dict[int, int]"


def calculate_sync_diff(before: IdToLastReview, after: IdToLastReview) -> IdToLastReview:
    result = {}

    for card_id, last_review_after in after.items():
        if card_id in before:
            last_review_before = before[card_id]
            if last_review_before == last_review_after:
                continue
            if last_review_before > last_review_after:
                raise Exception(
                    f"After sync, last review of {card_id} unexpectedly changed"
                    f" from {last_review_before} to a lower value {last_review_before}"
                )
        result[card_id] = last_review_after

    return result


def calculate_delays_after_sync(sync_diff: IdToLastReview) -> Iterator[Delay]:
    sync_diff = sorted_by_value(sync_diff)
    today = get_anki_today()

    while sync_diff:
        card_id, last_review_time = sync_diff.popitem()  # last, most recent review
        siblings = get_siblings(mw.col.get_card(card_id))
        last_review_day = epoch_to_anki_days(last_review_time / 1000)
        delays = get_delays(siblings, rescheduling_day=last_review_day)

        for delay in delays:
            if delay.new_absolute_due > today:
                yield delay

        for sibling in siblings:
            with suppress(KeyError):
                sync_diff.pop(sibling.id)


def perform_historic_delaying(before: IdToLastReview, after: IdToLastReview):
    sync_diff = calculate_sync_diff(before, after)
    delays = list(calculate_delays_after_sync(sync_diff))

    # print(f":: {before=}")
    # print(f":: {after=}")
    # print(f":: {sync_diff=}")
    # print(f":: {delays=}")

    if delays:
        dialog = DelayAfterSyncDialog()
        dialog.set_delays(delays)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # print(f":: executing")
            for delay in delays:
                set_card_absolute_due(delay.sibling, delay.new_absolute_due)


########################################################################################


# noinspection PyTypeChecker
def get_card_id_to_last_review_time_for_all_cards() -> IdToLastReview:
    return dict(mw.col.db.all(f"""
        select revlog.cid, max(revlog.id)
        from (revlog inner join cards on cards.id = revlog.cid)
        where cards.did in ({",".join(config.enabled_for_deck_ids)})
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
################################################################ menus and configuration
########################################################################################


config = Config()
config.load()


def flip_enabled(checked):
    config.enabled_for_current_deck = checked

def flip_quiet(checked):
    config.quiet = checked

def flip_offer_to_delay_after_sync(checked):
    config.offer_to_delay_after_sync = checked


menu_enabled = QAction("Enable sibling delaying for this deck", mw, checkable=True, enabled=False)  # noqa
menu_enabled.triggered.connect(flip_enabled)  # noqa

menu_quiet = QAction("Don’t notify if a card is delayed by less than 2 weeks", mw, checkable=True)  # noqa
menu_quiet.triggered.connect(flip_quiet)  # noqa

menu_offer_to_delay_after_sync = QAction("Offer to delay after sync, if enabled for deck", mw, checkable=True)  # noqa
menu_offer_to_delay_after_sync.triggered.connect(flip_offer_to_delay_after_sync)  # noqa

mw.form.menuTools.addSeparator()
mw.form.menuTools.addAction(menu_enabled)
menu_for_all_decks = mw.form.menuTools.addMenu("For all decks")
menu_for_all_decks.addAction(menu_quiet)
menu_for_all_decks.addAction(menu_offer_to_delay_after_sync)


def adjust_menu():
    if mw.col is not None:
        menu_enabled.setEnabled(mw.state in ["overview", "review"])
        menu_enabled.setChecked(config.enabled_for_current_deck)
        menu_quiet.setChecked(config.quiet)
        menu_offer_to_delay_after_sync.setChecked(config.offer_to_delay_after_sync)


@gui_hooks.state_did_change.append
def state_did_change(_next_state, _previous_state):
    adjust_menu()


@run_on_configuration_change
def configuration_changed():
    config.load()
    adjust_menu()
