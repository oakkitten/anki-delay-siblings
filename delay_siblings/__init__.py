# -*- coding: utf-8 -*-

# Copyright (c) 2018-2022 oakkitten
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# When reviewing a card, reschedule siblings of the current card if they appear too close.
# Especially useful when reviewing a deck that wasn't touched for a while.

# For reference: https://github.com/ankidroid/Anki-Android/wiki/Database-Structure
# To get some type checking, see https://github.com/ankitects/anki-typecheck


import random
from contextlib import suppress
from dataclasses import dataclass

from anki.cards import Card
from anki.utils import strip_html
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
def get_siblings(card: Card) -> list[Card]:
    card_ids = card.col.db.list("select id from cards where nid=? and id!=?",
                                card.nid, card.id)
    return [mw.col.get_card(card_id) for card_id in card_ids]


@dataclass
class Reschedule:
    sibling: Card
    old_absolute_due: int
    new_absolute_due: int


def get_pending_sibling_reschedules(card: Card) -> list[Reschedule]:
    today = get_today()
    siblings = get_siblings(card)
    cards_per_note = len(siblings) + 1

    for sibling in siblings:
        if is_card_reviewing(sibling) and not is_card_suspended(sibling):
            sibling_interval = sibling.ivl
            old_relative_due = get_card_absolute_due(sibling) - today
            new_relative_due_min, new_relative_due_max = \
                calculate_new_relative_due_range(sibling_interval, cards_per_note)

            if new_relative_due_min > 0 and new_relative_due_min > old_relative_due:
                new_relative_due = random.randint(new_relative_due_min, new_relative_due_max)
                yield Reschedule(sibling, today + old_relative_due, today + new_relative_due)


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
    messages = []

    for reschedule in get_pending_sibling_reschedules(card):
        set_card_absolute_due(reschedule.sibling, reschedule.new_absolute_due)
        remove_card_from_current_review_queue(reschedule.sibling)

        if (
            reschedule.new_absolute_due - max(reschedule.old_absolute_due, today) >= 14
            or not config.current_deck.quiet
        ):
            messages.append(get_reschedule_message(reschedule))

    if messages:
        tooltip(f"<span style='color: green'>{'<hr>'.join(messages)}</span>")


########################################################################## configuration


ENABLED = "enabled"
QUIET = "quiet"


class DeckConfig:
    def __init__(self, cfg, deck_id):
        self.config = cfg
        self.deck_data = cfg.data.setdefault(str(deck_id), {ENABLED: False, QUIET: False})

    @staticmethod
    def make_property(name):
        def getter(self):
            return self.deck_data[name]

        def setter(self, value):
            self.deck_data[name] = value
            self.config.save()

        return property(getter, setter)

    enabled = make_property(ENABLED)
    quiet = make_property(QUIET)


class Config:
    def __init__(self):
        self.data = mw.addonManager.getConfig(__name__)
        self.current_deck = DeckConfig(self.data, 0)

    def save(self):
        mw.addonManager.writeConfig(__name__, self.data)

    def set_current_deck_id(self, deck_id):
        self.current_deck = DeckConfig(self.data, deck_id)

config = Config()


################################################################################## menus


def flip_enabled(_key):
    config.current_deck.enabled = not config.current_deck.enabled
    menu_quiet.setEnabled(config.current_deck.enabled)


def flip_quiet(_key):
    config.current_deck.quiet = not config.current_deck.quiet


menu_enabled = QAction("Enable sibling delaying",
                       mw, checkable=True, enabled=False)
menu_enabled.triggered.connect(flip_enabled)

menu_quiet = QAction("Don’t notify if a card is delayed by less than 2 weeks",
                     mw, checkable=True, enabled=False)
menu_quiet.triggered.connect(flip_quiet)

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


################################################################################## hooks


gui_hooks.reviewer_did_show_answer.append(reviewer_did_show_answer)
gui_hooks.state_did_change.append(state_did_change)
