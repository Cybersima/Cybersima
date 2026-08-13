import unittest

from network_guard.detector import PacketMeta, ThreatDetector


class DetectorTests(unittest.TestCase):
    def test_port_scan_triggers_block(self) -> None:
        detector = ThreatDetector(scan_ports_threshold=5, scan_window_sec=5)
        findings = []
        for port in range(20, 30):
            findings.extend(
                detector.observe(
                    PacketMeta(
                        src_ip="203.0.113.9",
                        dst_ip="192.168.1.1",
                        dst_port=port,
                        protocol="TCP",
                        syn=True,
                    )
                )
            )
        self.assertTrue(any(f.category == "port_scan" and f.should_block for f in findings))

    def test_threat_intel_match(self) -> None:
        detector = ThreatDetector(threat_ips={"198.51.100.66"})
        findings = detector.observe(
            PacketMeta(
                src_ip="198.51.100.66",
                dst_ip="192.168.1.1",
                dst_port=22,
                protocol="TCP",
                syn=True,
            )
        )
        self.assertEqual(findings[0].category, "threat_intel")


if __name__ == "__main__":
    unittest.main()
