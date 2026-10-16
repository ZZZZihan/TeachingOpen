"""Offline regressions for complete, attributable PR evidence reuse.

The GitHub payloads below are synthetic. These tests do not call GitHub, run a
workflow, or turn partial PR coverage into proof of a full successful suite.
"""

from copy import deepcopy
from contextlib import chdir
from datetime import datetime, timedelta, timezone
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings
import zipfile

import check_required_jobs as required
import ci_reuse as reuse


HEAVY_JOBS = ("frontend", "tools", "backend")
JOB_NAMES = {
    "frontend": "Frontend tests and build",
    "tools": "Backup and migration tools",
    "backend": "Backend and MySQL registration",
    "required": "CI required",
}
RUNTIMES = {
    "frontend": {"node": "v26.7.0", "npm": "11.19.0"},
    "tools": {"python": "3.12.15", "java": "1.8.0_504-b01"},
    "backend": {
        "python": "3.12.15", "java": "1.8.0_504-b01",
        "mysql": "sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b",
        "redis": "sha256:46f15cf64fdef63e483dcda99e74e3d51c017b1175547b6bb874152ee2391aad",
    },
}


def timestamp(value):
    return value.isoformat().replace("+00:00", "Z")


def valid_fixture():
    """One successful PR actually tested a different SHA with the target tree."""
    now = datetime(2026, 10, 16, 4, 30, tzinfo=timezone.utc)
    completed = now - timedelta(minutes=30)
    repo = {"id": 1001, "full_name": "ZZZZihan/TeachingOpen"}
    target = {
        "event": "push", "ref": "refs/heads/main", "sha": "a" * 40,
        "tree": "c" * 40, "repository": repo["full_name"],
        "repository_id": repo["id"], "workflow_id": 2001,
        "workflow_blob": "f" * 40, "image_os": "ubuntu22",
        "image_version": "20261012.1.0",
    }
    pr = {
        "number": 148, "state": "closed", "merged": True,
        "merge_commit_sha": target["sha"],
        "base": {"ref": "main", "sha": "d" * 40, "repo": deepcopy(repo)},
        "head": {"sha": "e" * 40, "repo": deepcopy(repo)},
    }
    run = {
        "id": 777, "run_attempt": 1, "event": "pull_request",
        "status": "completed", "conclusion": "success", "workflow_id": 2001,
        "path": ".github/workflows/ci.yml", "head_sha": pr["head"]["sha"],
        "repository": deepcopy(repo), "head_repository": deepcopy(repo),
        "created_at": timestamp(completed - timedelta(hours=1)),
        "updated_at": timestamp(completed),
    }
    jobs = [{
        "id": 800 + index, "name": display_name, "status": "completed",
        "conclusion": "success", "run_id": run["id"], "run_attempt": 1,
        "started_at": timestamp(completed - timedelta(minutes=45)),
        "completed_at": timestamp(completed - timedelta(seconds=30)),
    } for index, display_name in enumerate(JOB_NAMES.values())]
    receipts = {job: {
        "schema": 1, "mode": "fresh", "job": job,
        "repository": repo["full_name"], "repository_id": repo["id"],
        "run_id": run["id"], "run_attempt": 1, "event": "pull_request",
        "pr_number": pr["number"], "head_sha": pr["head"]["sha"],
        "base_sha": pr["base"]["sha"], "checkout_sha": "b" * 40,
        "tree": target["tree"], "parents": [pr["base"]["sha"], pr["head"]["sha"]],
        "workflow_blob": target["workflow_blob"], "image_os": target["image_os"],
        "image_version": target["image_version"],
        "runtimes": deepcopy(RUNTIMES[job]),
        "recorded_at": timestamp(completed - timedelta(minutes=1)),
    } for job in HEAVY_JOBS}
    receipts["backend"]["apt_packages"] = "6" * 64
    return target, pr, run, jobs, receipts, now


