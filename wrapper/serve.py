"""Fly a HUGINN scenario through the link, for ODIN's COSMOS, without ODIN.

    python -m wrapper.serve P1_nominal --contact 0 410 --until 430
    python -m wrapper.serve P1_nominal --contact 0 410 --until 430 --receiver-down 100 160

The simulator runs in real time from --start-at to --until, and the link carries frames down and
commands up inside each --contact window, AOS and LOS as whole-second METs. The scenario's scripted
commands inside a window are dropped and the rest kept (the Director's ruling on U35). --receiver-down
drops the frames stamped inside its window at the ground receiver while COSMOS stays connected. Every
tenth frame, each command that reaches the spacecraft and each change of contact or receiver is printed.
"""

import argparse
import sys

from wrapper.clock import RunClock
from wrapper.huginn import load_scenario
from wrapper.link import Link
from wrapper.simulator import Simulator


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", help="a scenario in deps/huginn/sim/scenarios/, or a path to one")
    parser.add_argument("--contact", nargs=2, type=int, action="append", required=True, metavar=("AOS", "LOS"))
    parser.add_argument("--start-at", type=int, default=0, metavar="MET")
    parser.add_argument("--until", type=int, required=True, metavar="MET")
    parser.add_argument("--rate", type=float, default=1.0, help="simulated seconds per wall-clock second")
    parser.add_argument("--receiver-down", nargs=2, type=int, action="append", default=[], metavar=("FROM", "TO"))
    args = parser.parse_args(argv)

    link = Link(args.contact).start()
    simulator = Simulator(load_scenario(args.scenario), windows=args.contact, link=link, start_at=args.start_at)
    scenario = simulator.scenario
    shown = {"state": None, "applied": 0}

    def before_next_tick():
        # The receiver's state and the contact for the tick about to be stepped.
        upcoming = int(simulator.spacecraft.t_s)
        link.receiver_up = not any(start <= upcoming < end for start, end in args.receiver_down)
        state = (f"{'IN CONTACT' if link.in_contact(upcoming) else 'OUT OF CONTACT'}, "
                 f"{'receiver up' if link.receiver_up else 'receiver DOWN'}")
        if state != shown["state"]:
            print(f"  MET {upcoming:6d}  {state}", flush=True)
            shown["state"] = state

    def on_tick(frame):
        met_s = simulator.met_s
        for when, name, accepted, reason in simulator.applied[shown["applied"]:]:
            print(f"  MET {when:6d}  command {name}: {'ACCEPTED' if accepted else 'REJECTED ' + reason}", flush=True)
        shown["applied"] = len(simulator.applied)
        if frame is not None and met_s % 10 == 0:
            print(f"  MET {met_s:6d}  frame {frame['CDH_FRAME_CNT']}  COSMOS connections {link.clients}  "
                  f"sent {link.counts['SENT']}  dropped {link.counts['RECEIVER_DOWN']}", flush=True)
        before_next_tick()

    host, port = link.address
    print(f"serving {scenario.scenario_id} on {host}:{port} from MET {simulator.met_s} to {args.until} "
          f"({args.rate}x real time)", flush=True)
    for command in scenario.commands:
        print(f"  scripted {command['mnemonic']} at MET {command['t_s']}: kept, outside every contact", flush=True)
    for command in simulator.dropped:
        print(f"  scripted {command['mnemonic']} at MET {command['t_s']}: dropped, inside a contact", flush=True)
    before_next_tick()
    clock = RunClock(simulator, until_met_s=args.until, rate=args.rate, on_tick=on_tick)
    try:
        clock.run()
    except KeyboardInterrupt:
        pass
    finally:
        link.stop()
    print(f"stopped at MET {simulator.met_s}: {link.counts}, commands lost out of contact {link.commands_lost}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
