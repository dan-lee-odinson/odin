"""The run's clock: how simulation time passes against wall-clock time (CONTRACT.md §4, §10.1).

REAL_TIME steps the simulator one tick per wall-clock second, as in phases 1 and 2 and in phase 3's
ground seat. Like HUGINN's serve_sim.py it sleeps against the total elapsed since pacing began, so
drift never accumulates over a long pass.

CHARGED is phase 3's onboard seat, out of contact (the Director's ruling, §10.1): the simulator pauses
while ODIN takes a turn, then advances by at least the turn's measured wall-clock time before
BALDUR-0's dispatch recheck. Thinking time costs simulation time, and quiet stretches run faster than
real time. The harness pauses the clock from on_tick, at the tick that raises a turn's trigger, and
calls charge() with the turn's measured time when the turn ends.

on_tick(frame) runs after every tick, in whichever thread stepped it. met_s is the MET of the newest
tick, the clock BALDUR-0 and the logs read.
"""

import math
import threading
import time

PACINGS = ("REAL_TIME", "CHARGED")


class RunClock:
    def __init__(self, simulator, *, until_met_s, pacing="REAL_TIME", rate=1.0, on_tick=None,
                 wall=time.monotonic, sleep=time.sleep):
        """until_met_s: the MET the run ends at. rate: simulated seconds per wall-clock second in
        REAL_TIME, 1.0 in every scored run; tests run faster."""
        if pacing not in PACINGS:
            raise ValueError(f"pacing {pacing!r} is not one of {PACINGS}")
        self.simulator = simulator
        self.until_met_s = until_met_s
        self.rate = rate
        self.on_tick = on_tick
        self._wall = wall
        self._sleep = sleep
        self._pacing = pacing
        self._paused = False
        self._stopped = False
        self._turn = threading.Lock()
        self._changed = threading.Condition()
        self._thread = None
        self._restart_pacing()

    @property
    def met_s(self):
        return self.simulator.met_s

    @property
    def pacing(self):
        return self._pacing

    @property
    def finished(self):
        return self.simulator.spacecraft.t_s >= self.until_met_s

    # -- running -------------------------------------------------------------------------------

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return self

    def run(self):
        """Step until the run ends or stop() is called."""
        while True:
            with self._changed:
                while self._paused and not self._stopped:
                    self._changed.wait()
                if self._stopped or self.finished:
                    return
            self._tick()
            if self._pacing == "REAL_TIME":
                self._keep_pace()

    def stop(self):
        with self._changed:
            self._stopped = True
            self._changed.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def set_pacing(self, pacing):
        """Change pacing, at loss or acquisition of signal in phase 3."""
        if pacing not in PACINGS:
            raise ValueError(f"pacing {pacing!r} is not one of {PACINGS}")
        with self._changed:
            self._pacing = pacing
            self._paused = False
            self._restart_pacing()
            self._changed.notify_all()

    # -- a turn in the onboard seat ------------------------------------------------------------

    def pause(self):
        """Stop the simulator before its next tick while ODIN takes a turn. Only in CHARGED pacing."""
        with self._changed:
            if self._pacing != "CHARGED":
                raise RuntimeError("the simulator pauses for a turn only in CHARGED pacing")
            self._paused = True

    def charge(self, wall_seconds):
        """Advance the paused simulator by the turn's measured wall-clock time, rounded up to whole
        ticks so that it is never less, and leave it paused for BALDUR-0's recheck. Returns the ticks
        stepped."""
        with self._changed:
            if not self._paused:
                raise RuntimeError("charge() is for a paused clock")
        # By the Director's ruling on U37 (27 October 2026): (a) the charge is rounded up to whole
        # ticks; (b) quiet stretches run as fast as the simulator steps; (c) a turn's time runs from
        # the bundle served to BALDUR-0's receipt of the request, or to ODIN's next request for a turn
        # when it sends none. The harness measures (c) and passes it here.
        ticks = math.ceil(wall_seconds / self.simulator.spacecraft.dt)
        stepped = 0
        while stepped < ticks and not self.finished:
            self._tick()
            stepped += 1
        return stepped

    def resume(self):
        """Let the simulator run on after the turn's dispatch."""
        with self._changed:
            self._paused = False
            self._changed.notify_all()

    # -- inside ----------------------------------------------------------------------------------

    def _tick(self):
        with self._turn:
            frame = self.simulator.step()
        if self.on_tick is not None:
            self.on_tick(frame)

    def _restart_pacing(self):
        self._paced_from = (self._wall(), self.simulator.spacecraft.t_s)

    def _keep_pace(self):
        wall0, t0 = self._paced_from
        gap = wall0 + (self.simulator.spacecraft.t_s - t0) / self.rate - self._wall()
        if gap > 0:
            self._sleep(gap)
