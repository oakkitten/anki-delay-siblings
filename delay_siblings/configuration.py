from aqt import mw


ENABLED = "enabled"
QUIET = "quiet"
OFFER_TO_DELAY_AFTER_SYNC = "offer_to_delay_after_sync"


def make_property(name):
    def getter(self):
        return self.deck_data[name]

    def setter(self, value):
        self.deck_data[name] = value
        self.config.save()

    return property(getter, setter)

class DeckConfig:
    def __init__(self, cfg, deck_id):
        self.config = cfg
        self.deck_data = cfg.data.setdefault(str(deck_id), {ENABLED: False, QUIET: False})

    enabled = make_property(ENABLED)
    quiet = make_property(QUIET)


class Config:
    def __init__(self):
        self.data = mw.addonManager.getConfig(__name__) or {}
        self.current_deck = DeckConfig(self, 0)

    def save(self):
        mw.addonManager.writeConfig(__name__, self.data)

    def set_current_deck_id(self, deck_id):
        self.current_deck = DeckConfig(self, deck_id)

    @property
    def offer_to_delay_after_sync(self):
        return self.data.get(OFFER_TO_DELAY_AFTER_SYNC, False)