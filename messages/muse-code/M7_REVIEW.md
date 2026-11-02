Review of M7, from the Director. Good work, and thank you for the honesty note about the red case. Fix these before I freeze; each one is a contract point. Keep everything rendered from the schemas where a schema has it.

1. Rungs. This build has two, AI_AUTONOMOUS and HUMAN_ONLY (contract §7.4 and contract/schemas). AI_PROPOSE and SAFE_HOLD are not in it, and no human ever sends a command. Render the rungs from the schema's enum, with a red case.
2. The protective commands are open at AI_AUTONOMOUS whatever the plan says; at HUMAN_ONLY they are refused like everything else (§5.5). "Always open to you" is wrong.
3. Remove "Without fresh telemetry, prefer to wait." The instructions describe the system; what to do comes from the plan and the procedures in force. Add no advice of your own.
4. VOIDED: BALDUR-0 rechecks every allowed command just before dispatch and voids it if the result or its basis changed (§9.3); a plan boundary is one case among others. A REFUSE names the first check that failed (U14).
5. The history tool returns one row per received frame (U3), up to 3,600 s. Nothing is downsampled: remove the 50 buckets. The bundle's own history is the last 300 s of the points the procedures name.
6. A check-in report answers the Director's words. There is no astronaut.
7. Turn rhythm: a plan has objectives and a contact window, not a schedule. Say that.
8. Explain contact_state and seat (§6.2): GROUND works COSMOS, ONBOARD reads beside the simulator, and out of contact escalations queue until acquisition of signal (§7.1). Explain each observation field as contract §6.4 and the schema give it, including the ground interface's state and received packet count, which arrive with Claude Code's next refresh (my ruling of tonight). If they aren't in your schemas yet, say so.
9. In an escalation, proposed is a command with its parameters, or null (U11).

Then show me the changed text and stop. Don't freeze or deposit yet: I'll say when.
