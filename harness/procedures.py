"""The procedures a plan names, as the turn bundle carries them (CONTRACT.md §5.1, §6.2, §16.1 U5).

A plan's procedures_in_force names each procedure by id, version and the SHA-256 of its exact bytes.
The bundle carries each one unchanged, its full text, with its attachments.

The texts are found by the hash of their bytes in the folders the run names: by default the Director's
inputs in inputs-pre-existing/, never its comparison-only/, and plans/. So a plan can name only a
procedure whose exact text is there, and the hash picks the version. A run whose chain names a
procedure or reference that is not there does not start.

Every reference a plan lists is attached beside PROC-001, resolved by its hash, so an attachment's
hash always equals the plan's: the pass plans, the console card, contact A's telemetry, and ODIN's
COSMOS reference and phase-1 notes once they exist (the Director's ruling on U43, 27 October 2026).
A reference whose hash is still all zeros is a placeholder for a file that does not exist yet and is
not attached. Attachments are text, the file's bytes as UTF-8.
"""

from pathlib import Path

from log.canonical import sha256_tag

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = (ROOT / "inputs-pre-existing", ROOT / "plans")
HIDDEN = "comparison-only"   # used only to score ODIN, never shown to it
ATTACHED_TO = "PROC-001"
PLACEHOLDER = "sha256:" + "0" * 64


class MissingProcedure(Exception):
    pass


def references(plan_document):
    """The references a plan lists that name a file, placeholders left out."""
    return [ref for ref in plan_document.get("references", []) if ref["sha256"] != PLACEHOLDER]


class ProcedureLibrary:
    def __init__(self, *folders):
        self._by_hash = {}
        for folder in folders or FOLDERS:
            for path in sorted(Path(folder).rglob("*")):
                if path.is_file() and HIDDEN not in path.relative_to(folder).parts:
                    self._by_hash[sha256_tag(path.read_bytes())] = path

    def missing(self, chain):
        """What the chain's plans name that is not here, each as a line saying what and where."""
        found = []
        for plan in chain.plans:
            document = plan.document
            found += [f"{plan.plan_id}: procedure {ref['id']} {ref['version']} {ref['sha256']}"
                      for ref in document["procedures_in_force"] if ref["sha256"] not in self._by_hash]
            found += [f"{plan.plan_id}: reference {ref['name']!r} {ref['sha256']}"
                      for ref in references(document) if ref["sha256"] not in self._by_hash]
            if references(document) and ATTACHED_TO not in [ref["id"] for ref in document["procedures_in_force"]]:
                found.append(f"{plan.plan_id}: references to attach but no {ATTACHED_TO} in force to attach them beside")
        return found

    def _text(self, sha256, what):
        path = self._by_hash.get(sha256)
        if path is None:
            raise MissingProcedure(f"{what}: no file holds {sha256}")
        return path.read_bytes().decode("utf-8")

    def for_plan(self, plan):
        """The bundle's procedures for the plan in force, in its order, or None with no plan in force."""
        if plan is None:
            return None
        attached = [{"name": ref["name"], "sha256": ref["sha256"], "text": self._text(ref["sha256"], ref["name"])}
                    for ref in references(plan.document)]
        return [{"id": ref["id"], "version": ref["version"], "sha256": ref["sha256"],
                 "text": self._text(ref["sha256"], f"{ref['id']} {ref['version']}"),
                 "attachments": attached if ref["id"] == ATTACHED_TO else []}
                for ref in plan.document["procedures_in_force"]]