class EvidenceValidationTests(unittest.TestCase):
    def setUp(self):
        (self.target, self.pr, self.run, self.jobs,
         self.receipts, self.now) = valid_fixture()

    def validate(self, now=None):
        return reuse.validate_evidence(
            self.target, self.pr, self.run, self.jobs, self.receipts,
            self.now if now is None else now,
        )

    def reject(self):
        with self.assertRaises(ValueError):
            self.validate()

    def test_complete_evidence_reuses_same_tree_without_relabelling_tested_sha(self):
        proof = self.validate()
        self.assertEqual(proof["schema"], 1)
        self.assertEqual(proof["mode"], "reused")
        self.assertEqual(proof["target_sha"], self.target["sha"])
        self.assertEqual(proof["source_sha"], "b" * 40)
        self.assertNotEqual(proof["source_sha"], proof["target_sha"])
        self.assertEqual(proof["tree"], self.target["tree"])
        self.assertEqual(proof["source_run_id"], self.run["id"])
        self.assertEqual(proof["source_run_attempt"], 1)
        self.assertEqual(proof["pr_number"], self.pr["number"])
        self.assertEqual(proof["source_job_ids"], {
            job: 800 + index for index, job in enumerate(JOB_NAMES)
        })
        self.assertTrue(proof["source_url"].startswith(
            "https://github.com/ZZZZihan/TeachingOpen/actions/runs/777"))
        self.assertTrue(all(receipt["checkout_sha"] == "b" * 40
                            for receipt in self.receipts.values()))

    def test_same_commit_is_also_valid_but_original_inputs_are_not_rewritten(self):
        for receipt in self.receipts.values():
            receipt["checkout_sha"] = self.target["sha"]
        before = deepcopy((self.target, self.pr, self.run, self.jobs, self.receipts))
        self.assertEqual(self.validate()["source_sha"], self.target["sha"])
        self.assertEqual((self.target, self.pr, self.run, self.jobs, self.receipts), before)

    def test_pr_and_non_main_push_contexts_cannot_reuse(self):
        for field, value in (
            ("event", "pull_request"), ("event", "pull_request_target"),
            ("event", "workflow_dispatch"), ("event", ""),
            ("ref", "refs/heads/topic"), ("ref", "refs/pull/148/merge"),
        ):
            with self.subTest(field=field, value=value):
                original = self.target[field]
                self.target[field] = value
                self.reject()
                self.target[field] = original

    def test_target_identifiers_and_environment_must_be_present_and_well_formed(self):
        for field in tuple(self.target):
            with self.subTest(missing=field):
                original = self.target.pop(field)
                self.reject()
                self.target[field] = original
        for field in ("sha", "tree", "workflow_blob"):
            for value in ("a" * 39, "g" * 40, "A" * 40, "HEAD", "", None, True):
                with self.subTest(field=field, value=value):
                    original = self.target[field]
                    self.target[field] = value
                    self.reject()
                    self.target[field] = original
        for field in ("repository_id", "workflow_id"):
            for value in (None, True, "1001", 0, -1):
                with self.subTest(field=field, value=value):
                    original = self.target[field]
                    self.target[field] = value
                    self.reject()
                    self.target[field] = original

    def test_even_consistent_source_receipts_cannot_authorize_a_different_target_tree(self):
        for receipt in self.receipts.values():
            receipt["tree"] = "2" * 40
        self.reject()

    def test_pr_head_agreement_is_not_proof_of_the_actual_tested_merge_tree(self):
        for receipt in self.receipts.values():
            receipt["checkout_sha"] = self.pr["head"]["sha"]
            receipt["tree"] = "1" * 40
        self.reject()

    def test_three_actual_checkout_shas_trees_and_parent_order_must_agree(self):
        for job in HEAVY_JOBS:
            for field, value in (
                ("checkout_sha", "1" * 40), ("tree", "1" * 40),
                ("parents", [self.pr["head"]["sha"], self.pr["base"]["sha"]]),
                ("parents", [self.pr["base"]["sha"]]),
                ("parents", [self.pr["base"]["sha"], self.pr["head"]["sha"], "1" * 40]),
            ):
                with self.subTest(job=job, field=field, value=value):
                    original = self.receipts[job][field]
                    self.receipts[job][field] = value
                    self.reject()
                    self.receipts[job][field] = original

    def test_live_pr_base_can_advance_without_relabelling_the_tested_base(self):
        tested_base = self.receipts["frontend"]["base_sha"]
        self.pr["base"]["sha"] = "1" * 40
        self.assertEqual(self.validate()["source_sha"], "b" * 40)
        self.assertTrue(all(receipt["parents"][0] == tested_base
                            for receipt in self.receipts.values()))

    def test_receipt_base_must_be_consistent_and_equal_the_recorded_parent(self):
        self.receipts["frontend"]["base_sha"] = "1" * 40
        self.reject()
        self.receipts["frontend"]["parents"][0] = "1" * 40
        self.reject()

    def test_workflow_blob_os_and_actual_runner_image_version_must_match(self):
        for job in HEAVY_JOBS:
            for field, value in (
                ("workflow_blob", "1" * 40), ("image_os", "ubuntu24"),
                ("image_version", "20261013.1.0"), ("image_version", ""),
            ):
                with self.subTest(job=job, field=field, value=value):
                    original = self.receipts[job][field]
                    self.receipts[job][field] = value
                    self.reject()
                    self.receipts[job][field] = original
        self.target["image_version"] = "newer-image-under-the-same-ubuntu-label"
        self.reject()

    def test_mixed_runner_images_report_the_mismatched_field_without_relaxing_checks(self):
        self.receipts["tools"]["image_version"] = "20261004.315.1"
        with self.assertRaisesRegex(ValueError, r"Receipt mismatch: tools \(fields: image_version\)"):
            self.validate()

    def test_diagnostics_report_all_different_expected_fields_without_echoing_values(self):
        receipt = self.receipts["tools"]
        receipt["image_version"] = "untrusted-secret-value\n::warning::injected"
        receipt["image_os"] = "ubuntu24"
        receipt["runtimes"] = {}
        receipt.pop("workflow_blob")
        with self.assertRaises(ValueError) as caught:
            self.validate()
        self.assertEqual(str(caught.exception),
                         "Receipt mismatch: tools (fields: workflow_blob, image_os, image_version, runtimes)")

    def test_actual_runtime_versions_and_service_image_digests_must_match(self):
        for job in HEAVY_JOBS:
            original = deepcopy(self.receipts[job]["runtimes"])
            for runtime in original:
                with self.subTest(job=job, runtime=runtime, state="changed"):
                    self.receipts[job]["runtimes"] = {**original, runtime: "different-version-or-digest"}
                    self.reject()
                with self.subTest(job=job, runtime=runtime, state="missing"):
                    self.receipts[job]["runtimes"] = {
                        key: value for key, value in original.items() if key != runtime
                    }
                    self.reject()
            self.receipts[job]["runtimes"] = original

    def test_only_the_merged_same_repository_pr_for_the_target_push_is_eligible(self):
        for field, value in (
            ("number", True), ("state", "open"), ("merged", False),
            ("merged", "true"), ("merge_commit_sha", "1" * 40),
        ):
            with self.subTest(field=field, value=value):
                original = self.pr[field]
                self.pr[field] = value
                self.reject()
                self.pr[field] = original
        for side in ("base", "head"):
            for field, value in (("id", 1002), ("full_name", "fork/TeachingOpen")):
                with self.subTest(side=side, field=field):
                    original = self.pr[side]["repo"][field]
                    self.pr[side]["repo"][field] = value
                    self.reject()
                    self.pr[side]["repo"][field] = original
        self.pr["base"]["ref"] = "release"
        self.reject()

    def test_source_workflow_event_run_and_repositories_are_bound_to_the_pr(self):
        for field, value in (
            ("id", True), ("id", 0), ("event", "push"),
            ("event", "pull_request_target"), ("workflow_id", 2002),
            ("path", ".github/workflows/same-name-other-workflow.yml"),
            ("head_sha", "1" * 40), ("status", "in_progress"),
            ("conclusion", "failure"), ("conclusion", "cancelled"),
            ("conclusion", "skipped"), ("conclusion", None),
        ):
            with self.subTest(field=field, value=value):
                original = self.run[field]
                self.run[field] = value
                self.reject()
                self.run[field] = original
        for side in ("repository", "head_repository"):
            for field, value in (("id", 1002), ("full_name", "fork/TeachingOpen")):
                with self.subTest(side=side, field=field):
                    original = self.run[side][field]
                    self.run[side][field] = value
                    self.reject()
                    self.run[side][field] = original

    def test_each_heavy_job_and_required_must_actually_complete_successfully(self):
        for index, job in enumerate(self.jobs):
            for field, value in (
                ("status", "queued"), ("status", "in_progress"),
                ("conclusion", "skipped"), ("conclusion", "failure"),
                ("conclusion", "cancelled"), ("conclusion", "neutral"),
                ("conclusion", None), ("run_id", 778), ("run_attempt", 2),
                ("id", True),
            ):
                with self.subTest(job=job["name"], field=field, value=value):
                    original = self.jobs[index][field]
                    self.jobs[index][field] = value
                    self.reject()
                    self.jobs[index][field] = original

    def test_missing_duplicate_or_misnamed_jobs_cannot_be_combined_into_coverage(self):
        original = deepcopy(self.jobs)
        for index in range(len(original)):
            with self.subTest(missing=index):
                self.jobs = [job for i, job in enumerate(original) if i != index]
                self.reject()
            with self.subTest(duplicate=index):
                self.jobs = original + [deepcopy(original[index])]
                self.reject()
            with self.subTest(renamed=index):
                self.jobs = deepcopy(original)
                self.jobs[index]["name"] += " (legacy)"
                self.reject()
        self.jobs = original

    def test_selective_pr_green_status_is_not_a_full_suite(self):
        for job in self.jobs:
            if job["name"] != JOB_NAMES["required"]:
                job["conclusion"] = "skipped"
        self.reject()

    def test_nonheavy_planning_jobs_may_be_skipped_without_invalidating_full_checks(self):
        self.jobs.extend([
            {"id": 900, "name": "Select affected PR jobs", "status": "completed",
             "conclusion": "success", "run_id": 777, "run_attempt": 1},
            {"id": 901, "name": "Verify identical-tree PR evidence", "status": "completed",
             "conclusion": "skipped", "run_id": 777, "run_attempt": 1},
        ])
        self.assertEqual(self.validate()["source_run_id"], 777)

    def test_reruns_and_cross_attempt_receipts_are_conservatively_rejected(self):
        self.run["run_attempt"] = 2
        for job in self.jobs:
            job["run_attempt"] = 2
        for receipt in self.receipts.values():
            receipt["run_attempt"] = 2
        self.reject()
        self.setUp()
        self.receipts["backend"]["run_attempt"] = 2
        self.reject()

    def test_all_receipts_are_required_fresh_and_bound_to_the_exact_source(self):
        for job in HEAVY_JOBS:
            original = self.receipts.pop(job)
            with self.subTest(missing=job):
                self.reject()
            self.receipts[job] = original
        changes = {
            "schema": 2, "mode": "reused", "job": "required",
            "repository": "fork/TeachingOpen", "repository_id": 1002,
            "run_id": 778, "run_attempt": 2, "event": "push",
            "pr_number": 149, "head_sha": "1" * 40, "base_sha": "2" * 40,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                original = self.receipts["frontend"][field]
                self.receipts["frontend"][field] = value
                self.reject()
                self.receipts["frontend"][field] = original
        for field in tuple(self.receipts["frontend"]):
            with self.subTest(missing_field=field):
                original = self.receipts["frontend"].pop(field)
                self.reject()
                self.receipts["frontend"][field] = original

    def test_six_hour_ttl_boundary_is_explicit_and_stale_evidence_is_rejected(self):
        created = datetime.fromisoformat(self.run["created_at"].replace("Z", "+00:00"))
        self.assertEqual(self.validate(now=created + timedelta(hours=6))["mode"], "reused")
        with self.assertRaises(ValueError):
            self.validate(now=created + timedelta(hours=6, seconds=1))

    def test_previous_shanghai_date_expires_even_when_less_than_six_hours_old(self):
        now = datetime(2026, 10, 16, 16, 5, tzinfo=timezone.utc)  # 00:05 Oct 17 CST
        completed = now - timedelta(minutes=10)  # 23:55 Oct 16 CST
        self.run["updated_at"] = timestamp(completed)
        self.run["created_at"] = timestamp(completed - timedelta(hours=1))
        for job in self.jobs:
            job["started_at"] = timestamp(completed - timedelta(minutes=45))
            job["completed_at"] = timestamp(completed - timedelta(seconds=30))
        for receipt in self.receipts.values():
            receipt["recorded_at"] = timestamp(completed - timedelta(minutes=1))
        with self.assertRaises(ValueError):
            self.validate(now=now)

    def test_future_missing_invalid_and_naive_times_are_not_fresh_evidence(self):
        for field in ("created_at", "updated_at"):
            for value in (None, "", "yesterday", "2026-10-16T04:00:00",
                          timestamp(self.now + timedelta(seconds=1))):
                with self.subTest(field=field, value=value):
                    original = self.run[field]
                    self.run[field] = value
                    self.reject()
                    self.run[field] = original
        for job in self.jobs:
            for field in ("started_at", "completed_at"):
                original = job[field]
                job[field] = timestamp(self.now + timedelta(seconds=1))
                with self.subTest(job=job["name"], field=field):
                    self.reject()
                job[field] = original
        self.receipts["tools"]["recorded_at"] = timestamp(self.now + timedelta(seconds=1))
        self.reject()
        self.setUp()
        with self.assertRaises(ValueError):
            self.validate(now=self.now.replace(tzinfo=None))

    def test_malformed_or_missing_api_objects_never_form_partial_evidence(self):
        for attribute in ("target", "pr", "run", "jobs", "receipts"):
            for value in (None, "", [], {}):
                with self.subTest(attribute=attribute, value=value):
                    original = getattr(self, attribute)
                    try:
                        setattr(self, attribute, value)
                        self.reject()
                    finally:
                        setattr(self, attribute, original)


def receipt_zip(members, *, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", compression=compression) as archive:
            for name, data in members:
                archive.writestr(name, data)
    return stream.getvalue()


class ReceiptArchiveTests(unittest.TestCase):
    def setUp(self):
        self.receipt = valid_fixture()[4]["frontend"]
        self.payload = json.dumps(self.receipt).encode("utf-8")

    def test_unique_bounded_receipt_json_is_read_without_extraction(self):
        self.assertEqual(reuse.read_receipt_zip(receipt_zip([
            ("receipt.json", self.payload),
        ])), self.receipt)

    def test_missing_duplicate_extra_and_path_members_are_rejected(self):
        for members in (
            [], [("other.json", self.payload)],
            [("receipt.json", self.payload), ("receipt.json", self.payload)],
            [("receipt.json", self.payload), ("notes.txt", b"extra")],
            [("../receipt.json", self.payload)], [("/receipt.json", self.payload)],
            [("folder/receipt.json", self.payload)], [("folder\\receipt.json", self.payload)],
        ):
            with self.subTest(names=[name for name, _ in members]):
                with self.assertRaises(ValueError):
                    reuse.read_receipt_zip(receipt_zip(members))

    def test_compressed_oversized_member_is_rejected_before_json_is_trusted(self):
        raw = b'{"padding":"' + b"x" * (64 * 1024) + b'"}'
        archive = receipt_zip([("receipt.json", raw)])
        self.assertLess(len(archive), 256 * 1024)
        with self.assertRaises(ValueError):
            reuse.read_receipt_zip(archive)

    def test_archive_size_limit_applies_even_to_a_bounded_unique_member(self):
        stream = io.BytesIO()
        info = zipfile.ZipInfo("receipt.json")
        # Valid empty extra fields plus a valid ZIP comment make the transport
        # exceed its bound while the sole uncompressed JSON remains 64 KiB.
        info.extra = b"\xfe\xca\x00\x00" * 16383
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.comment = b"x" * 65535
            archive.writestr(info, b"{}" + b" " * (64 * 1024 - 2))
        data = stream.getvalue()
        self.assertGreater(len(data), 256 * 1024)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(len(archive.read("receipt.json")), 64 * 1024)
        with self.assertRaises(ValueError):
            reuse.read_receipt_zip(data)

    def test_invalid_zip_json_utf8_and_duplicate_json_keys_are_rejected(self):
        for data in (b"not a zip", b"", receipt_zip([("receipt.json", b"{invalid")]),
                     receipt_zip([("receipt.json", b"\xff")])):
            with self.subTest(data=data[:20]):
                with self.assertRaises(ValueError):
                    reuse.read_receipt_zip(data)
        for raw in (b'null', b'[]', b'"receipt"', b'{"schema":1,"schema":1}',
                    b'{"outer":{"run_id":777,"run_id":777}}'):
            with self.subTest(json=raw):
                with self.assertRaises(ValueError):
                    reuse.read_receipt_zip(receipt_zip([("receipt.json", raw)]))


class SourceDiscoveryTests(unittest.TestCase):
    """Exercise discovery and provenance with bounded synthetic API responses."""

    def setUp(self):
        (self.target, self.pr, self.run, self.jobs,
         self.receipts, self.now) = valid_fixture()
        self.associated = [{
            "number": self.pr["number"], "merge_commit_sha": self.target["sha"],
            "merged_at": timestamp(self.now - timedelta(minutes=10)),
            "base": {"ref": "main"},
        }]
        self.runs = [deepcopy(self.run)]
        self.commit = {
            "sha": "b" * 40, "tree": {"sha": self.target["tree"]},
            "parents": [{"sha": self.pr[side]["sha"]} for side in ("base", "head")],
        }
        self.archives = {}
        self.artifacts = []
        for index, job in enumerate(HEAVY_JOBS):
            artifact_id = 950 + index
            data = receipt_zip([("receipt.json", json.dumps(self.receipts[job]).encode())])
            self.archives[artifact_id] = data
            self.artifacts.append({
                "id": artifact_id, "name": "ci-fresh-" + job + "-777-1",
                "expired": False, "size_in_bytes": len(data),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "workflow_run": {
                    "id": self.run["id"], "repository_id": self.target["repository_id"],
                    "head_repository_id": self.target["repository_id"],
                    "head_sha": self.pr["head"]["sha"],
                },
            })
        self.api = Mock()
        self.api.bounded_list.side_effect = self.bounded_list
        self.api.request.side_effect = self.request
        self.api.download.side_effect = self.download
        self.run_reads = 0

    def bounded_list(self, path, field=None):
        if path.endswith("/pulls"):
            return deepcopy(self.associated)
        return deepcopy({
            "workflow_runs": self.runs, "jobs": self.jobs, "artifacts": self.artifacts,
        }[field])

    def request(self, path):
        if "/pulls/" in path:
            return deepcopy(self.pr)
        if "/git/commits/" in path:
            return deepcopy(self.commit)
        if "/actions/runs/" in path:
            self.run_reads += 1
            requested = int(path.rsplit("/", 1)[1])
            return deepcopy(next(run for run in self.runs if run["id"] == requested))
        raise AssertionError("Unexpected synthetic API route: " + path)

    def download(self, path):
        return self.archives[int(path.split("/")[-2])]

    def resolve(self, source_run_id=None, packages=None):
        fixed_now = self.now

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(fixed_now.timestamp(), tz or timezone.utc)

        with patch.object(reuse, "datetime", FrozenDateTime), \
                patch.object(reuse.subprocess, "run", return_value=Mock(returncode=0)), \
                patch.object(reuse, "installed_packages_digest",
                             return_value="6" * 64 if packages is None else packages):
            return reuse.resolve(self.api, self.target, source_run_id=source_run_id)

    def test_discovery_downloads_unique_provenance_bound_receipts_and_checks_real_git(self):
        proof = self.resolve()
        self.assertEqual(proof["source_sha"], self.commit["sha"])
        self.assertEqual(proof["target_sha"], self.target["sha"])
        self.assertEqual(self.api.download.call_count, 3)
        self.assertTrue(any("/git/commits/" in call.args[0]
                            for call in self.api.request.call_args_list))
        self.assertGreaterEqual(self.run_reads, 2)

    def test_source_run_is_bound_again_when_required_rechecks_the_selected_run(self):
        with self.assertRaises(ValueError):
            self.resolve(source_run_id=778)

    def test_latest_failed_incomplete_or_rerun_source_cannot_fall_back_to_older_green(self):
        for updates in (
            {"status": "completed", "conclusion": "failure"},
            {"status": "in_progress", "conclusion": None},
            {"run_attempt": 2},
        ):
            with self.subTest(updates=updates):
                latest = {**self.run, **updates, "id": 778,
                          "created_at": timestamp(self.now - timedelta(minutes=50))}
                self.runs = [deepcopy(self.run), latest]
                with self.assertRaises(ValueError):
                    self.resolve()

    def test_an_unassociated_or_ambiguous_pr_does_not_get_same_tree_reuse(self):
        original = deepcopy(self.associated)
        for candidates in ([], original + original,
                           [{**original[0], "merge_commit_sha": "1" * 40}]):
            with self.subTest(candidates=candidates):
                self.associated = candidates
                with self.assertRaises(ValueError):
                    self.resolve()

    def test_missing_duplicate_expired_or_forged_artifacts_are_rejected(self):
        original = deepcopy(self.artifacts)
        for artifacts in (original[1:], original + [deepcopy(original[0])]):
            with self.subTest(count=len(artifacts)):
                self.artifacts = artifacts
                with self.assertRaises(ValueError):
                    self.resolve()
        self.artifacts = deepcopy(original)
        for field, value in (
            ("expired", True), ("size_in_bytes", 0),
            ("size_in_bytes", 256 * 1024 + 1), ("digest", "sha256:" + "0" * 64),
        ):
            with self.subTest(field=field, value=value):
                saved = self.artifacts[0][field]
                self.artifacts[0][field] = value
                with self.assertRaises(ValueError):
                    self.resolve()
                self.artifacts[0][field] = saved
        for field, value in (
            ("id", 778), ("repository_id", 1002),
            ("head_repository_id", 1002), ("head_sha", "1" * 40),
        ):
            with self.subTest(origin_field=field):
                saved = self.artifacts[0]["workflow_run"][field]
                self.artifacts[0]["workflow_run"][field] = value
                with self.assertRaises(ValueError):
                    self.resolve()
                self.artifacts[0]["workflow_run"][field] = saved

    def test_actual_source_commit_must_confirm_receipt_sha_tree_and_parents(self):
        for field, value in (
            ("sha", "1" * 40), ("tree", {"sha": "1" * 40}),
            ("parents", list(reversed(self.commit["parents"]))),
            ("parents", []),
        ):
            with self.subTest(field=field):
                original = self.commit[field]
                self.commit[field] = value
                with self.assertRaises(ValueError):
                    self.resolve()
                self.commit[field] = original

    def test_source_changed_during_download_is_not_silently_accepted(self):
        original = self.request

        def changed_request(path):
            result = original(path)
            if "/actions/runs/" in path and self.run_reads > 1:
                result["run_attempt"] = 2
                result["status"] = "in_progress"
                result["conclusion"] = None
            return result

        self.api.request.side_effect = changed_request
        with self.assertRaises(ValueError):
            self.resolve()

    def test_new_run_appearing_during_verification_invalidates_the_selected_source(self):
        original = self.bounded_list
        lists = 0

        def changed_list(path, field=None):
            nonlocal lists
            if field == "workflow_runs":
                lists += 1
                if lists > 1:
                    return self.runs + [{**self.run, "id": 778,
                                         "created_at": timestamp(self.now - timedelta(minutes=45))}]
            return original(path, field)

        self.api.bounded_list.side_effect = changed_list
        with self.assertRaises(ValueError):
            self.resolve()

    def test_resolved_system_packages_must_match_the_original_backend_manifest(self):
        with self.assertRaises(ValueError):
            self.resolve(packages="7" * 64)


class DecisionNormalizationTests(unittest.TestCase):
    def test_only_successful_exact_output_and_canonical_run_id_enable_reuse(self):
        for source in ("1", "777", "9876543210123456789"):
            with self.subTest(source=source):
                self.assertEqual(reuse.normalize_decision({
                    "outcome": "success", "outputs": {"reuse": "true", "source_run_id": source},
                }), {"reuse": "true", "source_run_id": source})

    def test_malformed_case_folded_partial_or_failed_decisions_always_run_full_suite(self):
        outputs = {"reuse": "true", "source_run_id": "777"}
        cases = [None, [], "true", {}, {"outputs": outputs},
                 {"outcome": "success"}, {"outcome": "success", "outputs": []}]
        for outcome in (None, "failure", "cancelled", "skipped", "Success", True):
            cases.append({"outcome": outcome, "outputs": outputs})
        for flag in (None, "TRUE", "True", "true ", "false", True, 1):
            cases.append({"outcome": "success", "outputs": {**outputs, "reuse": flag}})
        for source in (None, "", "0", "0777", "-1", "+777", "777 ", "7.0", "7\nreuse=true", 777, True):
            cases.append({"outcome": "success", "outputs": {**outputs, "source_run_id": source}})
        for missing in outputs:
            cases.append({"outcome": "success", "outputs": {
                key: value for key, value in outputs.items() if key != missing
            }})
        for step in cases:
            with self.subTest(step=step):
                self.assertEqual(reuse.normalize_decision(step), {"reuse": "false", "source_run_id": ""})

    def test_normalize_cli_writes_only_the_same_safe_outputs_and_fails_if_unwritable(self):
        cases = (
            (json.dumps({"outcome": "success", "outputs": {
                "reuse": "true", "source_run_id": "777",
            }}), {"reuse": "true", "source_run_id": "777"}),
            (json.dumps({"outcome": "success", "outputs": {
                "reuse": "TRUE", "source_run_id": "777",
            }}), {"reuse": "false", "source_run_id": ""}),
            ("{invalid", {"reuse": "false", "source_run_id": ""}),
            ("null", {"reuse": "false", "source_run_id": ""}),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "github-output"
                with patch.object(sys, "argv", ["ci_reuse.py", "--normalize"]), \
                        patch.dict(os.environ, {"CI_REUSE_STEP": raw, "GITHUB_OUTPUT": str(output)}):
                    self.assertEqual(reuse.main(), 0)
                self.assertEqual(dict(line.split("=", 1) for line in output.read_text().splitlines()), expected)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sys, "argv", ["ci_reuse.py", "--normalize"]), \
                patch.dict(os.environ, {"CI_REUSE_STEP": "{}", "GITHUB_OUTPUT": directory}):
            with self.assertRaises(OSError):
                reuse.main()


class OriginalReceiptGitTests(unittest.TestCase):
    """Use real Git identities while keeping installed-runtime checks synthetic."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="teachingopen-ci-receipt-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.environment = {
            key: value for key, value in os.environ.items()
            if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
        }
        self.environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Offline CI receipt regression")
        self.git("config", "user.email", "ci-receipt@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write(".github/workflows/ci.yml", "name: Synthetic receipt fixture\n")
        self.write("web/base.txt", "common ancestor\n")
        self.commit("common ancestor")
        self.git("checkout", "-b", "topic")
        self.write("web/pr.txt", "PR input\n")
        self.head = self.commit("PR input")
        self.git("checkout", "main")
        self.write("api/base-only.txt", "independent base input\n")
        self.base = self.commit("base advanced independently")
        self.git("merge", "--no-ff", "topic", "-m", "synthetic tested merge")
        self.merge = self.git("rev-parse", "HEAD")
        self.merge_tree = self.git("rev-parse", "HEAD^{tree}")
        self.head_tree = self.git("rev-parse", self.head + "^{tree}")
        payload = {"number": 148, "pull_request": {
            "base": {"sha": self.base}, "head": {"sha": self.head},
        }}
        event_path = self.root / "event.json"
        event_path.write_text(json.dumps(payload))
        self.environment.update({
            "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_SHA": self.merge, "GITHUB_REPOSITORY": "ZZZZihan/TeachingOpen",
            "GITHUB_WORKFLOW_SHA": self.merge, "GITHUB_JOB": "frontend",
            "GITHUB_REPOSITORY_ID": "1001", "GITHUB_RUN_ID": "777",
            "GITHUB_RUN_ATTEMPT": "1", "ImageOS": "ubuntu22",
            "ImageVersion": "20261012.1.0",
        })

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments], cwd=self.repository, env=self.environment,
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def write(self, relative, contents):
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def record(self):
        real_command = reuse.command

        def command(*arguments):
            if arguments[0] == "git":
                return real_command(*arguments)
            if arguments == ("node", "--version"):
                return RUNTIMES["frontend"]["node"]
            if arguments == ("npm", "--version"):
                return RUNTIMES["frontend"]["npm"]
            raise AssertionError("Unexpected runtime probe in the synthetic frontend receipt")

        with chdir(self.repository), patch.dict(os.environ, self.environment, clear=True), \
                patch.object(reuse, "verify_environment_contract") as contract, \
                patch.object(reuse, "command", side_effect=command):
            reuse.record_receipt("frontend")
        self.assertTrue(contract.called)
        return json.loads((self.repository / "ci-results/reuse/frontend/receipt.json").read_text())

    def test_original_receipt_contains_actual_merge_sha_tree_and_real_parent_order(self):
        receipt = self.record()
        self.assertNotEqual(self.merge, self.head)
        self.assertNotEqual(self.merge_tree, self.head_tree)
        self.assertEqual(receipt["checkout_sha"], self.merge)
        self.assertEqual(receipt["tree"], self.merge_tree)
        self.assertEqual(receipt["parents"], [self.base, self.head])
        self.assertEqual(receipt["head_sha"], self.head)
        self.assertEqual(receipt["base_sha"], self.base)
        self.assertEqual(receipt["workflow_blob"], self.git("rev-parse", "HEAD:.github/workflows/ci.yml"))
        self.assertEqual(receipt["mode"], "fresh")
        self.assertEqual(receipt["runtimes"], RUNTIMES["frontend"])

    def test_checkout_sha_different_from_event_cannot_create_a_receipt(self):
        self.environment["GITHUB_SHA"] = self.head
        with self.assertRaises(ValueError):
            self.record()
        self.assertFalse((self.repository / "ci-results/reuse/frontend/receipt.json").exists())

    def test_pr_head_checkout_cannot_replace_the_actual_two_parent_merge(self):
        self.git("checkout", "--detach", self.head)
        self.environment["GITHUB_SHA"] = self.head
        self.environment["GITHUB_WORKFLOW_SHA"] = self.head
        with self.assertRaises(ValueError):
            self.record()
        self.assertFalse((self.repository / "ci-results/reuse/frontend/receipt.json").exists())

    def test_workflow_execution_and_recorded_job_must_match_the_actual_source(self):
        original = dict(self.environment)
        for name, value in (("GITHUB_WORKFLOW_SHA", self.head), ("GITHUB_WORKFLOW_SHA", None),
                            ("GITHUB_JOB", "backend"), ("GITHUB_JOB", None)):
            with self.subTest(name=name, value=value):
                try:
                    if value is None:
                        self.environment.pop(name)
                    else:
                        self.environment[name] = value
                    with self.assertRaises(ValueError):
                        self.record()
                    self.assertFalse((self.repository / "ci-results/reuse/frontend/receipt.json").exists())
                finally:
                    self.environment = dict(original)


class PreflightFallbackTests(unittest.TestCase):
    def test_api_failure_produces_explicit_full_suite_outputs_without_reuse(self):
        for error in (OSError("Synthetic API outage"), ValueError("Missing complete API evidence"),
                      ValueError("Receipt mismatch: tools (fields: image_version)")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "github-output"
                summary = Path(directory) / "summary"
                with patch.object(sys, "argv", ["ci_reuse.py"]), \
                        patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}), \
                        patch.object(reuse, "GitHub", return_value=Mock()), \
                        patch.object(reuse, "target_context", return_value=valid_fixture()[0]), \
                        patch.object(reuse, "resolve", side_effect=error), \
                        patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(reuse.main(), 0)
                self.assertEqual(dict(line.split("=", 1) for line in output.read_text().splitlines()),
                                 {"reuse": "false", "source_run_id": ""})
                self.assertIn("Run the complete suite", summary.read_text())
                if isinstance(error, ValueError):
                    self.assertIn(str(error), summary.read_text())


class ReuseRequiredGateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = valid_fixture()
        self.proof = reuse.validate_evidence(*self.fixture)
        self.target_sha = self.fixture[0]["sha"]

    def needs(self, states=("success", "skipped", "skipped"), result="success", flag="true"):
        return {
            "changes": {"result": "skipped", "outputs": {}},
            "reuse": {"result": result, "outputs": {"reuse": flag}},
            **{name: {"result": state} for name, state in zip(HEAVY_JOBS, states)},
        }

    def check(self, needs=None, event="push", proof=None, target_sha=None):
        return required.check(
            event, self.needs() if needs is None else needs,
            reuse_proof=self.proof if proof is None else proof,
            target_sha=self.target_sha if target_sha is None else target_sha,
        )

    def test_verified_push_proof_requires_fresh_frontend_and_success_or_reused_other_jobs(self):
        self.assertIsNone(self.check())
        for states in itertools.product(("success", "skipped", "failure", "cancelled", None), repeat=3):
            expected = states[0] == "success" and all(
                state in ("success", "skipped") for state in states[1:])
            with self.subTest(states=states):
                if expected:
                    self.assertIsNone(self.check(self.needs(states)))
                else:
                    with self.assertRaises(ValueError):
                        self.check(self.needs(states))

    def test_every_missing_or_malformed_heavy_result_is_rejected(self):
        for name in HEAVY_JOBS:
            for value in (None, [], "skipped", {}, {"conclusion": "skipped"}):
                with self.subTest(name=name, value=value):
                    needs = self.needs()
                    needs[name] = value
                    with self.assertRaises(ValueError):
                        self.check(needs)
            needs = self.needs()
            del needs[name]
            with self.assertRaises(ValueError):
                self.check(needs)

    def test_failed_cancelled_or_noncanonical_reuse_outputs_never_authorize_skip(self):
        for result in ("failure", "cancelled", "skipped", "Success", None):
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.check(self.needs(result=result))
        for flag in ("false", "TRUE", "True", "true ", "", None, True, 1):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.check(self.needs(flag=flag))
        for value in (None, {}, [], "success", {"result": "success", "outputs": {}}):
            needs = self.needs()
            needs["reuse"] = value
            with self.subTest(reuse=value), self.assertRaises(ValueError):
                self.check(needs)

    def test_default_call_and_forged_output_without_proof_keep_push_full(self):
        with self.assertRaises(ValueError):
            required.check("push", self.needs())
        for proof in (None, {}, [], "true", {"schema": 1, "mode": "reused",
                                             "target_sha": self.target_sha}):
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                required.check("push", self.needs(), reuse_proof=proof, target_sha=self.target_sha)

    def test_proof_cannot_be_transferred_to_another_target_or_event(self):
        for target_sha in (None, "", "1" * 40, "a" * 39, True):
            with self.subTest(target_sha=target_sha), self.assertRaises(ValueError):
                required.check("push", self.needs(), reuse_proof=self.proof, target_sha=target_sha)
        for event in ("pull_request", "pull_request_target", "workflow_dispatch", "", None):
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.check(event=event)

    def test_missing_invalid_or_relabelled_proof_fields_cannot_pass_the_final_gate(self):
        for field in tuple(self.proof):
            proof = dict(self.proof)
            del proof[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.check(proof=proof)
        for field, value in (
            ("schema", True), ("schema", 2), ("mode", "fresh"),
            ("target_sha", "1" * 40), ("source_sha", "HEAD"),
            ("tree", ""), ("source_run_id", True), ("source_run_attempt", 2),
            ("pr_number", 0), ("source_job_ids", {}), ("source_url", ""),
        ):
            proof = {**self.proof, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.check(proof=proof)

    def test_actual_full_success_does_not_depend_on_the_optimization(self):
        needs = self.needs(("success",) * 3, result="failure", flag="false")
        self.assertIsNone(required.check("push", needs))
        self.assertIsNone(required.check("push", needs, reuse_proof={}, target_sha="wrong"))


if __name__ == "__main__":
    unittest.main()
