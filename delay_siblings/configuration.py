from typing import Sequence

from aqt import mw


ENABLED = "enabled"
QUIET = "quiet"
OFFER_TO_DELAY_AFTER_SYNC = "offer_to_delay_after_sync"


class DeckConfig:
    def __init__(self, config, deck_id):
        self.deck_id = deck_id
        self.config = config
        self.deck_data = config.data.setdefault(str(deck_id), {})
        self.deck_data.setdefault(ENABLED, False)
        self.deck_data.setdefault(QUIET, False)

    @property
    def enabled(self):
        return self.deck_data[ENABLED]

    @enabled.setter
    def enabled(self, value):
        self.deck_data[ENABLED] = value
        self.config.save()

    @property
    def quiet(self):
        return self.deck_data[QUIET]

    @quiet.setter
    def quiet(self, value):
        self.deck_data[QUIET] = value
        self.config.save()


class Config:
    def __init__(self):
        self.data = {}
        self.current_deck = DeckConfig(self, 0)

    def load(self):
        self.data = mw.addonManager.getConfig(__name__) or {}

    def save(self):
        mw.addonManager.writeConfig(__name__, self.data)

    def set_current_deck_id(self, deck_id):
        self.current_deck = DeckConfig(self, deck_id)

    def enabled_deck_ids(self) -> Sequence[str]:
        return [key for key in self.data.keys() if key.isdigit() and self.data[key][ENABLED]]

    @property
    def offer_to_delay_after_sync(self):
        return self.data.get(OFFER_TO_DELAY_AFTER_SYNC, False)