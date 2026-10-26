"""Every new wiring-health measurement reaches every dashboard as
``health_update``: a read past the cache TTL as well as a forced one, after the
history entry it caused, and never for a read the cache answers."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import server


def _health(state: str) -> dict:
    return {"summary": {"state": state}, "harness_sync": {"harnesses": []}}


class HealthBroadcastTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / ".claude" / "agents").mkdir(parents=True)

    def events(self, app, action) -> list[dict]:
        """Run `action` with a subscriber attached and return what it received."""
        async def scenario() -> list[dict]:
            bus = app.state.bus
            bus.bind_loop(asyncio.get_running_loop())
            queue = bus.subscribe()
            await asyncio.to_thread(action)
            await asyncio.sleep(0.05)
            out = []
            while not queue.empty():
                out.append(await queue.get())
            return out

        return asyncio.run(scenario())

    def wiring(self, app):
        endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/api/health/wiring")
        return lambda: endpoint()

    def test_a_read_past_the_ttl_publishes_its_measurement_after_the_history_entry(self) -> None:
        values = iter([_health("HEALTHY"), _health("DEGRADED")])
        with mock.patch.object(server, "get_wiring_health", side_effect=lambda _root: next(values)):
            app = server.create_app(self.root, health_ttl=0.0, history_store=None)
            read = self.wiring(app)
            first = self.events(app, read)
            second = self.events(app, read)
        self.assertEqual([(e["event"], e["data"]["summary"]["state"]) for e in first],
                         [("health_update", "HEALTHY")])
        self.assertEqual([e["event"] for e in second], ["history_append", "health_update"])
        self.assertEqual(second[0]["data"]["summary"], "Wiring health: HEALTHY -> DEGRADED")
        self.assertEqual(second[1]["data"]["summary"]["state"], "DEGRADED")

    def test_a_read_the_cache_answers_publishes_nothing(self) -> None:
        with mock.patch.object(server, "get_wiring_health", return_value=_health("HEALTHY")) as probe:
            app = server.create_app(self.root, health_ttl=3600.0, history_store=None)
            read = self.wiring(app)
            self.events(app, read)
            cached = self.events(app, read)
        self.assertEqual(cached, [])
        self.assertEqual(probe.call_count, 1)

    def test_a_forced_measurement_publishes_exactly_one_health_update(self) -> None:
        with mock.patch.object(server, "get_wiring_health", return_value=_health("HEALTHY")):
            app = server.create_app(self.root, health_ttl=3600.0, history_store=None)
            events = self.events(app, lambda: app.state.watcher.on_flush(
                [self.root / ".claude" / "agents" / "redactor.md"]))
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds.count("health_update"), 1)
        self.assertIn("state_update", kinds)


if __name__ == "__main__":
    unittest.main()
