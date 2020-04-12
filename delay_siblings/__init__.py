# -*- coding: utf-8 -*-


# Copyright (c) 2018 oakkitten
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

# noinspection PyUnresolvedReferences
from aqt import mw
# noinspection PyUnresolvedReferences
from aqt.qt import QAction
# noinspection PyUnresolvedReferences
from aqt.utils import tooltip
# noinspection PyUnresolvedReferences
from anki.hooks import addHook
# noinspection PyUnresolvedReferences
from anki.utils import intTime
import random

ENABLED = 'sibling_delaying_enabled'
QUIET = 'sibling_delaying_quiet'


# this method uses some protected members, one to display question without css, and one to modify current queue
# _getQA(): https://github.com/dae/anki/blob/554ff3d8d2ddd8f3e3f84b63b342cfac731712e5/anki/cards.py#L128
# _getRevCard: https://github.com/dae/anki/blob/554ff3d8d2ddd8f3e3f84b63b342cfac731712e5/anki/sched.py#L786-L789

# noinspection PyProtectedMember,PyPep8Naming
def showAnswer():
    if not deck[ENABLED]:
        return

    siblings = get_siblings(mw.reviewer.card)
    cards_per_note = len(siblings) + 1

    out = []
    for sibling in siblings:
        # ignore suspended cards and new/learning cards
        # type: 0=new, 1=learning, 2=due
        # queue: same as type, but -1=suspended, -2=user buried, -3=sched buried
        if sibling.type != 2 or sibling.queue == -1:
            continue

        # get due regardless of whether the deck is filtered or not
        # our due is the number of days in which the card is due (-1 if yesterday, +1 if tomorrow)
        filtered = sibling.odue != 0 and sibling.odid != 0
        due = sibling.odue if filtered else sibling.due
        due -= mw.col.sched.today
        interval = sibling.ivl
        question = sibling._getQA()['q']

        # when the card is going to appear. 0 is today
        when = due if due > 0 else 0

        min_new_when, max_new_when = calc_new_when(interval, cards_per_note)

        if min_new_when > when:
            new_when = random.randint(min_new_when, max_new_when)
            reschedule(sibling, new_when, filtered)
            try: mw.col.sched._revQueue.remove(sibling.id)
            except ValueError: pass
            if (new_when - when) >= 14 or not deck[QUIET]:
                out.append(u"Sibling: %s (interval: <b>%s</b> days)<br>" % (question, interval) +
                           u"Rescheduling: <b>%s</b> → <span style='color: crimson'><b>%s</b></span> days after today"
                           % (due, new_when))

    if out:
        tooltip(u"<span style='color: green'>" + "<hr>".join(out) + "</span>")


# noinspection PyShadowingBuiltins
def get_siblings(card):
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
def calc_new_when(interval, cards_per_note):
    f = (24.0 * interval + 310)**0.4 - 10
    f = f * 2 / cards_per_note 
    return int(round(f)), int(round(f * 1.3))


# reschedule a card. like reschedCards, but don't do anything except change the due time
# mod and usn are used for synchronization, i guess?
# https://github.com/dae/anki/blob/554ff3d8d2ddd8f3e3f84b63b342cfac731712e5/anki/sched.py#L1348-L1362
def reschedule(card, due, filtered):
    mw.col.db.execute("update cards set %s=?, mod=?, usn=? where id=?" % ("odue" if filtered else "due"), 
                      mw.col.sched.today + due, intTime(), mw.col.usn(), card.id)


########################################################################################################################


# noinspection PyUnusedLocal
def flip_enabled(key):
    enabled = deck[ENABLED] = not deck[ENABLED]
    menu_quiet.setEnabled(enabled)


# noinspection PyUnusedLocal
def flip_quiet(key):
    deck[QUIET] = not deck[QUIET]


mw.form.menuTools.addSeparator()

menu_enabled = QAction("Enable sibling delaying", mw, checkable=True, enabled=False)
menu_enabled.triggered.connect(flip_enabled)
mw.form.menuTools.addAction(menu_enabled)

menu_quiet = QAction(u"Don’t notify if a card is delayed by less than 2 weeks", mw, checkable=True, enabled=False)
menu_quiet.triggered.connect(flip_quiet)
mw.form.menuTools.addAction(menu_quiet)


# noinspection PyUnusedLocal,PyGlobalUndefined,PyPep8Naming,PyShadowingBuiltins
def afterStateChange(prev, next, *args):
    if next == "overview":
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
        menu_quiet.setEnabled(False)


addHook('showAnswer', showAnswer)
addHook('afterStateChange', afterStateChange)
