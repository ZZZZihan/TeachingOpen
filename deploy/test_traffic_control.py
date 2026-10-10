"""Independent behavior tests. No network, credentials, or real cloud writes."""

import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traffic_control import AlibabaCloud, Config, Ledger, process_lock, run_once


UTC = dt.timezone.utc
CREATED = dt.datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
OCTOBER_NOW = dt.datetime(2026, 10, 31, 15, 55, tzinfo=UTC)
NOVEMBER_START = dt.datetime(2026, 10, 31, 16, 0, tzinfo=UTC)
NOVEMBER_NOW = dt.datetime(2026, 10, 31, 22, 5, tzinfo=UTC)
GB = 1_000_000_000


def timestamp_ms(value):
    return int(value.timestamp() * 1000)


def settled_end(now, seconds=300):
    seconds_since_epoch = int((now - dt.timedelta(seconds=seconds)).timestamp())
    return dt.datetime.fromtimestamp(seconds_since_epoch // 60 * 60, tz=UTC)


class FakeCloud:
    """CMS endpoints use minute end timestamps and (start, end] windows."""

    instance_id = "i-2zetrafficcontroltest"
    public_ip = "203.0.113.77"

    def __init__(self):
        self.bandwidth = 100
        self.points = {}
        self.hidden_points = set()
        self.duplicate_points = False
        self.calls = []
        self.metric_queries = []
        self.write_mode = "immediate"
        self.read_error = None
        self.metric_error = None
        self.description_changes = {}

    def describe(self):
        if self.read_error:
            raise self.read_error
        result = {
            "InstanceId": self.instance_id,
            "RegionId": "cn-beijing",
            "CreationTime": CREATED.isoformat().replace("+00:00", "Z"),
            "Status": "Running",
            "InstanceNetworkType": "vpc",
            "InternetChargeType": "PayByTraffic",
            "InternetMaxBandwidthOut": self.bandwidth,
            "PublicIpAddress": {"IpAddress": [self.public_ip]},
            "EipAddress": {"IpAddress": "", "AllocationId": ""},
            "OperationLocks": {"LockReason": []},
        }
        result.update(copy.deepcopy(self.description_changes))
        return result

    def metrics(self, start_ms, end_ms):
        self.metric_queries.append((start_ms, end_ms))
        if self.metric_error:
            raise self.metric_error
        points = [
            copy.deepcopy(point)
            for stamp, point in sorted(self.points.items())
            if start_ms < stamp <= end_ms and stamp not in self.hidden_points
        ]
        if self.duplicate_points:
            points += copy.deepcopy(points)
        return points

    def set_bandwidth(self, target, token):
        self.calls.append((target, token))
        if self.write_mode == "fail_before_effect":
            raise OSError("synthetic request failed before effect")
        if self.write_mode in {"immediate", "fail_after_effect", "readback_error"}:
            self.bandwidth = target
        if self.write_mode == "readback_error":
            self.read_error = OSError("synthetic readback unavailable")
        if self.write_mode == "fail_after_effect":
            raise OSError("synthetic response lost after effect")

    def populate(self, start, end, total_bytes):
        """Produce complete minute data without exceeding 100 Mbps for our totals.

        Most points have byte totals divisible by 15, allowing integer bit/s
        averages. A separate small remainder avoids accumulated floating error
        accidentally putting an exact threshold on the wrong side.
        """
        start_seconds = start.timestamp()
        first_end = int(-(-start_seconds // 60)) * 60 + 60
        final_end = int(end.timestamp()) // 60 * 60
        stamps = list(range(first_end, final_end + 1, 60))
        if len(stamps) < 2:
            raise ValueError("fixture requires at least two complete minutes")
        whole_units, remainder = divmod(total_bytes, 15)
        per_point, extra = divmod(whole_units, len(stamps) - 1)
        amounts = [(per_point + (index < extra)) * 15 for index in range(len(stamps) - 1)]
        amounts.append(remainder)
        for stamp, amount in zip(stamps, amounts):
            self.points[stamp * 1000] = {
                "timestamp": stamp * 1000,
                "Average": amount * 8 / 60,
                "instanceId": self.instance_id,
                "ip": self.public_ip,
            }


class TrafficControlTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="traffic-control-independent-")
        self.database = Path(self.directory.name) / "ledger.sqlite3"
        self.ledger = Ledger(self.database, initialize=True)
        self.cloud = FakeCloud()
        self.settings = {
            "instance_id": self.cloud.instance_id,
            "public_ip": self.cloud.public_ip,
            "region": "cn-beijing",
            "created_at": CREATED.isoformat().replace("+00:00", "Z"),
            "baseline_mbps": 100,
            "tiers": [[150, 5], [200, 1]],
            "enabled": True,
            "settle_seconds": 300,
        }
        self.config = Config.from_dict(self.settings)

    def tearDown(self):
        self.ledger.close()
        self.directory.cleanup()

    def reopen(self):
        self.ledger.close()
        self.ledger = Ledger(self.database)

    def check_once(self, now=OCTOBER_NOW, config=None, dry_run=False):
        report = run_once(config or self.config, self.ledger, self.cloud, now, dry_run=dry_run)
        self.assertIsInstance(report, dict)
        return report

    def attempt(self, now=OCTOBER_NOW, config=None):
        # An API failure may be surfaced as an exception or a diagnostic report.
        # Subsequent calls assert the durable recovery behavior independently.
        try:
            return self.check_once(now, config)
        except (OSError, RuntimeError):
            return None

    def seed_october(self, total):
        # A finite numeric bit/s Average cannot express every exact byte total.
        # Round only this synthetic fixture upward by at most 14 bytes to make
        # its integrated total exact. Config.cap tests the precise thresholds.
        total += (-total) % 15
        self.cloud.populate(CREATED, settled_end(OCTOBER_NOW), total)

    def prepare_november(self, total=0):
        # Complete the final settled-to-month-boundary interval of the old month.
        self.cloud.populate(settled_end(OCTOBER_NOW), NOVEMBER_START, 0)
        self.cloud.populate(NOVEMBER_START, settled_end(NOVEMBER_NOW), total)

    def test_first_creation_requires_explicit_initialization(self):
        missing = Path(self.directory.name) / "uninitialized.sqlite3"
        with self.assertRaises(Exception):
            unexpected = Ledger(missing)
            unexpected.close()

    def test_below_first_threshold_keeps_normal_bandwidth(self):
        self.seed_october(150 * GB - 15)
        report = self.check_once()
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["missing_minutes"], 0)
        self.assertLess(report["observed_gb"], 150)
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(self.cloud.bandwidth, 100)

    def test_exact_first_threshold_lowers_to_five(self):
        self.seed_october(150 * GB)
        report = self.check_once()
        self.assertTrue(report["coverage_complete"])
        self.assertAlmostEqual(report["observed_gb"], 150, places=7)
        self.assertEqual(report["target_mbps"], 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])
        self.assertEqual(self.cloud.bandwidth, 5)

    def test_below_second_threshold_uses_first_tier(self):
        self.seed_october(200 * GB - 5)
        report = self.check_once()
        self.assertLess(report["observed_gb"], 200)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])

    def test_exact_second_threshold_skips_first_tier(self):
        self.assertEqual(self.config.cap(200 * GB - 1), 5)
        self.assertEqual(self.config.cap(200 * GB), 1)
        self.seed_october(200 * GB)
        report = self.check_once()
        self.assertAlmostEqual(report["observed_gb"], 200, places=7)
        self.assertEqual(report["target_mbps"], 1)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])

    def test_repeated_and_duplicate_points_are_not_double_counted(self):
        self.seed_october(150 * GB)
        self.cloud.duplicate_points = True
        first = self.check_once()
        self.reopen()
        second = self.check_once()
        self.assertAlmostEqual(first["observed_gb"], 150, places=7)
        self.assertAlmostEqual(second["observed_gb"], 150, places=7)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])

    def test_missing_point_is_visible_and_late_data_closes_gap(self):
        self.seed_october(200 * GB)
        hidden = sorted(self.cloud.points)[len(self.cloud.points) // 2]
        self.cloud.hidden_points.add(hidden)
        incomplete = self.check_once()
        self.assertFalse(incomplete["coverage_complete"])
        self.assertEqual(incomplete["missing_minutes"], 1)
        self.assertLess(incomplete["observed_gb"], 200)
        self.cloud.hidden_points.clear()
        self.reopen()
        complete = self.check_once()
        self.assertTrue(complete["coverage_complete"])
        self.assertEqual(complete["missing_minutes"], 0)
        self.assertAlmostEqual(complete["observed_gb"], 200, places=7)
        self.assertEqual(self.cloud.bandwidth, 1)

    def test_empty_metrics_are_not_complete_zero_traffic(self):
        report = self.check_once()
        self.assertFalse(report["coverage_complete"])
        self.assertGreater(report["missing_minutes"], 0)
        self.assertEqual(self.cloud.calls, [])

    def test_raising_threshold_does_not_raise_existing_limit(self):
        self.seed_october(200 * GB)
        self.check_once()
        revised = dict(self.settings, tiers=[[150, 5], [250, 1]])
        report = self.check_once(config=Config.from_dict(revised))
        self.assertEqual(self.cloud.bandwidth, 1)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])
        self.assertLessEqual(report["target_mbps"], 1)

    def test_new_month_restores_confirmed_baseline(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        self.reopen()
        report = self.check_once(NOVEMBER_NOW)
        self.assertEqual(report["month"], "2026-11")
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["observed_gb"], 0)
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 100])

    def test_new_month_already_in_first_tier_never_writes_one_hundred(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november(160 * GB)
        report = self.check_once(NOVEMBER_NOW)
        self.assertEqual(report["target_mbps"], 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 5])

    def test_month_boundary_point_belongs_to_previous_month(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        boundary = self.cloud.points[timestamp_ms(NOVEMBER_START)]
        boundary["Average"] = 8_000_000  # Old month receives 60 MB, new receives zero.
        report = self.check_once(NOVEMBER_NOW)
        self.assertEqual(report["month"], "2026-11")
        self.assertEqual(report["observed_gb"], 0)
        self.assertEqual(self.cloud.bandwidth, 100)

    def test_incomplete_new_month_blocks_restore_until_backfilled(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        missing = timestamp_ms(NOVEMBER_START + dt.timedelta(minutes=1))
        self.cloud.hidden_points.add(missing)
        report = self.check_once(NOVEMBER_NOW)
        self.assertFalse(report["coverage_complete"])
        self.assertEqual(report["missing_minutes"], 1)
        self.assertEqual(self.cloud.bandwidth, 1)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])
        self.cloud.hidden_points.clear()
        self.reopen()
        report = self.check_once(NOVEMBER_NOW)
        self.assertTrue(report["coverage_complete"])
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 100])

    def test_disabled_across_month_boundary_never_writes(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        disabled = Config.from_dict(dict(self.settings, enabled=False))
        self.check_once(NOVEMBER_NOW, config=disabled)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])
        self.reopen()
        report = self.check_once(NOVEMBER_NOW)
        self.assertTrue(report["coverage_complete"])
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 100])

    def test_unregistered_manual_change_blocks_monthly_restore(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.cloud.bandwidth = 50
        self.prepare_november()
        report = self.check_once(NOVEMBER_NOW)
        self.assertEqual(self.cloud.bandwidth, 50)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])
        self.assertEqual(report["status"], "conflict")

    def test_pending_write_is_confirmed_only_after_real_effect(self):
        self.seed_october(150 * GB)
        self.cloud.write_mode = "delayed"
        self.attempt()
        self.assertEqual(self.cloud.bandwidth, 100)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])
        self.cloud.bandwidth = 5
        self.reopen()
        report = self.check_once()
        self.assertEqual(report["current_mbps"], 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])
        self.assertNotIn("manual", json.dumps(report).lower())

    def test_pending_failed_before_effect_retries_same_logical_token(self):
        self.seed_october(150 * GB)
        self.cloud.write_mode = "fail_before_effect"
        self.attempt()
        self.assertEqual(self.cloud.bandwidth, 100)
        self.assertTrue(self.cloud.calls)
        first_token = self.cloud.calls[0][1]
        self.cloud.write_mode = "immediate"
        self.reopen()
        self.check_once()
        self.assertEqual(self.cloud.bandwidth, 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [5, 5])
        self.assertEqual(self.cloud.calls[-1][1], first_token)
        self.assertTrue(first_token)

    def test_response_lost_after_effect_does_not_repeat_or_mark_manual(self):
        self.seed_october(150 * GB)
        self.cloud.write_mode = "fail_after_effect"
        self.attempt()
        self.assertEqual(self.cloud.bandwidth, 5)
        self.reopen()
        report = self.check_once()
        self.assertEqual([call[0] for call in self.cloud.calls], [5])
        self.assertNotIn("manual", json.dumps(report).lower())

    def test_unavailable_readback_preserves_pending_until_confirmed(self):
        self.seed_october(150 * GB)
        self.cloud.write_mode = "readback_error"
        self.attempt()
        self.assertEqual(self.cloud.bandwidth, 5)
        self.cloud.read_error = None
        self.reopen()
        report = self.check_once()
        self.assertEqual(report["current_mbps"], 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])
        self.assertNotEqual(report["status"], "conflict")

    def test_failed_monthly_restore_remains_pending_and_retries(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        self.cloud.write_mode = "fail_before_effect"
        self.attempt(NOVEMBER_NOW)
        self.assertEqual(self.cloud.bandwidth, 1)
        self.cloud.write_mode = "immediate"
        self.reopen()
        self.check_once(NOVEMBER_NOW)
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 100, 100])
        self.assertEqual(self.cloud.calls[-1][1], self.cloud.calls[-2][1])

    def test_dry_run_collects_without_modifying_cloud(self):
        self.seed_october(200 * GB)
        report = self.check_once(dry_run=True)
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["target_mbps"], 1)
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(self.cloud.bandwidth, 100)
        self.reopen()
        self.check_once()
        self.assertEqual([call[0] for call in self.cloud.calls], [1])

    def test_wrong_instance_identity_cannot_change_bandwidth(self):
        self.seed_october(200 * GB)
        self.cloud.description_changes["InstanceId"] = "i-unrelated"
        try:
            report = self.check_once()
        except (ValueError, RuntimeError):
            report = None
        self.assertEqual(self.cloud.calls, [])
        if report is not None:
            self.assertNotEqual(report.get("status"), "ok")

    def test_later_configured_creation_time_cannot_skip_actual_history(self):
        self.seed_october(200 * GB)
        later = (CREATED + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        invalid = Config.from_dict(dict(self.settings, created_at=later))
        with self.assertRaises(RuntimeError):
            self.check_once(config=invalid)
        self.assertEqual(self.cloud.metric_queries, [])
        self.assertEqual(self.cloud.calls, [])

    def rpc_only_cloud(self):
        # Bypass __init__ deliberately: these tests must never contact IMDS.
        cloud = AlibabaCloud.__new__(AlibabaCloud)
        cloud.c = self.config
        cloud.config_path = Path(self.directory.name) / "live-config.json"
        cloud.config_path.write_text(json.dumps(self.settings))
        calls = []

        def fake_rpc(*args, **kwargs):
            calls.append((args, kwargs))
            return {"RequestId": "synthetic-request"}

        cloud.rpc = fake_rpc
        return cloud, calls

    def test_production_config_pause_blocks_rpc_before_any_write(self):
        cloud, calls = self.rpc_only_cloud()
        cloud.config_path.write_text(json.dumps(dict(self.settings, enabled=False)))
        with self.assertRaises(RuntimeError):
            cloud.set_bandwidth(5, "synthetic-idempotency-token")
        self.assertEqual(calls, [])

    def test_production_stale_config_blocks_rpc_matching_config_allows_it(self):
        cloud, calls = self.rpc_only_cloud()
        cloud.config_path.write_text(json.dumps(dict(self.settings, tiers=[[180, 5], [200, 1]])))
        with self.assertRaises(RuntimeError):
            cloud.set_bandwidth(5, "synthetic-idempotency-token")
        self.assertEqual(calls, [])
        cloud.config_path.write_text(json.dumps(self.settings))
        cloud.set_bandwidth(5, "synthetic-idempotency-token")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], "ModifyInstanceNetworkSpec")
        self.assertNotIn("NetworkChargeType", calls[0][1])
        self.assertNotIn("StartTime", calls[0][1])

    def test_midrun_month_rollover_blocks_old_month_write(self):
        self.seed_october(200 * GB)
        self.cloud.now = lambda: NOVEMBER_START
        with self.assertRaises(RuntimeError):
            self.check_once()
        self.assertEqual(self.cloud.bandwidth, 100)
        self.assertEqual(self.cloud.calls, [])

    def test_late_revision_replaces_samples_without_reopening_speed(self):
        self.seed_october(150 * GB)
        self.check_once()
        self.seed_october(100 * GB)
        report = self.check_once()
        self.assertAlmostEqual(report["observed_gb"], 100, places=7)
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(self.cloud.bandwidth, 5)
        self.assertEqual([call[0] for call in self.cloud.calls], [5])

    def test_new_month_over_second_threshold_never_writes_high_speed(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november(205 * GB)
        report = self.check_once(NOVEMBER_NOW)
        self.assertEqual(report["target_mbps"], 1)
        self.assertEqual(self.cloud.bandwidth, 1)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])

    def test_cloud_metric_failure_cannot_restore_high_speed(self):
        self.seed_october(200 * GB)
        self.check_once()
        self.prepare_november()
        self.cloud.metric_error = OSError("synthetic CloudMonitor failure")
        self.attempt(NOVEMBER_NOW)
        self.assertEqual(self.cloud.bandwidth, 1)
        self.assertEqual([call[0] for call in self.cloud.calls], [1])
        self.cloud.metric_error = None
        self.reopen()
        self.check_once(NOVEMBER_NOW)
        self.assertEqual([call[0] for call in self.cloud.calls], [1, 100])

    def test_eip_resource_change_is_rejected(self):
        self.seed_october(200 * GB)
        self.cloud.description_changes["EipAddress"] = {
            "IpAddress": self.cloud.public_ip,
            "AllocationId": "eip-unrelated",
        }
        with self.assertRaises(RuntimeError):
            self.check_once()
        self.assertEqual(self.cloud.calls, [])

    def test_lock_refuses_overlapping_execution_and_releases_on_exit(self):
        with process_lock(self.database):
            with self.assertRaises(RuntimeError):
                with process_lock(self.database):
                    self.fail("second execution unexpectedly acquired the lock")
        with process_lock(self.database):
            pass


if __name__ == "__main__":
    unittest.main()
