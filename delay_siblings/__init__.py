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
import datetime

from typing import List, Dict
from contextlib import suppress
import random

from anki.cards import Card
from anki.hooks import addHook
from anki.utils import stripHTML

# noinspection PyUnresolvedReferences
from aqt.qt import QAction, QMessageBox, QDialog, QGridLayout
from aqt import mw
from aqt.utils import tooltip, showInfo

ENABLED = 'enabled'
QUIET = 'quiet'

# see the sources of both anki/sched.py and anki/schedv2.py:
# card types: 0=new, 1=lrn, 2=rev, 3=relrn
# queue types: 0=new/cram, 1=lrn, 2=rev, 3=day lrn, -1=suspended, -2=buried
CARD_TYPE_REVIEWING = 2
CARD_TYPE_NEW = 0
QUEUE_TYPE_SUSPENDED = -1

global_config: Dict
current_deck_config: Dict


# noinspection PyPep8Naming
def showAnswer():
    if not current_deck_config[ENABLED]:
        return

    out = delay_siblings(mw.reviewer.card)

    if out:
        text_changes = [f"Sibling: {sibling['question']} (interval: <b>{sibling['interval']}</b> days)<br>"
                        f"Rescheduling: <b>{sibling['original_due']}</b> → <span style='color: crimson'><b>{sibling['new_due']}</b></span> "
                        f"days after today" for sibling in out]
        tooltip("<span style='color: green'>" + "<hr>".join(text_changes) + "</span>", 10000)


def delay_siblings(card: Card) -> List[Dict]:
    """
    Delays siblings for a given card.
    Returns string for tooltip notification.
    """
    siblings = get_siblings(card)
    cards_per_note = len(siblings) + 1

    # The two possible reference dates - either when the card will be due (in its original deck) or its latest review
    if card.odue != 0 and card.odid != 0:  # i.e. if in filtered deck
        card_due = card.odue
    else:
        card_due = card.due
    card_due = max(mw.col.sched.today, card_due)  # Treat overdue cards as due today
    latest_review = int((mw.col.db.first(f"SELECT MAX(id) FROM revlog WHERE cid={card.id};")[0]/1000 - mw.col.crt)/86400)

    assert card_due > latest_review, f"Latest review ({latest_review - mw.col.sched.today}) is after" \
                                     f" due date({card_due - mw.col.sched.today}) for card {card.id}" \
                                     f", doesn't make sense; {card.odue = }, {card.due = }, {mw.col.sched.today = }"

    changes: List[Dict] = []
    for sibling in siblings:
        # ignore suspended cards and new/learning cards
        if sibling.type != CARD_TYPE_REVIEWING or sibling.queue == QUEUE_TYPE_SUSPENDED:
            continue

        # get due regardless of whether the deck is filtered or not
        filtered = sibling.odue != 0 and sibling.odid != 0
        original_due = sibling.odue if filtered else sibling.due

        interval = sibling.ivl
        min_new_when, max_new_when = calc_new_when(interval, cards_per_note)
        delay = random.randint(min_new_when, max_new_when)

        if card_due <= original_due < card_due + min_new_when:
            new_due = card_due + delay
            print('Delaying due to due date')
        elif latest_review <= original_due < latest_review + min_new_when:
            new_due = latest_review + delay
            print('Delaying due to review')
        else:
            continue

        print(f'{original_due=}, {new_due=}, {min_new_when=}, {max_new_when=}, {card_due=}, {latest_review=}')

        reschedule(sibling, new_due, filtered)

        if (new_due - original_due) >= 14 or not current_deck_config[QUIET]:
            question = stripHTML(sibling.question())[:50]
            changes.append({'question': question,
                            'interval': interval,
                            'original_due': original_due - mw.col.sched.today,
                            'new_due': new_due - mw.col.sched.today,
                            'sibling': sibling})

    return changes


# see https://github.com/ankitects/anki/blob/6ecf2ffa2c46f2501ddbc3fd778035e715399a98/pylib/anki/sched.py#L985-L986
# noinspection PyShadowingBuiltins
def get_siblings(card: Card) -> List[Card]:
    return [card.col.getCard(id) for id in card.col.db.list("select id from cards where nid=? and id!=?",
                                                            card.nid, card.id)]


