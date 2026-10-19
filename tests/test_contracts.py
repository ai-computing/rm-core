import unittest

from rm_core import Accelerator, ContractError, KVLayout, Measurement, MemoryTier, TransportError, Workload
from rm_core import conformance, k8s, registry
from rm_core.reference import GreedyPlacement, LoopbackTransport, SimAcceleratorProvider


class AcceleratorTest(unittest.TestCase):
    def test_valid(self):
        a = Accelerator(id="n1/furiosa:0", node="n1", vendor="furiosa", model="RNGD",
                        memory_bytes=1, memory_kind="hbm", peak_tflops={"bf16": 1.0}, peak_source="spec sheet")
        self.assertEqual(Accelerator.from_dict(a.to_dict()), a)

    def test_rejects(self):
        bad = [dict(id="bad", vendor="furiosa"), dict(vendor="acme"), dict(memory_kind="sram"),
               dict(peak_tflops={"bf16": 1.0}), dict(peak_tflops={"fp64": 1.0}, peak_source="x"),
               dict(interconnect=["usb"]), dict(node="other")]
        base = dict(id="n1/furiosa:0", vendor="furiosa", model="RNGD", memory_bytes=1, memory_kind="hbm")
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ContractError):
                Accelerator(**{**base, **change}).validate()


class K8sTest(unittest.TestCase):
    def test_profile_roundtrip(self):
        for acc in SimAcceleratorProvider("n1").discover():
            self.assertEqual(k8s.from_profile(k8s.accelerator_profile(acc)), acc)

    def test_profile_keeps_extra(self):
        a = Accelerator(id="n1/furiosa:0", node="n1", vendor="furiosa", model="RNGD", memory_bytes=1,
                        memory_kind="hbm", extra={"pci_bdf": "0000:03:00.0", "firmware": "x"})
        self.assertEqual(k8s.from_profile(k8s.accelerator_profile(a)), a)

    def test_no_hardware_is_one_class(self):
        import subprocess, sys
        from rm_core import errors
        self.assertIs(conformance.NoHardware, errors.NoHardware)
        code = ("import runpy, rm_core.errors as e; g = runpy.run_module('rm_core.conformance', run_name='not_main');"
                "assert g['NoHardware'] is e.NoHardware")
        self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 0)

    def test_node_labels(self):
        labels = k8s.node_labels(SimAcceleratorProvider("n1").discover())
        self.assertEqual(labels["airm.ai-computing.io/furiosa.RNGD"], "1")


class MetricsTest(unittest.TestCase):
    def test_rules(self):
        Measurement("tok_s", 120.5, {"component": "rngd-pd"}).validate()
        for m in [Measurement("tokens_per_sec", 1), Measurement("tok_s", 1, {"host": "x"}),
                  Measurement("mfu_pct", 30), Measurement("power_w", 300)]:
            with self.subTest(m=m), self.assertRaises(ContractError):
                m.validate()


class ReferenceConformanceTest(unittest.TestCase):
    def test_provider(self):
        self.assertTrue(conformance.check_accelerator_provider(SimAcceleratorProvider()))

    def test_transport(self):
        conformance.check_kv_transport(LoopbackTransport())

    def test_transport_failure_is_reported(self):
        t = LoopbackTransport(fail_request_ids=["r"])
        src, dst = MemoryTier("a", "host-dram", 1 << 20), MemoryTier("b", "host-dram", 1 << 20)
        layout = KVLayout(1, 1, 8, "bf16")
        result = t.wait(t.submit(t.plan("r", src, dst, layout, layout, (0, 4))), 1.0)
        self.assertFalse(result.ok)
        with self.assertRaises(TransportError):
            t.plan("r2", src, dst, layout, KVLayout(1, 1, 8, "fp8"), (0, 4))

    def test_placement(self):
        conformance.check_placement(GreedyPlacement())

    def test_workload_validation(self):
        with self.assertRaises(ContractError):
            Workload(kind="decode", model="m", slo={"latency": 1}).validate()


class RegistryTest(unittest.TestCase):
    def test_reference_entry_points(self):
        # Requires `pip install -e .` so the entry points are registered.
        self.assertIn("loopback", registry.available("airm.kv_transports"))
        self.assertIsInstance(registry.load("airm.placements", "greedy"), GreedyPlacement)
        self.assertEqual(conformance.main([]), 0)


if __name__ == "__main__":
    unittest.main()
