import datetime
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Sequence

import aqt
from _pytest.monkeypatch import MonkeyPatch
from anki.cards import Card
from anki.collection import Collection
from anki.notes import Note

anki_version = tuple(int(segment) for segment in aqt.appVersion.split("."))


def get_collection() -> Collection:
    return aqt.mw.col


def get_deck_ids() -> list[int]:
    return [item.id for item in get_collection().decks.all_names_and_ids()]


def get_model_ids() -> list[int]:
    return [item.id for item in get_collection().models.all_names_and_ids()]


@dataclass
class CardDescription:
    name: str
    front: str
    back: str


def create_model(model_name: str, field_names: Sequence[str], card_descriptions: Sequence[CardDescription]) -> int:
    models = get_collection().models
    model = models.new(model_name)

    for field_name in field_names:
        field = models.new_field(field_name)
        models.add_field(model, field)

    for card_description in card_descriptions:
        template = models.new_template(card_description.name)
        template["qfmt"] = card_description.front
        template["afmt"] = card_description.back
        models.add_template(model, template)

    return models.add(model).id


def create_deck(deck_name: str) -> int:
    return get_collection().decks.id(deck_name)


def add_note(model_name: str, deck_name: str, fields: dict[str, str], tags: Sequence[str] = None) -> int:
    collection = get_collection()

    model_id = collection.models.id_for_name(model_name)
    deck_id = collection.decks.id_for_name(deck_name)
    note = Note(collection, model_id)

    for field_name, field_value in fields.items():
        note[field_name] = field_value

    if tags is not None:
        note.tags = list(tags)

    collection.add_note(note, deck_id)
    return note.id


def set_scheduler(version: int):
    if version == 2:
        get_collection().set_v3_scheduler(enabled=False)
    if version == 3:
        get_collection().set_v3_scheduler(enabled=True)


def get_scheduler_card():
    return get_collection().sched.getCard()


AGAIN = 0
HARD = 1
GOOD = 2
EASY = 3


@contextmanager
def clock_changed_to(epoch_seconds: float):
    days_delta = datetime.timedelta(seconds=epoch_seconds - time.time()).days

    with MonkeyPatch().context() as monkey:
        monkey.setattr(time, "time", lambda: epoch_seconds)
        monkey.setattr(get_collection().sched.__class__, "today", aqt.mw.col.sched.today + days_delta)
        yield


def minutes(n):
    return n * 60


def days(n):
    return n * 24 * 60 * 60


@contextmanager
def clock_set_back(*, by_days: int):
    epoch_seconds = int(time.time()) - days(by_days)
    with clock_changed_to(epoch_seconds):
        yield epoch_seconds


def answer_card(card: Card, answer: int):
    get_collection().sched.answerCard(card, answer)
