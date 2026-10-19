import copy
import json
import os
import unittest
from datetime import datetime, timezone

from rm_core import ContractError, PlacementDecision, Workload
from rm_core import accelerator, conformance, placement, workload
from rm_core.placement import Decision, PlacementDocument

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "k8s", "airm-placement.schema.json")

# What the existing writers and readers already exchange (protocol 0.1):
EMPTY = {"protocol": "0.1", "generation": 0, "updatedAt": None, "decisions": []}   # hetero-llm-d default
HETERO_LLM_D_EXAMPLE = {   # hetero-llm-d deploy/airm/README.md
    "protocol": "0.1", "generation": 12, "updatedAt": "2026-10-19T00:00:00Z", "placement": "greedy",
    "decisions": [{"pool": "llama8b-pd-pool",
                   "workload": {"kind": "decode", "model": "meta-llama/Llama-3.1-8B-Instruct",
                                "slo": {"tpot_p90_ms": 40}, "labels": {}},
                   "acceleratorIds": ["node-a/furiosa:0", "node-a/furiosa:1"], "kvTransport": "p2p",
                   "reason": "lowest tpot_p90 within SLO"}]}
RM_CONTROLLER_OUTPUT = {   # ai-rm rm-controller (document.py), hetero P2P example spec
    "protocol": "0.1", "generation": 1, "updatedAt": "2026-10-19T01:02:03Z", "placement": "topology",
    "decisions": [
        {"pool": "koni-hetero-pd-pool",
         "workload": {"kind": "prefill", "model": "KISTI-KONI/KONI-Llama3.1-8B-Instruct-20241024", "slo": {},
                      "labels": {"airm.ai-computing.io/accelerator": "furiosa.RNGD"}},
         "acceleratorIds": ["node-a/furiosa:0"], "kvTransport": "p2p", "reason": "highest peak"},
        {"pool": "koni-hetero-pd-pool",
         "workload": {"kind": "decode", "model": "KISTI-KONI/KONI-Llama3.1-8B-Instruct-20241024", "slo": {},
                      "labels": {"airm.ai-computing.io/accelerator": "rebellions.ATOM"}},
         "acceleratorIds": ["node-a/rebellions:0", "node-a/rebellions:1"], "kvTransport": "p2p",
         "reason": "most memory"}]}
LMD_TOP_FIXTURE = {   # lmd-top src/airm.rs test
    "protocol": "0.1", "generation": 1, "placement": "manual", "updatedAt": "2026-10-19T00:00:00Z",
    "decisions": [
        {"pool": "llama8b-pd-pool", "workload": {"kind": "prefill", "model": "m"},
         "acceleratorIds": ["n/furiosa:0"], "kvTransport": "shm", "reason": "pinned"},
        {"pool": "llama8b-pd-pool", "workload": {"kind": "decode", "model": "m"},
         "acceleratorIds": ["n/furiosa:1"], "kvTransport": "shm", "reason": "next to prefill"}]}
VALID = [EMPTY, HETERO_LLM_D_EXAMPLE, RM_CONTROLLER_OUTPUT, LMD_TOP_FIXTURE]


def _change(doc, path, value):
    """A copy of doc with the value at path (keys/indexes) replaced; value=KeyError deletes it."""
    out = copy.deepcopy(doc)
    target = out
    for k in path[:-1]:
        target = target[k]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return out


