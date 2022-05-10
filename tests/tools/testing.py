import concurrent.futures
import time
from contextlib import contextmanager
from pathlib import Path

import anki.collection
import aqt.operations.note
import pytest
from _pytest.monkeypatch import MonkeyPatch  # noqa
from pytest_anki._launch import anki_running, temporary_user  # noqa
from waitress import wasyncore

from tests.tools.collection import (
    anki_version,
    get_decks,
    get_models,
    get_all_deck_ids,
    get_all_model_ids,
    move_main_window_to_state,
)

try:
    from PyQt6 import QtTest
except ImportError:
    from PyQt5 import QtTest


# wait for n seconds, while events are being processed
def wait(seconds):
    milliseconds = int(seconds * 1000)
    QtTest.QTest.qWait(milliseconds)  # noqa


def wait_until(booleanish_function, at_most_seconds=10):
    deadline = time.time() + at_most_seconds

    while time.time() < deadline:
        if booleanish_function():
            return
        wait(0.01)

    raise Exception(f"Function {booleanish_function} never once returned "
                    f"a positive value in {at_most_seconds} seconds")


def close_all_dialogs_and_wait_for_them_to_run_closing_callbacks():
    aqt.dialogs.closeAll(onsuccess=lambda: None)
    wait_until(aqt.dialogs.allClosed)


def reset_addon_configuration(addon_name: str):
    default_config = aqt.mw.addonManager.addonConfigDefaults(addon_name)
    aqt.mw.addonManager.writeConfig(addon_name, default_config)


addons_to_copy_into_anki_addons_folders = []


def add_addon_to_copy_into_anki_addons_folder(addon_name: str, addon_folder: str):
    addon_folder = Path(addon_folder).resolve()

    if not addon_folder.exists() or not addon_folder.is_dir():
        raise Exception(f"Addon folder {addon_folder} is not a directory")

    if (addon_folder / "meta.json").exists():
        raise Exception(f"Addon folder {addon_folder} contains meta.json")

    addons_to_copy_into_anki_addons_folders.append((addon_name, addon_folder))


########################################################################################


# waitress is a WSGI server that Anki starts to serve css etc to its web views.
# it seems to have a race condition issue;
# the main loop thread is trying to `select.select` the sockets
# which a worker thread is closing because of a dead connection.
# this is especially pronounced in tests,
# as we open and close windows rapidly--and so web views and their connections.
# this small patch makes waitress skip actually closing the sockets
# (unless the server is shutting down--if it is, loop exceptions are ignored).
# while the unclosed sockets might accumulate,
# this should not pose an issue in test environment.
# see https://github.com/Pylons/waitress/issues/374
@contextmanager
def waitress_patched_to_prevent_it_from_dying():
    original_close = wasyncore.dispatcher.close
    sockets_that_must_not_be_garbage_collected = []     # lists are thread-safe

    def close(self):
        if not aqt.mw.mediaServer.is_shutdown:
            sockets_that_must_not_be_garbage_collected.append(self.socket)
            self.socket = None
        original_close(self)

    with MonkeyPatch().context() as monkey:
        monkey.setattr(wasyncore.dispatcher, "close", close)
        yield


@contextmanager
def anki_patched_to_prevent_backups():
    with MonkeyPatch().context() as monkey:
        if anki_version < (2, 1, 50):
            monkey.setitem(aqt.profiles.profileConf, "numBackups", 0)
        else:
            monkey.setattr(anki.collection.Collection, "create_backup",
                           lambda *args, **kwargs: True)
        yield


@contextmanager
def empty_anki_session_started():
    with waitress_patched_to_prevent_it_from_dying():
        with anki_patched_to_prevent_backups():
            with anki_running(
                qtbot=None,  # noqa
                enable_web_debugging=False,
                profile_name="test_user",
                unpacked_addons=addons_to_copy_into_anki_addons_folders
            ) as session:
                yield session


