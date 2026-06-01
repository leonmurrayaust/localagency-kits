"""
localagency/services/voicekit_worker.py
═══════════════════════════════════════════
Entry point for the VoiceKit worker process.
Listens for call events from Redis/Celery and processes them through
the LangGraph state machine.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from localagency.config import get_settings
from localagency.services.voicekit import VoiceKitService

logger = logging.getLogger("voicekit-worker")


async def main():
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO if not settings.debug else logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("VoiceKit Worker starting...")
    logger.info(f"Environment: {settings.environment}")

    voicekit = VoiceKitService()

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    loop.add_signal_handler(signal.SIGINT, _signal_handler)

    logger.info("VoiceKit Worker ready. Waiting for calls...")

    # In Phase 1, this just waits for Celery tasks
    # In Phase 2, this will poll Redis for pending call events
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    logger.info("VoiceKit Worker shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
