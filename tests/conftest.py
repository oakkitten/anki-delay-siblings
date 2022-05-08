import os
from dataclasses import dataclass

import pytest
from anki.decks import DeckId

from tests.tools.collection import (
    CardDescription,
    get_collection,
    get_decks,
    create_model,
    create_deck,
    add_note,
    set_scheduler,
    do_some_historic_reviews,
    EASY,
    DO_NOT_ANSWER,
    reset_window_to_review_state,
)

from tests.tools.testing import (
    add_addon_to_copy_into_anki_addons_folder,
    close_all_dialogs_and_wait_for_them_to_run_closing_callbacks,
)

# used fixtures and pytest hooks
# noinspection PyUnresolvedReferences
from tests.tools.testing import (
    pytest_addoption,
    pytest_report_header,
    pytest_generate_tests,
    run_background_tasks_on_main_thread,
    session_scope_empty_session,
    session_scope_session_with_profile_loaded,
    session_with_profile_loaded,
)


addon_name = "delay_siblings"
addon_folder = os.path.join(os.path.split(__file__)[0], f"../{addon_name}")

add_addon_to_copy_into_anki_addons_folder(addon_name, addon_folder)


def review_cards_in_0_5_10_days(setup):
    do_some_historic_reviews({
        0: {setup.card1_id: EASY, setup.card2_id: EASY},
        5: {setup.card1_id: EASY, setup.card2_id: EASY},
        10: {setup.card1_id: EASY, setup.card2_id: EASY},
    })


def review_card1_in_20_days(setup):
    do_some_historic_reviews({
        20: {setup.card1_id: EASY},
    })


def show_answer_of_card1_in_20_days(setup):
    do_some_historic_reviews({
        20: {setup.card1_id: DO_NOT_ANSWER},
    })


@dataclass
class Setup:
    delay_siblings: "delay_siblings"
    model_id: int
    deck_id: int
    note_id: int
    card1_id: int
    card2_id: int


def set_up_test_deck_and_test_model_and_two_notes():
    deck_id = create_deck("test_deck")

    model_id = create_model(
        model_name="test_model",
        field_names=["field1", "field2"],
        card_descriptions=[
            CardDescription(name="card_1", front="{{field1}}", back="{{field1}}<br> {{field2}}"),
            CardDescription(name="card_2", front="{{field2}}", back="{{field2}}<br> {{field1}}")
        ],
    )

    note_id = add_note(
        model_name="test_model",
        deck_name="test_deck",
        fields={"field1": "note1 field1", "field2": "note1 field2"},
        tags=["tag1"],
    )


    card_ids = get_collection().find_cards(query=f"nid:{note_id}")

    get_decks().set_current(DeckId(deck_id))
    reset_window_to_review_state()

    import delay_siblings
    delay_siblings.config.load()

    return Setup(
        delay_siblings=delay_siblings,
        model_id=model_id,
        deck_id=deck_id,
        note_id=note_id,
        card1_id=card_ids[0],
        card2_id=card_ids[1],
    )


@pytest.fixture
def setup(request, session_with_profile_loaded):
    if hasattr(request, "param"):
        set_scheduler(request.param)

    yield set_up_test_deck_and_test_model_and_two_notes()
    close_all_dialogs_and_wait_for_them_to_run_closing_callbacks()


try_with_all_schedulers = pytest.mark.parametrize(
    "setup",
    [2, 3],
    ids=["v2 scheduler", "v3 scheduler"],
    indirect=True
)