INVALID = [
    ("not an object", []),
    ("no protocol", _change(EMPTY, ["protocol"], KeyError)),
    ("protocol not MAJOR.MINOR", _change(EMPTY, ["protocol"], "v0.1")),
    ("other major", _change(EMPTY, ["protocol"], "1.0")),
    ("negative generation", _change(EMPTY, ["generation"], -1)),
    ("bool generation", _change(EMPTY, ["generation"], True)),
    ("no updatedAt", _change(EMPTY, ["updatedAt"], KeyError)),
    ("local time", _change(HETERO_LLM_D_EXAMPLE, ["updatedAt"], "2026-10-19T09:00:00+09:00")),
    ("null updatedAt after a write", _change(HETERO_LLM_D_EXAMPLE, ["updatedAt"], None)),
    ("no policy name after a write", _change(HETERO_LLM_D_EXAMPLE, ["placement"], KeyError)),
    ("decisions at generation 0", _change(HETERO_LLM_D_EXAMPLE, ["generation"], 0)),
    ("decisions not a list", _change(EMPTY, ["decisions"], {})),
    ("no pool", _change(LMD_TOP_FIXTURE, ["decisions", 0, "pool"], "")),
    ("unknown kind", _change(LMD_TOP_FIXTURE, ["decisions", 0, "workload", "kind"], "any")),
    ("no model", _change(LMD_TOP_FIXTURE, ["decisions", 0, "workload", "model"], KeyError)),
    ("unknown SLO", _change(HETERO_LLM_D_EXAMPLE, ["decisions", 0, "workload", "slo"], {"latency": 1})),
    ("bad accelerator id", _change(LMD_TOP_FIXTURE, ["decisions", 0, "acceleratorIds"], ["furiosa:0"])),
    ("duplicate card", _change(LMD_TOP_FIXTURE, ["decisions", 0, "acceleratorIds"], ["n/furiosa:0"] * 2)),
    ("empty without reason", _change(_change(LMD_TOP_FIXTURE, ["decisions", 0, "acceleratorIds"], []),
                                     ["decisions", 0, "reason"], "")),
    ("bad label", _change(RM_CONTROLLER_OUTPUT, ["decisions", 0, "workload", "labels",
                                                  "airm.ai-computing.io/accelerator"], "RNGD")),
    ("card of another vendor", _change(RM_CONTROLLER_OUTPUT, ["decisions", 1, "acceleratorIds"],
                                       ["node-a/furiosa:1"])),
    ("same pool and kind twice", _change(LMD_TOP_FIXTURE, ["decisions", 1, "workload", "kind"], "prefill")),
    ("kvTransport not a string", _change(LMD_TOP_FIXTURE, ["decisions", 0, "kvTransport"], None)),
]


class ValidateTest(unittest.TestCase):
    def test_existing_documents_are_valid(self):
        for doc in VALID:
            with self.subTest(doc=doc.get("placement")):
                self.assertEqual(placement.validate(doc), [])

    def test_violations_are_reported(self):
        for name, doc in INVALID:
            with self.subTest(name), self.assertRaises(ContractError):
                self.assertTrue(placement.validate(doc))
                PlacementDocument.from_dict(doc)

    def test_unknown_fields_are_ignored(self):
        doc = copy.deepcopy(LMD_TOP_FIXTURE)
        doc["future"] = {"x": 1}
        doc["decisions"][0]["cost"] = 3
        doc["decisions"][0]["workload"]["shape"] = "chat"
        self.assertEqual(placement.validate(doc), [])
        self.assertEqual(PlacementDocument.from_dict(doc), PlacementDocument.from_dict(LMD_TOP_FIXTURE))

    def test_newer_minor_is_accepted(self):
        self.assertEqual(placement.validate(_change(EMPTY, ["protocol"], "0.9")), [])


class ModelTest(unittest.TestCase):
    def test_round_trip(self):
        for doc in VALID:
            with self.subTest(doc=doc.get("placement")):
                model = PlacementDocument.from_dict(doc)
                self.assertEqual(PlacementDocument.from_dict(json.loads(model.to_json())), model)

    def test_rm_controller_output_is_reproduced_exactly(self):
        # rm-controller can switch to rm_core.placement without bumping generation on the live document.
        self.assertEqual(PlacementDocument.from_dict(RM_CONTROLLER_OUTPUT).to_dict(), RM_CONTROLLER_OUTPUT)

    def test_decision_accessors(self):
        d = PlacementDocument.from_dict(RM_CONTROLLER_OUTPUT).for_pool("koni-hetero-pd-pool")[1]
        self.assertEqual(d.workload.kind, "decode")
        self.assertEqual(d.nodes, ["node-a"])
        self.assertEqual(d.decision, PlacementDecision(["node-a/rebellions:0", "node-a/rebellions:1"], "p2p",
                                                       "most memory"))

    def test_parse_configmap(self):
        self.assertEqual(placement.parse(None), PlacementDocument())
        self.assertEqual(placement.parse({"data": {}}), PlacementDocument())
        cm = placement.configmap(PlacementDocument.from_dict(LMD_TOP_FIXTURE), "llm-serving")
        self.assertEqual(cm["metadata"]["name"], "airm-placement")
        self.assertEqual(cm["metadata"]["annotations"]["airm.ai-computing.io/protocol"], "0.1")
        self.assertEqual(placement.parse(cm), PlacementDocument.from_dict(LMD_TOP_FIXTURE))
        with self.assertRaises(ContractError):
            placement.parse({"data": {"decisions.json": "{not json"}})


