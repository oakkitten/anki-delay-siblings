# -*- coding: utf-8 -*-


# Copyright (c) 2018-2020 oakkitten
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


# when reviewing a card, reschedule siblings of the current card if they appear too close
# especially useful when reviewing a deck that wasn't touched for a while

# https://github.com/ankidroid/Anki-Android/wiki/Database-Structure

# to get some type checking, see https://github.com/ankitects/anki-typecheck
from typing import List, Dict
from contextlib import suppress
import random

from anki.cards import Card
from anki.hooks import addHook
from anki.utils import stripHTML

# noinspection PyUnresolvedReferences
from aqt.qt import QAction
from aqt import mw
from aqt.utils import tooltip

ENABLED = 'sibling_delaying_enabled'
QUIET = 'sibling_delaying_quiet'

# see the sources of both anki/sched.py and anki/schedv2.py:
# card types: 0=new, 1=lrn, 2=rev, 3=relrn
# queue types: 0=new/cram, 1=lrn, 2=rev, 3=day lrn, -1=suspended, -2=buried
CARD_TYPE_REVIEWING = 2
QUEUE_TYPE_SUSPENDED = -1

# current deck, only used for storing settings
deck: Dict

# noinspection PyPep8Naming
def showAnswer():
    if not deck[ENABLED]:
        return

    siblings = get_siblings(mw.reviewer.card)
    cards_per_note = len(siblings) + 1

    out: List[str] = []
    for sibling in siblings:
        # ignore suspended cards and new/learning cards
        if sibling.type != CARD_TYPE_REVIEWING or sibling.queue == QUEUE_TYPE_SUSPENDED:
            continue

        # get due regardless of whether the deck is filtered or not
        # our due is the number of days in which the card is due (-1 if yesterday, +1 if tomorrow)
        filtered = sibling.odue != 0 and sibling.odid != 0
        due = sibling.odue if filtered else sibling.due
        due -= mw.col.sched.today
        interval = sibling.ivl

        # when the card is going to appear. 0 is today
        when = due if due > 0 else 0

        min_new_when, max_new_when = calc_new_when(interval, cards_per_note)

        if min_new_when > when:
            new_when = random.randint(min_new_when, max_new_when)
            reschedule(sibling, new_when + mw.col.sched.today, filtered)

            if (new_when - when) >= 14 or not deck[QUIET]:
                question = stripHTML(sibling.q())
                out.append(f"Sibling: {question} (interval: <b>{interval}</b> days)<br>"
                           f"Rescheduling: <b>{due}</b> → <span style='color: crimson'><b>{new_when}</b></span> "
                           f"days after today")

    if out:
        tooltip("<span style='color: green'>" + "<hr>".join(out) + "</span>")


# see https://github.com/ankitects/anki/blob/6ecf2ffa2c46f2501ddbc3fd778035e715399a98/pylib/anki/sched.py#L985-L986
# noinspection PyShadowingBuiltins
def get_siblings(card: Card) -> List[Card]:
    return [card.col.getCard(id) for id in card.col.db.list("select id from cards where nid=? and id!=?",
                                                            card.nid, card.id)]


# delay ranges for 2; 3 cards per note:
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
def calc_new_when(interval: int, cards_per_note: int):
    f = (24.0 * interval + 310) ** 0.4 - 10
    f = f * 2 / cards_per_note 
    return int(round(f)), int(round(f * 1.3))


# reschedule a card and remove it from the current queue, if it is there
# this method relies on a protected member; see
# https://github.com/ankitects/anki/blob/351d8a309f7d3c0cae7f818313b1a0e7aac4408a/pylib/anki/sched.py#L566-L573
# noinspection PyProtectedMember
def reschedule(sibling: Card, due: int, filtered: bool):
    if filtered:
        sibling.odue = due
    else:
        sibling.due = due
    sibling.flushSched()

    with suppress(AttributeError, ValueError):
        mw.col.sched._revQueue.remove(sibling.id)

########################################################################################################################


def flip_enabled(_key):
    enabled = deck[ENABLED] = not deck[ENABLED]
    menu_quiet.setEnabled(enabled)


def flip_quiet(_key):
    deck[QUIET] = not deck[QUIET]


mw.form.menuTools.addSeparator()

menu_enabled = QAction("Enable sibling delaying", mw, checkable=True, enabled=False)
menu_enabled.triggered.connect(flip_enabled)
mw.form.menuTools.addAction(menu_enabled)

menu_quiet = QAction("Don’t notify if a card is delayed by less than 2 weeks", mw, checkable=True, enabled=False)
menu_quiet.triggered.connect(flip_quiet)
mw.form.menuTools.addAction(menu_quiet)


# noinspection PyPep8Naming
def afterStateChange(next_state: str, _prev, *_args):
    if next_state in ["overview", "review"]:
        global deck
        deck = mw.col.decks.current()
        enabled = deck.setdefault(ENABLED, False)
        quiet = deck.setdefault(QUIET, False)
        menu_enabled.setEnabled(True)
        menu_enabled.setChecked(enabled)
        menu_quiet.setChecked(quiet)
        menu_quiet.setEnabled(enabled)
    else:
        menu_enabled.setEnabled(False)
        menu_enabled.setChecked(False)
        menu_quiet.setEnabled(False)
        menu_quiet.setChecked(False)


addHook('showAnswer', showAnswer)
addHook('afterStateChange', afterStateChange)
