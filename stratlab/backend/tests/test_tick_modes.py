from app.kite_service import TickHub


class WS:
    MODE_QUOTE, MODE_FULL = "quote", "full"

    def __init__(self):
        self.calls = []

    def subscribe(self, toks):
        self.calls.append(("sub", sorted(toks)))

    def set_mode(self, mode, toks):
        self.calls.append((mode, sorted(toks)))

    def unsubscribe(self, toks):
        self.calls.append(("unsub", sorted(toks)))


def test_full_depth_only_where_a_listener_needs_the_spread():
    hub = TickHub(kite=None)
    hub.ws, hub.started, hub.connected = WS(), True, True
    hub.add("s1", 1, lambda t: None)
    hub.add("g1:0", 2, lambda t: None, full=True)
    assert hub.ws.calls[-1] == ("full", [2]) and ("quote", [1]) in hub.ws.calls
    hub.ws.calls.clear()
    hub._on_connect(hub.ws, None)                        # a reconnect restores both modes
    assert ("quote", [1]) in hub.ws.calls and ("full", [2]) in hub.ws.calls
    hub.remove("g1:0")
    assert hub._full_tokens() == set() and ("unsub", [2]) in hub.ws.calls
