"""Messenger bridges (Telegram / Discord / Webhook / iMessage).

Each module exposes a {Name}Bridge class with ``async start()`` / ``async stop()``
so the orchestrator can attach and detach external channels at runtime.
"""
