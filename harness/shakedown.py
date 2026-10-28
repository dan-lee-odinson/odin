"""Phase 1's clock (CONTRACT.md §1, §10.1; the Director's ruling on U58, 28 October 2026).

In phase 1 ODIN flies COSMOS's demo spacecraft, which simulates itself inside COSMOS: there is no HUGINN to
step. The run's clock still ticks once a second in real time, and its MET counts whole seconds from the start
of the run's plan, so the plan's span, the check-ins and every record keep the times the run gives them. The
demo is always in contact. This stands where the simulator stands for RunClock, and steps nothing.
"""


class Shakedown:
    dt = 1.0

    def __init__(self, start_at=0):
        self.start_met_s = self.met_s = int(start_at)
        self.t_s = float(start_at)
        self.spacecraft = self   # RunClock reads the clock's time and step from here
        self.applied = []

    def step(self):
        """One tick of the run's MET. No frame is generated here; the harness reads COSMOS's."""
        self.met_s = int(self.t_s)
        self.t_s += self.dt
        return None
