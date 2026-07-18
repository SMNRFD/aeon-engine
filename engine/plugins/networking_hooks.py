"""Plugin networking hooks — let plugins intercept network messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.core.logging import get_logger
from engine.network import NetworkMessage, MessageType


log = get_logger("plugins.networking")


@dataclass
class NetworkHook:
    """A hook that a plugin has registered for network messages."""

    plugin_name: str
    message_type: MessageType
    handler: Callable[[NetworkMessage], Optional[NetworkMessage]]
    priority: int = 50  # lower = earlier
    is_outgoing: bool = False  # True = outgoing, False = incoming


class PluginNetworkingHooks:
    """Manages network message hooks registered by plugins.

    Plugins can intercept incoming or outgoing network messages to:
    * Modify message payloads
    * Block messages
    * Add custom logging
    * Implement protocol extensions
    """

    def __init__(self) -> None:
        self._incoming_hooks: dict[MessageType, list[NetworkHook]] = {}
        self._outgoing_hooks: dict[MessageType, list[NetworkHook]] = {}
        self._blocked_count: int = 0
        self._modified_count: int = 0

    def register_incoming(self, plugin_name: str, message_type: MessageType,
                           handler: Callable[[NetworkMessage], Optional[NetworkMessage]],
                           priority: int = 50) -> None:
        """Register a hook for incoming messages of a type."""
        hook = NetworkHook(
            plugin_name=plugin_name, message_type=message_type,
            handler=handler, priority=priority, is_outgoing=False,
        )
        self._incoming_hooks.setdefault(message_type, []).append(hook)
        self._incoming_hooks[message_type].sort(key=lambda h: h.priority)

    def register_outgoing(self, plugin_name: str, message_type: MessageType,
                            handler: Callable[[NetworkMessage], Optional[NetworkMessage]],
                            priority: int = 50) -> None:
        """Register a hook for outgoing messages of a type."""
        hook = NetworkHook(
            plugin_name=plugin_name, message_type=message_type,
            handler=handler, priority=priority, is_outgoing=True,
        )
        self._outgoing_hooks.setdefault(message_type, []).append(hook)
        self._outgoing_hooks[message_type].sort(key=lambda h: h.priority)

    def process_incoming(self, message: NetworkMessage) -> Optional[NetworkMessage]:
        """Run all incoming hooks for a message. Returns modified message or None if blocked."""
        hooks = self._incoming_hooks.get(message.type, [])
        for hook in hooks:
            try:
                result = hook.handler(message)
                if result is None:
                    # Hook blocked the message
                    self._blocked_count += 1
                    log.debug("Message %s blocked by plugin %s",
                              message.type.name, hook.plugin_name)
                    return None
                message = result
                self._modified_count += 1
            except Exception as exc:  # noqa: BLE001
                log.error("Incoming hook %s raised: %s", hook.plugin_name, exc)
        return message

    def process_outgoing(self, message: NetworkMessage) -> Optional[NetworkMessage]:
        """Run all outgoing hooks for a message."""
        hooks = self._outgoing_hooks.get(message.type, [])
        for hook in hooks:
            try:
                result = hook.handler(message)
                if result is None:
                    self._blocked_count += 1
                    log.debug("Outgoing message %s blocked by plugin %s",
                              message.type.name, hook.plugin_name)
                    return None
                message = result
                self._modified_count += 1
            except Exception as exc:  # noqa: BLE001
                log.error("Outgoing hook %s raised: %s", hook.plugin_name, exc)
        return message

    def unregister_plugin(self, plugin_name: str) -> int:
        """Remove all hooks from a plugin. Returns count removed."""
        count = 0
        for hooks in self._incoming_hooks.values():
            before = len(hooks)
            hooks[:] = [h for h in hooks if h.plugin_name != plugin_name]
            count += before - len(hooks)
        for hooks in self._outgoing_hooks.values():
            before = len(hooks)
            hooks[:] = [h for h in hooks if h.plugin_name != plugin_name]
            count += before - len(hooks)
        if count:
            log.info("Removed %d network hooks from plugin %s", count, plugin_name)
        return count

    def stats(self) -> dict[str, Any]:
        return {
            "incoming_hooks": sum(len(h) for h in self._incoming_hooks.values()),
            "outgoing_hooks": sum(len(h) for h in self._outgoing_hooks.values()),
            "blocked_count": self._blocked_count,
            "modified_count": self._modified_count,
        }
