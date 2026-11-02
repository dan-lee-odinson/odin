"""Phase 3's chosen contacts, SAA transits and fault times, checked against each other and against HUGINN's
pinned orbit. Held out. Reads HUGINN; writes nothing.

Contacts and transits are HUGINN's own intervals (Orbit.contact_windows and Orbit.saa_transits on their
10 s grid, half-open), as its campaign plan computes them. Each boundary is also found to the second
with HUGINN's own visible_at and in_saa_at, to show how far the grid sits from it.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HUGINN = Path(__file__).resolve().parents[2] / "deps" / "huginn"
sys.path.insert(0, str(HUGINN))

from sim.orbit import Orbit  # noqa: E402

CAMPAIGN_EPOCH = "2026-07-29T14:00:00Z"
WEEK_S = 7 * 86400.0
LEAD_S = 7200          # the Director's approval: first contact 2 h after each scenario's start
DAMAGE_S = 120         # phase-3 document, scenario C

orbit = Orbit(HUGINN / "defs" / "orbit", CAMPAIGN_EPOCH)
EPOCH = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
contacts = orbit.contact_windows(WEEK_S)
transits = orbit.saa_transits(WEEK_S)


def utc(t):
    return (EPOCH + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%SZ")


def edge(predicate, t, before):
    """The first whole second at or after t - 10 at which predicate turns to `not before`."""
    s = t - 10
    while predicate(s) == before:
        s += 1
    return s


def contact(n):
    return contacts[n - 1]


def transit_before(aos):
    return [s for s in transits if s[1] <= aos][-1]


failures = []


def require(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def report(name, rows, epoch_s):
    print(f"\n{name}: scenario epoch {utc(epoch_s)} (campaign t {epoch_s:.0f} s)")
    for label, t in rows:
        print(f"  {label:<34} {utc(t)}   MET {t - epoch_s:>6.0f}   campaign t {t:>8.0f}")


# --- C: contacts 14 and 15, the latch-up in the one SAA transit between them -------------------------------
aos14, los14 = contact(14)
aos15, los15 = contact(15)
between = [s for s in transits if los14 <= s[0] and s[1] <= aos15]
require(len(between) == 1, f"exactly one SAA transit of 60 s or more between contacts 14 and 15 ({len(between)})")
t0, t1 = between[0]
latch = (t0 + t1) / 2
damage = latch + DAMAGE_S
epoch_c = aos14 - LEAD_S
report("C", [("contact 14 acquisition", aos14), ("contact 14 loss of signal", los14), ("SAA transit start", t0),
             ("SAA transit middle = latch-up", latch), ("damage time (latch-up + 120 s)", damage),
             ("SAA transit end", t1), ("contact 15 acquisition", aos15), ("contact 15 loss of signal", los15)],
       epoch_c)
print(f"  gaps: LOS 14 to transit start {t0 - los14:.0f} s ({(t0 - los14) / 60:.1f} min); transit {t1 - t0:.0f} s; "
      f"damage to transit end {t1 - damage:.0f} s; transit end to AOS 15 {aos15 - t1:.0f} s; "
      f"damage to AOS 15 {aos15 - damage:.0f} s ({(aos15 - damage) / 60:.1f} min); "
      f"LOS 14 to AOS 15 {aos15 - los14:.0f} s ({(aos15 - los14) / 60:.1f} min)")
require(los14 < t0 < latch < damage < t1 < aos15, "LOS 14 < transit start < latch-up < damage < transit end < AOS 15")
require(orbit.in_saa_at(latch) and orbit.in_saa_at(damage), "latch-up and damage both inside the SAA box")
# The true edges, to the second. HUGINN's grid takes the first 10 s sample past each edge, so it lags by 1-10 s.
true = {"AOS 14": edge(orbit.visible_at, aos14, False), "LOS 14": edge(orbit.visible_at, los14, True),
        "transit start": edge(orbit.in_saa_at, t0, False), "transit end": edge(orbit.in_saa_at, t1, True),
        "AOS 15": edge(orbit.visible_at, aos15, False), "LOS 15": edge(orbit.visible_at, los15, True)}
grid = {"AOS 14": aos14, "LOS 14": los14, "transit start": t0, "transit end": t1, "AOS 15": aos15, "LOS 15": los15}
print("  true edges to the second: " + ", ".join(f"{k} {v:.0f} (grid {grid[k]:.0f}, {grid[k] - v:+.0f} s)"
                                                 for k, v in true.items()))
require(all(0 < grid[k] - true[k] <= 10 for k in true), "every grid edge lags its true edge by 1-10 s")
require(not any(orbit.visible_at(t) for t in range(int(true["LOS 14"]), int(true["AOS 15"]))),
        "the station sees nothing from the true LOS 14 to the true AOS 15, second by second")
require(all(orbit.in_saa_at(t) for t in range(int(true["transit start"]), int(true["transit end"]))),
        "inside the SAA box every second of the true transit")
require(true["transit start"] < latch < damage < true["transit end"], "latch-up and damage inside the true transit")
require(epoch_c > 0 and not any(orbit.visible_at(t) for t in range(int(epoch_c), int(true["AOS 14"]))),
        "no contact in the 2 h lead before the true AOS 14")

# --- A, B and D: contact 6; A's halt in the last SAA transit before it -------------------------------------
aos6, los6 = contact(6)
h0, h1 = transit_before(aos6)
halt = (h0 + h1) / 2
epoch_a = aos6 - LEAD_S
report("A, B and D", [("SAA transit start", h0), ("SAA transit middle = A's halt", halt), ("SAA transit end", h1),
                      ("contact 6 acquisition", aos6), ("contact 6 loss of signal", los6)], epoch_a)
require(epoch_a < h0 < halt < h1 < aos6 < los6, "epoch < transit start < halt < transit end < AOS 6 < LOS 6")
require(orbit.in_saa_at(halt), "A's halt inside the SAA box")
true6 = {"transit start": edge(orbit.in_saa_at, h0, False), "transit end": edge(orbit.in_saa_at, h1, True),
         "AOS 6": edge(orbit.visible_at, aos6, False), "LOS 6": edge(orbit.visible_at, los6, True)}
grid6 = {"transit start": h0, "transit end": h1, "AOS 6": aos6, "LOS 6": los6}
print("  true edges to the second: " + ", ".join(f"{k} {v:.0f} (grid {grid6[k]:.0f}, {grid6[k] - v:+.0f} s)"
                                                 for k, v in true6.items()))
require(all(0 < grid6[k] - true6[k] <= 10 for k in true6), "every grid edge lags its true edge by 1-10 s")
require(true6["transit start"] < halt < true6["transit end"], "A's halt inside the true transit")
require(not any(orbit.visible_at(t) for t in range(int(epoch_a), int(true6["AOS 6"]))),
        "no contact in the 2 h lead before the true AOS 6")
require(not [s for s in transits if h1 <= s[0] < aos6], "no later transit before contact 6")

require(not [(c, s) for c in contacts for s in transits if s[0] < c[1] and c[0] < s[1]],
        "no SAA transit overlaps any contact in the week")
print("\nALL CHECKS HOLD" if not failures else f"\n{len(failures)} CHECKS FAIL")
sys.exit(1 if failures else 0)
