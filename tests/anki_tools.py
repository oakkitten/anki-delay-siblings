from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from textwrap import dedent
from typing import Sequence

import aqt
import libfaketime  # noqa  (n/a on windows)
from anki.cards import Card
from anki.collection import Collection, V2Scheduler, V3Scheduler
from anki.decks import DeckId, FilteredDeckConfig, DeckManager
from anki.models import ModelManager
from anki.notes import Note
from anki.scheduler.base import SchedulerBase
from anki.utils import strip_html
from aqt.main import MainWindowState

anki_version = tuple(int(segment) for segment in aqt.appVersion.split("."))


# used to print some stuff that you can see by running
#   $ python -m pytest -s
say = print

def say_card(card_or_card_id: Card | int):
    card = get_card(card_or_card_id) if isinstance(card_or_card_id, int) else card_or_card_id
    card.load()
    say(CardInfo.from_card(card).to_string())


############################################################################## get stuff


def get_collection() -> Collection:
    return aqt.mw.col

def get_models() -> ModelManager:
    return get_collection().models

def get_decks() -> DeckManager:
    return get_collection().decks

def get_scheduler() -> SchedulerBase:
    return get_collection().sched

def get_all_deck_ids() -> list[int]:
    return [item.id for item in get_decks().all_names_and_ids()]

def get_all_model_ids() -> list[int]:
    return [item.id for item in get_models().all_names_and_ids()]

def get_card(card_id: int) -> Card:
    return get_collection().get_card(card_id)


def move_main_window_to_state(state: MainWindowState):
    aqt.mw.moveToState(state)


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

        date = datetime.fromtimestamp(self.id / 1000)
        date_str = date.strftime("%b %d %H:%M")

        old_interval = interval_to_string(self.last_interval)
        new_interval = interval_to_string(self.interval)

        ease = self.ease / 10

        due = date + timedelta(days=interval_to_days(self.interval))
        due_str = due.strftime("%b %d" if self.interval >= 0 else "%b %d %H:%M")

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
        if self.due > 1000000:
            due_str = datetime.fromtimestamp(self.due).strftime("%b %d %H:%M")
        else:
            due_rel = self.due - get_scheduler().today
            due_date_str = (datetime.now() + timedelta(days=self.due)).strftime("%b %d")
            due_str = f"in {due_rel} days, {due_date_str}"

        reviews_str = "\n                  ".join(
            review.to_string() for review in self.reviews
        )

        return dedent(f"""
              id: {self.id}
        question: {self.question}
          answer: {self.answer}
             due: {self.due} ({due_str})
         reviews: {reviews_str}
        """)


########################################################################### create stuff


@dataclass
class CardDescription:
    name: str
    front: str
    back: str


def create_model(model_name: str, field_names: Sequence[str],
                 card_descriptions: Sequence[CardDescription]) -> int:
    models = get_models()
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
    return get_decks().id(deck_name)


def add_note(model_name: str, deck_name: str, fields: dict[str, str],
             tags: Sequence[str] = None) -> int:
    model_id = get_models().id_for_name(model_name)
    deck_id = get_decks().id_for_name(deck_name)
    note = Note(get_collection(), model_id)

    for field_name, field_value in fields.items():
        note[field_name] = field_value

    if tags is not None:
        note.tags = list(tags)

    get_collection().add_note(note, deck_id)
    return note.id


################################################################### create filtered deck


def create_filtered_deck(search_string) -> int:
    search_term = FilteredDeckConfig.SearchTerm(
        search=search_string,
        limit=100,
        order=0,  # random?
    )

    filtered_deck = get_scheduler().get_or_create_filtered_deck(DeckId(0))
    del filtered_deck.config.search_terms[:]
    filtered_deck.config.search_terms.append(search_term)
    return get_scheduler().add_or_update_filtered_deck(filtered_deck).id


# note that creating a filtered deck will change the current deck for some reason
# either way, you should be calling `show_deck_overview` inside the with clause
@contextmanager
def filtered_deck_created(search_string):
    deck_id = create_filtered_deck(search_string)
    yield deck_id
    get_decks().remove([DeckId(deck_id)])


