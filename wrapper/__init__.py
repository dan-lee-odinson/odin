"""The simulator wrapper, the link and the onboard tap (CONTRACT.md §3; 00_HANDOFF.md §4, S4).

huginn.py loads HUGINN unchanged; frames.py reads and writes its bytes as COSMOS does; link.py carries
frames down and commands up between the simulator and COSMOS; simulator.py steps HUGINN with the link,
the onboard tap and the truth file beside it; clock.py paces it in real time, or pauses and charges it
for phase 3's onboard seat (§10.1); serve.py flies a scenario through the link without ODIN.
"""
