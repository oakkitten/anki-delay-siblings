import traceback
import jsonschema

from typing import Sequence

from aqt import mw
from aqt.utils import showWarning

from .tools import get_current_deck_id


ENABLED_FOR_DECKS = "enabled_for_decks"
QUIET = "quiet"
DELAY_AFTER_SYNC = "delay_after_sync"
VERSION = "version"

DELAY_WITHOUT_ASKING = "delay_without_asking"
ASK_EVERY_TIME = "ask_every_time"
DO_NOT_DELAY = "do_not_delay"


tag = mw.addonManager.addonFromModule(__name__)


def load_config():
    return mw.addonManager.getConfig(tag)

def load_default_config():
    return mw.addonManager.addonConfigDefaults(tag)

def save_config(data):
    mw.addonManager.writeConfig(tag, data)

def validate_config(data):
    jsonschema.validate(data, mw.addonManager._addon_schema(tag))

def run_on_configuration_change(function):
    mw.addonManager.setConfigUpdatedAction(__name__, lambda *_: function())


########################################################################################


# noinspection PyAttributeOutsideInit
class Config:
    def load(self):
        self.data = migrate_data_restoring_default_config_on_error(load_config())

    def save(self):
        save_config(self.data)

    @property
    def enabled_for_deck_ids(self) -> Sequence[str]:
        return [deck_id for deck_id, enabled in self.data[ENABLED_FOR_DECKS].items() if enabled is True]

    @property
    def enabled_for_current_deck(self):
        return str(get_current_deck_id()) in self.enabled_for_deck_ids

    @enabled_for_current_deck.setter
    def enabled_for_current_deck(self, value):
        self.data[ENABLED_FOR_DECKS][str(get_current_deck_id())] = value
        self.save()

    @property
    def quiet(self):
        return self.data[QUIET]

    @quiet.setter
    def quiet(self, value):
        self.data[QUIET] = value
        self.save()

    @property
    def delay_after_sync(self):
        return self.data[DELAY_AFTER_SYNC]

    @delay_after_sync.setter
    def delay_after_sync(self, value):
        self.data[DELAY_AFTER_SYNC] = value
        self.save()


########################################################################################


def migrate(data):
    if data["version"] == 0:
        print(":: delay siblings: migrating config from version 0")

        decks = {}
        quiet = False

        for key, value in data.items():
            if key.isdigit() and key != "0":
                enabled = value["enabled"]
                decks[key] = enabled
                if enabled:
                    quiet = value["quiet"]

        data = {
            VERSION: 1,
            ENABLED_FOR_DECKS: decks,
            QUIET: quiet,
            DELAY_AFTER_SYNC: ASK_EVERY_TIME
        }

    validate_config(data)

    return data


def migrate_data_restoring_default_config_on_error(data):
    try:
        fixed_data = migrate(data)
    except Exception:  # noqa
        showWarning(
            title="Delay siblings",
            text="Unexpected error while migrating configuration. "
                 "Loading default configuration.\n\n" + traceback.format_exc()
        )
        fixed_data = load_default_config()

    if fixed_data != data:
        save_config(fixed_data)
        data = fixed_data

    return data