def pre_delay():
    change_reports = []
    for deck in mw.col.decks.all():
        load_current_deck_config(deck["id"])
        if current_deck_config[ENABLED]:
            cards = [mw.col.getCard(card_id) for card_id in mw.col.find_cards(f'-is:new -is:suspended "deck:{deck["name"]}"')]
            cards.sort(key=lambda card: card.due)
            cards = [card.id for card in cards]
            for card_id in cards:
                card = mw.col.getCard(card_id)
                changes = delay_siblings(card)
                if changes:
                    note = mw.col.getNote(card.nid)
                    note_type = list(filter(lambda model: model['id'] == note.mid, mw.col.models.all()))[0]
                    sort_field = note_type['sortf']
                    note_name = note.fields[sort_field]
                    if note_type['tmpls'][0]['name'] == 'Cloze' and len(note_type['tmpls']) == 1:
                        origin_template_name = f'Cloze {card.ord + 1}'
                        changed_templates = [f'Cloze {change["sibling"].ord + 1}' for change in changes]
                    else:
                        origin_template_name = \
                            list(filter(lambda template: template['ord'] == card.ord, note_type['tmpls']))[0]['name']
                        changed_templates = [list(filter(lambda template: template['ord'] == change['sibling'].ord, note_type['tmpls']))[0]['name'] for change in changes]
                    card_due = card.due if card.odue == 0 and card.odid == 0 else card.odue
                    text_changes = '\n - '.join([f'{template} (ivl. {change["interval"]}) {change["original_due"]} -> {change["new_due"]} days from today' for template, change in zip(changed_templates, changes)])
                    change_report = f'{note_type["name"]} -- {note_name} -- {origin_template_name} (due in {card_due - mw.col.sched.today} days) delayed: \n - {text_changes}'
                    change_reports.append(change_report)
                    print(change_report)
                    
    if change_reports:
        message_box = QMessageBox()
        message_box.setWindowTitle('Success')
        message_box.setText('Delays have been successfully appled.')
        message_box.setDetailedText('\n'.join(change_reports))
        message_box.exec()
    else:
        message_box = QMessageBox()
        message_box.setWindowTitle('Success')
        message_box.setText('No delays were required.')
        message_box.exec()


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
    sibling.flush()

    with suppress(AttributeError, ValueError):
        mw.col.sched._revQueue.remove(sibling.id)

########################################################################################################################

def flip_enabled(_key):
    enabled = current_deck_config[ENABLED] = not current_deck_config[ENABLED]
    menu_quiet.setEnabled(enabled)
    save_global_config()


def flip_quiet(_key):
    current_deck_config[QUIET] = not current_deck_config[QUIET]
    save_global_config()


mw.form.menuTools.addSeparator()

menu_enabled = QAction("Enable sibling delaying", mw, checkable=True, enabled=False)
menu_enabled.triggered.connect(flip_enabled)
mw.form.menuTools.addAction(menu_enabled)

menu_quiet = QAction("Don’t notify if a card is delayed by less than 2 weeks", mw, checkable=True, enabled=False)
menu_quiet.triggered.connect(flip_quiet)
mw.form.menuTools.addAction(menu_quiet)

pre_delay_action = QAction("Pre-delay future cards")
pre_delay_action.triggered.connect(pre_delay)
mw.form.menuTools.addAction(pre_delay_action)

mw.form.menuTools.addSeparator()

########################################################################################################################

def load_global_config():
    global global_config
    global_config = mw.addonManager.getConfig(__name__)


def save_global_config():
    mw.addonManager.writeConfig(__name__, global_config)


def load_current_deck_config(deck_id: int):
    global current_deck_config
    current_deck_config = global_config.setdefault(str(deck_id), {})    # str() as json keys can't be numbers
    current_deck_config.setdefault(ENABLED, False)
    current_deck_config.setdefault(QUIET, False)


# noinspection PyPep8Naming
def afterStateChange(next_state: str, _prev, *_args):
    if next_state in ["overview", "review"]:
        load_current_deck_config(mw.col.decks.current()["id"])
        menu_enabled.setEnabled(True)
    else:
        load_current_deck_config(0)
        menu_enabled.setEnabled(False)
    menu_enabled.setChecked(current_deck_config[ENABLED])
    menu_quiet.setChecked(current_deck_config[QUIET])
    menu_quiet.setEnabled(current_deck_config[ENABLED])


load_global_config()
load_current_deck_config(0)

addHook('showAnswer', showAnswer)
addHook('afterStateChange', afterStateChange)
