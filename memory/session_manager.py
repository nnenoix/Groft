from __future__ import annotations

import asyncio


class SessionManager:
    def __init__(
        self,
        tmux_target: str,
        context_limit_tokens: int = 200_000,
        compaction_threshold: float = 0.80,
        chars_per_token: int = 4,
    ) -> None:
        self._tmux_target = tmux_target
        self._context_limit_tokens = context_limit_tokens
        self._compaction_threshold = compaction_threshold
        self._chars_per_token = chars_per_token
        self._current_tokens = 0

    def track_context_size(self, current_text: str) -> int:
        # coarse char-based estimate — good enough for a compaction trigger, not for billing
        tokens = len(current_text) // self._chars_per_token
        self._current_tokens = tokens
        return tokens

    def current_tokens(self) -> int:
        return self._current_tokens

    def needs_compaction(self) -> bool:
        if self._context_limit_tokens <= 0:
            return False
        ratio = self._current_tokens / self._context_limit_tokens
        return ratio >= self._compaction_threshold

    async def trigger_compaction(self) -> bool:
        # /compact is a Claude Code slash command; we just deliver the keystrokes via tmux
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "send-keys",
                "-t",
                self._tmux_target,
                "/compact",
                "Enter",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return False
        try:
            await proc.communicate()
        except Exception:
            return False
        return proc.returncode == 0
