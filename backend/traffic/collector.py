"""Scheduled collection of traffic flow, incidents and weather.

Run as a separate process:

    python -m traffic.collector            # loop forever
    python -m traffic.collector --once     # one sweep of every task (for cron / tests)

Request frequency is bounded by configured intervals and by the shared TomTom
daily budget (background work never consumes the interactive reserve). A failing
provider is logged and retried on the next interval with exponential backoff;
it never stops the other tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

from core.log_config import configure_logging
from core.settings import Settings, get_settings
from db.session import init_db, session_scope
from providers.openmeteo import WEATHER_AREAS, OpenMeteoProvider
from providers.tomtom import ProviderError, ProviderUnavailable, TomTomProvider
from traffic.ingest import ensure_segments, store_flow, store_incidents, store_weather

logger = logging.getLogger("pulse.collector")


async def collect_flow(settings: Settings, tomtom: Optional[TomTomProvider] = None) -> Dict[str, int]:
    tomtom = tomtom or TomTomProvider(settings)
    stats = {"stored": 0, "duplicate": 0, "invalid": 0, "skipped": 0}
    if not tomtom.configured:
        logger.warning("TomTom not configured; flow collection skipped")
        stats["skipped"] = -1
        return stats
    with session_scope() as session:
        segments = [(s.id, s.code, s.lat, s.lon) for s in ensure_segments(session)]
    for seg_id, code, lat, lon in segments:
        try:
            reading = await tomtom.flow_segment(lat, lon, purpose="collector", background=True)
        except ProviderUnavailable as exc:
            logger.warning("Flow collection stopped: %s", exc)
            stats["skipped"] += 1
            break
        except ProviderError as exc:
            logger.warning("Flow reading rejected for %s: %s", code, exc)
            stats["invalid"] += 1
            continue
        with session_scope() as session:
            from db.models import TrafficSegment

            segment = session.get(TrafficSegment, seg_id)
            stats["stored" if store_flow(session, segment, reading) else "duplicate"] += 1
    logger.info("Flow sweep: %s", stats)
    return stats


async def collect_incidents(settings: Settings, tomtom: Optional[TomTomProvider] = None) -> Dict[str, int]:
    tomtom = tomtom or TomTomProvider(settings)
    if not tomtom.configured:
        return {"skipped": 1}
    readings = await tomtom.incidents(background=True)
    with session_scope() as session:
        result = store_incidents(session, readings)
    logger.info("Incident sweep: %d incidents %s", len(readings), result)
    return result


async def collect_weather(settings: Settings, provider: Optional[OpenMeteoProvider] = None) -> Dict[str, int]:
    provider = provider or OpenMeteoProvider(settings)
    stats = {"stored": 0, "duplicate": 0, "invalid": 0}
    for area, (lat, lon) in WEATHER_AREAS.items():
        try:
            reading = await provider.current(lat, lon)
        except ProviderError as exc:
            logger.warning("Weather reading rejected for %s: %s", area, exc)
            stats["invalid"] += 1
            continue
        with session_scope() as session:
            stats["stored" if store_weather(session, area, lat, lon, reading) else "duplicate"] += 1
    logger.info("Weather sweep: %s", stats)
    return stats


@dataclass
class Task:
    name: str
    interval_s: float
    run: Callable[[], Awaitable[dict]]
    next_run: float = 0.0
    failures: int = 0

    def schedule_after(self, ok: bool) -> None:
        self.failures = 0 if ok else self.failures + 1
        backoff = min(2 ** self.failures, 8) if self.failures else 1
        self.next_run = time.monotonic() + self.interval_s * (backoff if not ok else 1)


def build_tasks(settings: Settings) -> list[Task]:
    tomtom = TomTomProvider(settings)
    weather = OpenMeteoProvider(settings)
    return [
        Task("flow", settings.collector_flow_interval_minutes * 60, lambda: collect_flow(settings, tomtom)),
        Task("weather", settings.collector_weather_interval_minutes * 60, lambda: collect_weather(settings, weather)),
        Task("incidents", settings.collector_incident_interval_minutes * 60, lambda: collect_incidents(settings, tomtom)),
    ]


async def run_once(settings: Settings) -> dict:
    results = {}
    for task in build_tasks(settings):
        try:
            results[task.name] = await task.run()
        except Exception as exc:  # isolate task failures
            logger.exception("Collector task %s failed", task.name)
            results[task.name] = {"error": type(exc).__name__}
    return results


async def run_forever(settings: Settings) -> None:
    tasks = build_tasks(settings)
    logger.info("Collector started: %s", {t.name: t.interval_s for t in tasks})
    while True:
        now = time.monotonic()
        for task in tasks:
            if now >= task.next_run:
                try:
                    await task.run()
                    task.schedule_after(True)
                except Exception:
                    logger.exception("Collector task %s failed (failures=%d)", task.name, task.failures + 1)
                    task.schedule_after(False)
        await asyncio.sleep(max(5.0, min(t.next_run for t in tasks) - time.monotonic()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run every task once and exit")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if settings.db_auto_create:
        init_db()
    if args.once:
        print(asyncio.run(run_once(settings)))
    else:
        asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
