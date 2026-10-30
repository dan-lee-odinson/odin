"""The link between the simulator and COSMOS: frames down, commands up (00_HANDOFF.md §4, S4).

COSMOS's HUGINN_INT interface, from HUGINN's plugin unchanged, is a TCP client that dials the
simulator and reads frames by their LENGTH field, and writes each command as its bare bytes. The
link is the server it dials, on the link port of config/ports.yaml, which ODIN's COSMOS gives the
plugin as its huginn_sim_port. HUGINN's own simulator server listens on 7801, where the Director's
HUGINN COSMOS dials; the link never does.

Nothing passes either way out of contact: HUGINN receives telemetry and takes commands only inside a
contact window (HUGINN's CON-01, HUG-GND-005). A window is [aos_met_s, los_met_s), so a frame stamped
at LOS is not received. The ground receiver can also be down: frames are then dropped at the ground
while COSMOS stays connected, which on the console looks as a housekeeping halt does.

Commands are cut from the byte stream by their opcode's length in the dictionary, so two commands
that arrive in one read are both received; an opcode the dictionary does not define takes the rest
of the read, and the spacecraft accounts for it as UNKNOWN_OPCODE.
"""

import socket
import socketserver
import struct
import threading
from pathlib import Path

import yaml

from wrapper.frames import ENDIAN, command_length

PORTS = Path(__file__).resolve().parent.parent / "config" / "ports.yaml"


def link_address(ports=PORTS):
    """The host and port config/ports.yaml gives the link."""
    config = yaml.safe_load(Path(ports).read_text(encoding="utf-8"))
    return config["host"], config["ports"]["link"]


def in_window(met_s, windows):
    """Whether met_s falls inside one of the windows, each (aos_met_s, los_met_s) and half-open."""
    return any(aos <= met_s < los for aos, los in windows)


def split_commands(buffer):
    """(commands, rest): the whole commands at the front of buffer, and the bytes left waiting for
    the rest of a command."""
    commands = []
    while len(buffer) >= 2:
        length = command_length(struct.unpack_from(ENDIAN + "H", buffer, 0)[0])
        if length is None:
            length = len(buffer)
        if len(buffer) < length:
            break
        commands.append(bytes(buffer[:length]))
        buffer = buffer[length:]
    return commands, bytes(buffer)


class Link:
    def __init__(self, contact_windows, address=None, receiver_down=()):
        """contact_windows: the run's contacts as (aos_met_s, los_met_s), each half-open. receiver_down: a
        scenario's scripted ground-receiver fault, as (from_met_s, until_met_s) spans, each half-open (S9, piece 3)."""
        self.windows = sorted((float(aos), float(los)) for aos, los in contact_windows)
        self.receiver_down = sorted((float(start), float(end)) for start, end in receiver_down)
        self.receiver_up = True
        self._address = address or link_address()
        self._lock = threading.Lock()
        self._clients = []
        self._received = []
        self._server = None
        self.counts = {"SENT": 0, "OUT_OF_CONTACT": 0, "RECEIVER_DOWN": 0, "NO_GROUND": 0}
        self.commands_lost = 0

    # -- the server COSMOS dials -------------------------------------------------------------

    def start(self):
        link = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with link._lock:
                    link._clients.append(self.request)
                waiting = b""
                try:
                    while True:
                        data = self.request.recv(4096)
                        if not data:
                            break
                        commands, waiting = split_commands(waiting + data)
                        with link._lock:
                            link._received.extend(commands)
                except OSError:
                    pass
                finally:
                    with link._lock:
                        if self.request in link._clients:
                            link._clients.remove(self.request)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = False
            daemon_threads = True

        self._server = Server(self._address, Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def address(self):
        return self._server.server_address if self._server else self._address

    @property
    def clients(self):
        with self._lock:
            return len(self._clients)

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            with self._lock:
                for client in self._clients:
                    client.close()
                self._clients.clear()
            self._server = None

    # -- what passes -----------------------------------------------------------------------

    # Out of contact the link keeps COSMOS connected and carries nothing either way until the next
    # AOS, as a station that has lost the spacecraft's signal would (the Director's ruling on U34,
    # 27 October 2026). In Dan's passes the simulator was stopped at loss of signal, so his COSMOS
    # showed the interface disconnected until the next start.

    def in_contact(self, met_s):
        return in_window(met_s, self.windows)

    def downlink(self, raw, met_s):
        """Carry one frame stamped met_s to COSMOS. Returns SENT, or why it was not received:
        OUT_OF_CONTACT, RECEIVER_DOWN, or NO_GROUND when COSMOS is not connected."""
        if not self.in_contact(met_s):
            outcome = "OUT_OF_CONTACT"
        elif not self.receiver_up or in_window(met_s, self.receiver_down):
            outcome = "RECEIVER_DOWN"
        else:
            with self._lock:
                for client in list(self._clients):
                    try:
                        client.sendall(raw)
                    except OSError:
                        self._clients.remove(client)
                outcome = "SENT" if self._clients else "NO_GROUND"
        self.counts[outcome] += 1
        return outcome

    def take_commands(self, met_s):
        """The commands COSMOS has sent since the last call, to reach the spacecraft at met_s. Out of
        contact they are lost and none is returned."""
        with self._lock:
            commands, self._received = self._received, []
        if commands and not self.in_contact(met_s):
            self.commands_lost += len(commands)
            return []
        return commands