class BuildTest(unittest.TestCase):
    T = datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc)

    def entries(self, ids):
        w = Workload(kind="decode", model="m")
        return [Decision.from_placement("p", w, PlacementDecision(ids, "shm", "most memory"))]

    def test_generation_moves_only_on_change(self):
        doc0 = PlacementDocument()
        doc1, changed = placement.build(self.entries(["n/furiosa:0"]), doc0, "topology", now=self.T)
        self.assertTrue(changed)
        self.assertEqual((doc1.generation, doc1.updated_at), (1, "2026-10-19T01:02:03Z"))
        same, changed = placement.build(self.entries(["n/furiosa:0"]), doc1, "topology")
        self.assertFalse(changed)
        self.assertIs(same, doc1)
        doc2, changed = placement.build(self.entries(["n/furiosa:1"]), doc1, "topology")
        self.assertTrue(changed and doc2.generation == 2)
        doc3, changed = placement.build(self.entries(["n/furiosa:1"]), doc2, "optimal")
        self.assertTrue(changed and doc3.generation == 3)

    def test_reader_rule(self):
        doc = PlacementDocument.from_dict(HETERO_LLM_D_EXAMPLE)
        self.assertTrue(placement.is_newer(doc, None))
        self.assertTrue(placement.is_newer(doc, 11))
        self.assertFalse(placement.is_newer(doc, 12))

    def test_invalid_decisions_are_not_written(self):
        w = Workload(kind="decode", model="m")
        bad = [Decision.from_placement("p", w, PlacementDecision([], "shm", ""))]
        with self.assertRaises(ContractError):
            placement.build(bad, PlacementDocument(), "topology")


class SchemaTest(unittest.TestCase):
    def setUp(self):
        with open(SCHEMA, encoding="utf-8") as f:
            self.schema = json.load(f)

    def test_enumerations_match_the_code(self):
        wl = self.schema["$defs"]["workload"]["properties"]
        self.assertEqual(tuple(wl["kind"]["enum"]), workload.WORKLOAD_KINDS)
        self.assertEqual(tuple(wl["slo"]["propertyNames"]["enum"]), workload.SLO_KEYS)
        self.assertEqual(tuple(wl["precision"]["enum"]), accelerator.PRECISIONS)
        label = wl["labels"]["properties"][placement.ACCELERATOR_LABEL]["pattern"]
        self.assertTrue(label.startswith("^(" + "|".join(accelerator.VENDORS) + ")\\."))
        ids = self.schema["$defs"]["decision"]["properties"]["acceleratorIds"]["items"]["pattern"]
        self.assertEqual(ids, accelerator._ID.pattern)

    def test_schema_agrees_on_the_examples(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed (optional; the stdlib validator is normative in code)")
        v = jsonschema.Draft202012Validator(self.schema)
        for doc in VALID:
            self.assertEqual([e.message for e in v.iter_errors(doc)], [])
        # Structural violations the schema can express must fail it too.
        for name, doc in INVALID:
            if name in ("decisions at generation 0", "null updatedAt after a write", "no policy name after a write",
                        "card of another vendor", "same pool and kind twice"):
                continue   # cross-field rules: rm_core.placement.validate only
            with self.subTest(name):
                self.assertTrue(list(v.iter_errors(doc)), name)


class ConformanceTest(unittest.TestCase):
    def test_bad_document_fails_placement_check(self):
        class NoReason:
            name = "no-reason"

            def place(self, workload, pool, metrics=None):
                return PlacementDecision([], "", "empty pool" if not pool else "")

        with self.assertRaisesRegex(AssertionError, "airm-placement document"):
            conformance.check_placement(NoReason())


if __name__ == "__main__":
    unittest.main()