@contextmanager
def profile_created_and_loaded(session):
    with temporary_user(session.base, "test_user", "en_US"):
        with session.profile_loaded():
            yield session


@contextmanager
def current_decks_and_models_etc_preserved():
    deck_ids_before = get_all_deck_ids()
    model_ids_before = get_all_model_ids()

    try:
        yield
    finally:
        deck_ids_after = get_all_deck_ids()
        model_ids_after = get_all_model_ids()

        deck_ids_to_delete = {*deck_ids_after} - {*deck_ids_before}
        model_ids_to_delete = {*model_ids_after} - {*model_ids_before}

        get_decks().remove(deck_ids_to_delete)  # noqa
        for model_id in model_ids_to_delete:
            get_models().remove(model_id)

        move_main_window_to_state("deckBrowser")


########################################################################################


def pytest_addoption(parser):
    parser.addoption("--tear-down-profile-after-each-test",
                     action="store_true",
                     default=True)
    parser.addoption("--no-tear-down-profile-after-each-test", "-T",
                     action="store_false",
                     dest="tear_down_profile_after_each_test")


def pytest_report_header(config):  # noqa
    if config.option.forked:
        return "test isolation: perfect; each test is run in a separate process"
    if config.option.tear_down_profile_after_each_test:
        return "test isolation: good; user profile is torn down after each test"
    else:
        return "test isolation: poor; only newly created decks and models " \
               "are cleaned up between tests"


@pytest.fixture(autouse=True)
def run_background_tasks_on_main_thread(request, monkeypatch):  # noqa
    """
    Makes background operations such as card deletion execute on main thread
    and execute the callback immediately
    """
    def run_in_background(task, on_done=None, kwargs=None):
        future = concurrent.futures.Future()

        try:
            future.set_result(task(**kwargs if kwargs is not None else {}))
        except BaseException as e:
            future.set_exception(e)

        if on_done is not None:
            on_done(future)

    monkeypatch.setattr(aqt.mw.taskman, "run_in_background", run_in_background)


# don't use run_background_tasks_on_main_thread for tests that don't run Anki
def pytest_generate_tests(metafunc):
    if (
        run_background_tasks_on_main_thread.__name__ in metafunc.fixturenames
        and session_scope_empty_session.__name__ not in metafunc.fixturenames
    ):
        metafunc.fixturenames.remove(run_background_tasks_on_main_thread.__name__)


@pytest.fixture(scope="session")
def session_scope_empty_session():
    with empty_anki_session_started() as session:
        yield session


@pytest.fixture(scope="session")
def session_scope_session_with_profile_loaded(session_scope_empty_session):
    with profile_created_and_loaded(session_scope_empty_session):
        yield session_scope_empty_session


# Yielding briefly may get rid of the Qt warning somehow:
#   Window should have been closed: <PyQt6.QtWidgets.QWidget object at 0x7f36e4169360>
@pytest.fixture
def session_with_profile_loaded(session_scope_empty_session, request):
    """
    Like anki_session fixture from pytest-anki, but:
      * Default profile is loaded
      * It's relying on session-wide app instance so that
        it can be used without forking every test;
        this can be useful to speed up tests and also
        to examine Anki's stdout/stderr, which is not visible with forking.
      * If command line option --no-tear-down-profile-after-each-test is passed,
        only the newly created decks and models are deleted.
        Otherwise, the profile is completely torn down after each test.
        Tearing down the profile is significantly slower.
    """
    if request.config.option.tear_down_profile_after_each_test:
        with profile_created_and_loaded(session_scope_empty_session):
            yield session_scope_empty_session
    else:
        session = request.getfixturevalue(
            session_scope_session_with_profile_loaded.__name__
        )
        with current_decks_and_models_etc_preserved():
            yield session

    for addon_name, _ in addons_to_copy_into_anki_addons_folders:
        reset_addon_configuration(addon_name)

    wait(0)
