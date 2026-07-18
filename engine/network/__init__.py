"""Networking hooks — architecture-ready for dedicated servers, MMO scaling.

The current implementation provides the message protocol and interface
contract for client/server communication, with a local-only transport
suitable for headless tests. Real networking would replace the transport
with TCP/WebSocket/QUIC while keeping the message protocol intact.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional

from engine.core.logging import get_logger


log = get_logger("network")


class MessageType(IntEnum):
    HANDSHAKE = 0
    PLAYER_ACTION = 1
    WORLD_SNAPSHOT = 2
    ENTITY_UPDATE = 3
    CHAT = 4
    EVENT = 5
    SAVE = 6
    ERROR = 7
    HEARTBEAT = 8
    DISCONNECT = 9


@dataclass
class NetworkMessage:
    """A network protocol message."""

    type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)
    sender_id: Optional[int] = None
    target_id: Optional[int] = None  # None = broadcast
    sequence: int = 0
    timestamp: float = 0.0

    def serialize(self) -> bytes:
        return json.dumps({
            "type": int(self.type),
            "payload": self.payload,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "NetworkMessage":
        d = json.loads(data.decode("utf-8"))
        return cls(
            type=MessageType(d["type"]),
            payload=d.get("payload", {}),
            sender_id=d.get("sender_id"),
            target_id=d.get("target_id"),
            sequence=d.get("sequence", 0),
            timestamp=d.get("timestamp", 0.0),
        )


class NetworkTransport:
    """Abstract transport layer."""

    def send(self, message: NetworkMessage) -> None:
        raise NotImplementedError

    def receive(self, timeout: float = 0.0) -> Optional[NetworkMessage]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class LocalTransport(NetworkTransport):
    """In-process transport for tests and single-player mode."""

    def __init__(self) -> None:
        self._queue: queue.Queue[NetworkMessage] = queue.Queue()

    def send(self, message: NetworkMessage) -> None:
        self._queue.put(message)

    def receive(self, timeout: float = 0.0) -> Optional[NetworkMessage]:
        try:
            return self._queue.get(timeout=timeout if timeout > 0 else None)
        except queue.Empty:
            return None


class NetworkClient:
    """A simple network client."""

    def __init__(self, transport: NetworkTransport, client_id: int) -> None:
        self.transport = transport
        self.client_id = client_id
        self._handlers: dict[MessageType, list[Callable[[NetworkMessage], None]]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sequence = 0

    def on(self, message_type: MessageType,
           handler: Callable[[NetworkMessage], None]) -> None:
        self._handlers.setdefault(message_type, []).append(handler)

    def send(self, message_type: MessageType, payload: dict[str, Any],
             target_id: Optional[int] = None) -> None:
        self._sequence += 1
        msg = NetworkMessage(
            type=message_type, payload=payload,
            sender_id=self.client_id, target_id=target_id,
            sequence=self._sequence,
        )
        self.transport.send(msg)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while self._running:
            msg = self.transport.receive(timeout=0.1)
            if msg is None:
                continue
            handlers = self._handlers.get(msg.type, [])
            for h in handlers:
                try:
                    h(msg)
                except Exception:  # noqa: BLE001
                    log.exception("Network handler raised")


class NetworkServer:
    """A simple network server (multi-client)."""

    def __init__(self) -> None:
        self._clients: dict[int, NetworkTransport] = {}
        self._handlers: dict[MessageType, list[Callable[[NetworkMessage], None]]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._next_client_id = 1

    def connect_client(self, transport: NetworkTransport) -> int:
        client_id = self._next_client_id
        self._next_client_id += 1
        self._clients[client_id] = transport
        return client_id

    def disconnect_client(self, client_id: int) -> None:
        self._clients.pop(client_id, None)

    def on(self, message_type: MessageType,
           handler: Callable[[NetworkMessage], None]) -> None:
        self._handlers.setdefault(message_type, []).append(handler)

    def broadcast(self, message_type: MessageType, payload: dict[str, Any],
                  exclude: Optional[int] = None) -> None:
        for cid, transport in self._clients.items():
            if cid == exclude:
                continue
            transport.send(NetworkMessage(
                type=message_type, payload=payload, sender_id=0,
                target_id=cid,
            ))

    def send_to(self, client_id: int, message_type: MessageType,
                payload: dict[str, Any]) -> None:
        transport = self._clients.get(client_id)
        if transport:
            transport.send(NetworkMessage(
                type=message_type, payload=payload,
                sender_id=0, target_id=client_id,
            ))

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while self._running:
            for cid, transport in list(self._clients.items()):
                msg = transport.receive(timeout=0.0)
                if msg is None:
                    continue
                msg.sender_id = cid
                handlers = self._handlers.get(msg.type, [])
                for h in handlers:
                    try:
                        h(msg)
                    except Exception:  # noqa: BLE001
                        log.exception("Server handler raised")
            import time
            time.sleep(0.01)