def show_deck_overview(deck_id):
    get_decks().set_current(deck_id)
    move_main_window_to_state("overview")


################################################################################ reviews


def set_scheduler(version: int):
    if version == 2:
        get_collection().set_v3_scheduler(enabled=False)
        assert isinstance(get_scheduler(), V2Scheduler)
    elif version == 3:
        get_collection().set_v3_scheduler(enabled=True)
        assert isinstance(get_scheduler(), V3Scheduler)
    else:
        raise ValueError(f"Bad scheduler version: {version}")


# this changes clock for both Python and Rust by doing some C magic.
# libfaketime needs to be preloaded by the dynamic linker;
# this can be done by running the following before the tests:
#   $ eval $(python-libfaketime)
# clock can only be set forward due to the way Anki's Rust backend handles deck time:
# it calls `elapsed()`, which returns 0 if clock went backwards.
#
# EXTREME CAUTION: Rust backend usually regenerates scheduler “today” via current time,
# but it stores the last result and will return it instead if is more “recent”.
# this means that “today”, at least as seen from python, can't go backwards!
# on the other hand, it seems that this does not affect answering cards in reviewer.
# see rslib/src/scheduler/mod.rs -> `impl Collection` -> `fn scheduler_info`
@contextmanager
def clock_set_forward_by(**kwargs):
    delta = timedelta(**kwargs)

    if delta < timedelta(0):
        raise Exception(f"Can't set clock backwards ({delta=})")

    with libfaketime.fake_time(datetime.now() + delta):
        yield


def reset_window_to_review_state():
    move_main_window_to_state("overview")
    move_main_window_to_state("review")
    assert aqt.mw.state == "review"

def reviewer_get_current_card():
    card = aqt.mw.reviewer.card
    assert card is not None
    return card

def reviewer_show_question():
    aqt.mw.reviewer._showQuestion()

def reviewer_show_answer():
    aqt.mw.reviewer._showAnswer()

DO_NOT_ANSWER = -1
AGAIN = 0
HARD = 1
GOOD = 2
EASY = 3

def reviewer_answer_card(answer: int):
    aqt.mw.reviewer._answerCard(answer)

def reviewer_bury_current_card():
    aqt.mw.reviewer.bury_current_card()

def unbury_cards_for_current_deck():
    current_deck_id = get_decks().get_current_id()
    get_scheduler().unbury_deck(current_deck_id)


def do_some_historic_reviews(days_to_ids_to_answers: dict[int, dict[int, int]]):
    say(f":: doing some historic reviews")

    for days, ids_to_answers in days_to_ids_to_answers.items():
        say(f":: @ {days} days :: {ids_to_answers}")

        with clock_set_forward_by(days=days):
            extra_minutes = 0
            reset_window_to_review_state()

            while aqt.mw.state == "review":
                extra_minutes += 1

                # we are probably going in circles, break to raise the exception
                if extra_minutes > 10:
                    break

                # change time, as review id is the timestamp and must be unique
                with clock_set_forward_by(minutes=extra_minutes):
                    reviewer_show_question()

                    try:
                        card = reviewer_get_current_card()
                        answer = ids_to_answers.pop(card.id)
                    except KeyError:
                        say(f":: :: {card.id} -> skipping")
                        reviewer_bury_current_card()
                    else:
                        say(f":: :: {card.id} -> answering with {answer}"
                            .replace("answering with -1", "only showing"))
                        reviewer_show_answer()
                        if answer != DO_NOT_ANSWER:
                            reviewer_answer_card(answer)

                if not ids_to_answers:
                    break

            unbury_cards_for_current_deck()

        if ids_to_answers:
            card_info = "\n".join(
                CardInfo.from_card(get_card(card_id)).to_string()
                for card_id in ids_to_answers.keys()
            )

            raise Exception("Reviewer didn't show some of the expected cards: \n"
                            f"{card_info}")
