import datetime
import time
from contextlib import contextmanager
from dataclasses import dataclass
from textwrap import dedent
from typing import Sequence

import aqt
from _pytest.monkeypatch import MonkeyPatch
from anki.cards import Card
from anki.collection import Collection
from anki.decks import DeckId, FilteredDeckConfig
from anki.notes import Note
from anki.utils import strip_html

anki_version = tuple(int(segment) for segment in aqt.appVersion.split("."))

say = print


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


def create_model(model_name: str, field_names: Sequence[str],
                 card_descriptions: Sequence[CardDescription]) -> int:
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


def add_note(model_name: str, deck_name: str, fields: dict[str, str],
             tags: Sequence[str] = None) -> int:
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


def get_card(card_id: int) -> Card:
    return aqt.mw.col.get_card(card_id)


################################################################################ reviews


@contextmanager
def clock_changed_to(epoch_seconds: float):
    days_delta = datetime.timedelta(seconds=epoch_seconds - time.time()).days

    with MonkeyPatch().context() as monkey:
        monkey.setattr(time, "time", lambda: epoch_seconds)
        monkey.setattr(get_collection().sched.__class__, "today",
                       aqt.mw.col.sched.today + days_delta)
        yield


def seconds_to_minutes(n):
    return n * 60


def seconds_to_days(n):
    return n * 24 * 60 * 60


def reviewer_reset():
    aqt.mw.moveToState("overview")
    aqt.mw.moveToState("review")
    assert aqt.mw.state == "review"


def reviewer_show_question():
    aqt.mw.reviewer._showQuestion()


def reviewer_show_answer():
    aqt.mw.reviewer._showAnswer()


def reviewer_show_next_card():
    aqt.mw.reviewer.nextCard()


DO_NOT_ANSWER = -1
AGAIN = 0
HARD = 1
GOOD = 2
EASY = 3


def reviewer_answer_card(answer: int):
    aqt.mw.reviewer._answerCard(answer)


def reviewer_get_current_card():
    card = aqt.mw.reviewer.card
    assert card is not None
    return card


@dataclass
class Review:
    id: int
    cid: int
    usn: int
    button_chosen: int
    interval: int
    last_interval: int
    ease: int
    taken_millis: int
    review_kind: int

    def to_string(self):
        def interval_to_days(interval):
            return interval if interval >= 0 else -interval / 60 / 60 / 24

        def interval_to_string(interval):
            return f"{interval} days" if interval >= 0 else f"{-interval / 60:n} minutes"

        answer = {0: "again", 1: "hard", 2: "good", 3: "easy"}[self.button_chosen]

        date = datetime.datetime.fromtimestamp(self.id / 1000)
        date_str = date.strftime("%b %d %H:%M")

        old_interval = interval_to_string(self.last_interval)
        new_interval = interval_to_string(self.interval)

        ease = self.ease / 10

        due = date + datetime.timedelta(days=interval_to_days(self.interval))
        due_str = due.strftime("%b %d")

        return f"{answer} @ {date_str} [{old_interval} -> {new_interval}, {ease:n}%, due @ {due_str}]"


def get_card_reviews(card_id: int) -> Sequence[Review]:
    return [
        Review(*data) for data
        in aqt.mw.col.db.all("select * from revlog where cid = ?", card_id)
    ]


@dataclass
class CardInfo:
    id: int
    question: str
    answer: str
    due: int
    reviews: Sequence[Review]

    @classmethod
    def from_card(cls, card: Card) -> "CardInfo":
        return cls(
            card.id,
            question=strip_html(card.question()),
            answer=strip_html(card.answer()),
            due=card.due,
            reviews=get_card_reviews(card.id),
        )

    def to_string(self) -> str:
        reviews_str = "\n                  ".join(
            review.to_string() for review in self.reviews
        )

        return dedent(f"""
              id: {self.id}
        question: {self.question}
          answer: {self.answer}
             due: {self.due}
         reviews: {reviews_str}
        """)


def do_some_historic_reviews(days_to_ids_to_answers: dict[int, dict[int, int]]):
    now = time.time()

    for days, ids_to_answers in days_to_ids_to_answers.items():
        extra_seconds = 0
        reviewer_reset()

        while aqt.mw.state == "review":
            extra_seconds += 1

            if extra_seconds > 10:
                break  # we are going in circles

            with clock_changed_to(now + seconds_to_days(days) + extra_seconds):
                reviewer_show_question()

                try:
                    card = reviewer_get_current_card()
                    answer = ids_to_answers.pop(card.id)
                except KeyError:
                    reviewer_show_next_card()
                else:
                    reviewer_show_answer()
                    if answer != DO_NOT_ANSWER:
                        reviewer_answer_card(answer)

            if not ids_to_answers:
                break

        if ids_to_answers:
            card_info = "\n".join(
                CardInfo.from_card(get_card(card_id)).to_string()
                for card_id in ids_to_answers.keys()
            )
            raise Exception("Reviewer didn't show some of the expected cards: \n"
                            f"{card_info}")


@contextmanager
def current_deck_preserved():
    current_deck_id = get_collection().decks.get_current_id()
    yield
    get_collection().decks.set_current(current_deck_id)


def create_filtered_deck(search_string) -> int:
    search_term = FilteredDeckConfig.SearchTerm(
        search=search_string,
        limit=100,
        order=0,  # random
    )

    with current_deck_preserved():
        filtered_deck = get_collection().sched.get_or_create_filtered_deck(DeckId(0))
        del filtered_deck.config.search_terms[:]
        filtered_deck.config.search_terms.append(search_term)
        return get_collection().sched.add_or_update_filtered_deck(filtered_deck).id


@contextmanager
def filtered_deck_created(search_string):
    deck_id = create_filtered_deck(search_string)
    yield deck_id
    get_collection().decks.remove([deck_id])


def show_deck_overview(deck_id):
    get_collection().decks.set_current(deck_id)
    aqt.mw.moveToState("overview")