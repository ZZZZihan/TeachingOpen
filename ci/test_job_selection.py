"""Offline CI planning and aggregate-status regressions; no services or network."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_required_jobs as required
import select_jobs as selection


ROOT = Path(__file__).resolve().parents[1]
JOBS = ("frontend", "tools", "backend")


def flags(*selected):
    return {job: job in selected for job in JOBS}


class PathSelectionTests(unittest.TestCase):
    def test_paths_select_real_consumers_including_cross_directory_inputs(self):
        # Expectations are based on the commands and source inputs used by CI,
        # including reads outside the directory containing the consuming job.
        cases = {
            "web/src/views/home/Home.vue": flags("frontend"),
            "web/package-lock.json": flags("frontend"),
            "web/tests/public-boundaries-live.py": flags("frontend", "backend"),
            "web/nginx/default.conf": flags("frontend", "tools"),
            "web/src/views/system/modules/DepartModal.vue": flags("frontend", "tools"),
            "api/jeecg-boot-module-system/src/main/java/example/Controller.java": flags("backend", "tools"),
            "api/jeecg-boot-base-common/src/main/java/org/jeecg/common/util/PasswordUtil.java": flags("backend", "tools"),
            "api/jeecg-boot-base-common/src/main/java/org/jeecg/common/constant/CacheConstant.java": flags("backend", "tools"),
            "api/jeecg-boot-module-system/src/test/java/example/NewRegressionTest.java": flags("backend", "tools"),
            "api/dev/local_recovery.py": flags("backend", "tools"),
            "api/db/work-events.sql": flags("backend", "tools"),
            "deploy/scheduled_backup.py": flags("backend", "tools"),
            "deploy/ip-https-proxy.properties.example": flags("backend", "tools"),
            "deploy/test_ip_https_proxy.py": flags("backend", "tools"),
            "examples/showcase/catalog.json": flags("frontend"),
            "资料/nginx.example.conf": flags("tools"),
            "ci/test_global_rule_sql.py": flags(*JOBS),
            ".github/workflows/ci.yml": flags(*JOBS),
            ".github/actions/example/action.yml": flags(*JOBS),
            "docs/verification/result.md": flags(),
            "evidence/ci/synthetic-result.json": flags(),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(selection.classify_paths([path]), expected)

    def test_multiple_paths_union_consumers_and_documentation_never_erases_source(self):
        self.assertEqual(selection.classify_paths([
            "docs/explanation.md", "web/src/example.vue", "api/dev/probe.py",
        ]), flags(*JOBS))
        self.assertEqual(selection.classify_paths([
            "docs/explanation.md", "evidence/result.json", "web/src/example.vue",
        ]), flags("frontend"))

    def test_unknown_or_empty_changes_conservatively_run_every_job(self):
        for paths in ([], ["README.md"], [".gitignore"], [".gitattributes"],
                      ["new-area/feature.py"], ["web/src/example.vue", "new-area/feature.py"]):
            with self.subTest(paths=paths):
                self.assertEqual(selection.classify_paths(paths), flags(*JOBS))

    def test_malformed_path_inputs_cannot_silently_skip_jobs(self):
        for paths in (None, "docs/explanation.md", [None], [42], [""],
                      ["/docs/explanation.md"], ["../docs/explanation.md"],
                      ["web/../docs/explanation.md"], ["./docs/explanation.md"],
                      ["docs\\explanation.md"], ["docs/explanation\x00.md"]):
            with self.subTest(paths=paths):
                self.assertEqual(selection.classify_paths(paths), flags(*JOBS))

    def test_valid_git_paths_keep_unicode_spaces_and_newlines(self):
        self.assertEqual(selection.classify_paths([
            "web/src/中文 空格\n组件.vue",
        ]), flags("frontend"))


class GitRepositoryTestCase(unittest.TestCase):
    """Use actual commit graphs so path parsing and diff fallbacks are exercised."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="teachingopen-ci-selection-")
        self.addCleanup(self.directory.cleanup)
        self.repository = Path(self.directory.name) / "repository"
        self.repository.mkdir()
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Offline CI regression")
        self.git("config", "user.email", "ci-selection@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *arguments):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
        environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        return subprocess.run(
            ["git", *arguments], cwd=self.repository, check=True,
            capture_output=True, text=True,
            env=environment,
        ).stdout.strip()

    def write(self, path, contents="synthetic CI input\n"):
        destination = self.repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")

    def commit(self, message="offline fixture"):
        self.git("add", "--all")
        self.git("commit", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")


class EventSelectionTests(GitRepositoryTestCase):
    def merge_fixture(self, paths, initial_paths=()):
        for path in initial_paths:
            self.write(path)
        self.write("docs/base.md")
        self.base = self.commit("base")
        self.git("checkout", "-b", "topic")
        for path in paths:
            self.write(path, "changed synthetic input\n")
        self.head = self.commit("PR changes")
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "topic", "-m", "synthetic merge")
        self.merge = self.git("rev-parse", "HEAD")
        self.event = {"pull_request": {
            "base": {"sha": self.base}, "head": {"sha": self.head},
        }}
        return self.event

    def plan(self, event=None, ref=None, event_name="pull_request", repository=None):
        return selection.select_for_event(
            event_name, self.event if event is None else event,
            self.repository if repository is None else repository,
            self.merge if ref is None else ref,
        )

    def assert_full(self, plan):
        self.assertEqual(plan["mode"], "full")
        self.assertEqual(plan["jobs"], flags(*JOBS))
        self.assertIsInstance(plan["reason"], str)
        self.assertTrue(plan["reason"])

    def test_pr_diff_uses_actual_merge_commit_and_preserves_unusual_file_names(self):
        changed = "web/src/中文 空格\n组件.vue"
        self.merge_fixture([changed])
        plan = self.plan()
        self.assertEqual(plan["mode"], "selective")
        self.assertEqual(plan["jobs"], flags("frontend"))
        self.assertEqual(plan["paths"], [changed])

    def test_deleted_inputs_still_trigger_their_consuming_jobs(self):
        removed = "web/src/views/system/modules/DepartModal.vue"
        self.write(removed)
        self.write("docs/base.md")
        self.base = self.commit("base")
        self.git("checkout", "-b", "topic")
        (self.repository / removed).unlink()
        self.head = self.commit("remove cross-directory input")
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "topic", "-m", "synthetic merge")
        self.merge = self.git("rev-parse", "HEAD")
        self.event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}
        plan = self.plan()
        self.assertEqual(plan["jobs"], flags("frontend", "tools"))
        self.assertEqual(plan["paths"], [removed])

    def test_renames_include_both_departing_and_arriving_dependency_scopes(self):
        for old, new, expected in (
            ("api/dev/input.py", "docs/input.py", flags("backend", "tools")),
            ("docs/input.py", "api/dev/input.py", flags("backend", "tools")),
            ("api/dev/input.py", "web/src/input.py", flags(*JOBS)),
            ("web/src/input.py", "docs/input.py", flags("frontend")),
        ):
            with self.subTest(old=old, new=new):
                with tempfile.TemporaryDirectory(prefix="teachingopen-ci-rename-") as raw:
                    self.repository = Path(raw)
                    self.git("init", "--initial-branch=main")
                    self.git("config", "user.name", "Offline CI regression")
                    self.git("config", "user.email", "ci-selection@example.invalid")
                    self.git("config", "commit.gpgsign", "false")
                    self.write(old)
                    self.base = self.commit("base")
                    self.git("checkout", "-b", "topic")
                    (self.repository / new).parent.mkdir(parents=True, exist_ok=True)
                    self.git("mv", old, new)
                    self.head = self.commit("move input")
                    self.git("checkout", "main")
                    self.git("merge", "--no-ff", "topic", "-m", "synthetic merge")
                    self.merge = self.git("rev-parse", "HEAD")
                    self.event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}
                    plan = self.plan()
                    self.assertEqual(plan["mode"], "selective")
                    self.assertEqual(plan["jobs"], expected)
                    self.assertEqual(set(plan["paths"]), {old, new})

    def test_base_only_changes_are_excluded_from_the_pr_three_dot_diff(self):
        self.write("docs/base.md")
        self.commit("common ancestor")
        self.git("checkout", "-b", "topic")
        self.write("deploy/tool.py")
        self.head = self.commit("PR changes")
        self.git("checkout", "main")
        self.write("web/src/base-only.vue")
        self.base = self.commit("independent base changes")
        self.git("merge", "--no-ff", "topic", "-m", "synthetic merge")
        self.merge = self.git("rev-parse", "HEAD")
        self.event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}
        plan = self.plan()
        self.assertEqual(plan["jobs"], flags("backend", "tools"))
        self.assertEqual(plan["paths"], ["deploy/tool.py"])

    def test_documentation_pr_can_skip_heavy_jobs_but_empty_pr_runs_all(self):
        self.merge_fixture(["docs/change.md"])
        self.assertEqual(self.plan()["jobs"], flags())
        event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.base}}}
        self.assert_full(self.plan(event))

    def test_non_pr_events_always_run_all_without_needing_a_git_repository(self):
        for event_name in ("push", "workflow_dispatch", "", None):
            with self.subTest(event_name=event_name):
                self.assert_full(selection.select_for_event(
                    event_name, {}, self.repository / "does-not-exist", "refs/heads/main",
                ))

    def test_main_push_always_runs_all_even_for_valid_documentation_only_diff(self):
        self.merge_fixture(["docs/change.md"])
        self.assert_full(self.plan(event_name="push"))

    def test_missing_malformed_or_unavailable_event_objects_fall_back_to_all(self):
        self.merge_fixture(["docs/change.md"])
        for event in ({}, {"pull_request": None}, {"pull_request": []}, [],
                      {"pull_request": {"base": {"sha": self.base}}},
                      {"pull_request": {"base": {"sha": "short"}, "head": {"sha": self.head}}},
                      {"pull_request": {"base": {"sha": "f" * 40}, "head": {"sha": self.head}}},
                      {"pull_request": {"base": {"sha": self.base}, "head": {"sha": "f" * 40}}}):
            with self.subTest(event=event):
                self.assert_full(self.plan(event))

    def test_checkout_sha_merge_parents_and_git_repository_must_match_the_event(self):
        self.merge_fixture(["docs/change.md"])
        self.assert_full(self.plan(ref=self.head))
        self.assert_full(self.plan(ref="not-a-sha"))
        self.assert_full(self.plan(repository=self.repository / "missing"))
        mismatched = {"pull_request": {"base": {"sha": self.head}, "head": {"sha": self.base}}}
        self.assert_full(self.plan(mismatched))
        self.git("checkout", "topic")
        self.assert_full(self.plan(ref=self.head))

    def test_a_valid_merge_with_no_changed_paths_conservatively_runs_all(self):
        self.merge_fixture([])
        self.assertEqual(self.git("rev-list", "--parents", "-n", "1", self.merge).split()[1:],
                         [self.base, self.head])
        self.assert_full(self.plan())

    def test_merge_candidates_with_more_than_two_parents_run_all(self):
        self.merge_fixture(["docs/change.md"])
        self.git("checkout", "--detach", self.base)
        third = self.commit("third parent")
        merge = self.git("commit-tree", self.git("rev-parse", self.head + "^{tree}"),
                         "-p", self.base, "-p", self.head, "-p", third,
                         "-m", "synthetic octopus merge")
        self.git("checkout", "--detach", merge)
        self.merge = merge
        self.assert_full(self.plan())

    def test_crisscross_history_with_multiple_merge_bases_runs_all(self):
        self.write("docs/root.md")
        common = self.commit("common ancestor")
        self.git("checkout", "-b", "left")
        self.write("docs/left.md")
        left = self.commit("left ancestor")
        self.git("checkout", "-b", "right", common)
        self.write("docs/right.md")
        right = self.commit("right ancestor")
        self.base = self.git("commit-tree", self.git("rev-parse", left + "^{tree}"),
                             "-p", left, "-p", right, "-m", "first merge")
        self.write("web/src/crisscross.vue")
        tree_commit = self.commit("different head tree")
        self.head = self.git("commit-tree", self.git("rev-parse", tree_commit + "^{tree}"),
                             "-p", right, "-p", left, "-m", "parallel merge")
        self.merge = self.git("commit-tree", self.git("rev-parse", self.head + "^{tree}"),
                              "-p", self.base, "-p", self.head, "-m", "PR merge")
        self.git("checkout", "--detach", self.merge)
        self.event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}
        self.assertEqual(set(self.git("merge-base", "--all", self.base, self.head).split()),
                         {left, right})
        self.assert_full(self.plan())

    def run_cli(self, event_path, output_path=None, event_name="pull_request"):
        env = dict(os.environ)
        env.pop("GITHUB_OUTPUT", None)
        env.pop("GITHUB_STEP_SUMMARY", None)
        if output_path is not None:
            env["GITHUB_OUTPUT"] = str(output_path)
        return subprocess.run([
            sys.executable, str(ROOT / "ci/select_jobs.py"),
            "--event-name", event_name, "--event-path", str(event_path),
            "--repository", str(self.repository), "--ref", self.merge,
        ], capture_output=True, text=True, env=env)

    def test_cli_emits_json_and_github_outputs_for_the_same_plan(self):
        self.merge_fixture(["web/src/组件.vue"])
        event_path = Path(self.directory.name) / "event.json"
        event_path.write_text(json.dumps(self.event), encoding="utf-8")
        output_path = Path(self.directory.name) / "github-output"
        process = self.run_cli(event_path, output_path)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["jobs"], flags("frontend"))
        outputs = dict(line.split("=", 1) for line in output_path.read_text().splitlines())
        self.assertEqual(outputs["mode"], "selective")
        self.assertEqual({job: outputs[job] for job in JOBS}, {
            "frontend": "true", "backend": "false", "tools": "false",
        })

    def test_cli_unreadable_or_invalid_event_falls_back_without_false_skip(self):
        self.merge_fixture(["docs/change.md"])
        event_path = Path(self.directory.name) / "event.json"
        for contents in (None, "{invalid", "null", "[]"):
            with self.subTest(contents=contents):
                if contents is not None:
                    event_path.write_text(contents, encoding="utf-8")
                process = self.run_cli(event_path)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assert_full(json.loads(process.stdout))

    def test_cli_output_write_failure_is_nonzero_so_workflow_can_fall_back(self):
        self.merge_fixture(["docs/change.md"])
        event_path = Path(self.directory.name) / "event.json"
        event_path.write_text(json.dumps(self.event), encoding="utf-8")
        process = self.run_cli(event_path, Path(self.directory.name))
        self.assertNotEqual(process.returncode, 0)


class PlanNormalizationTests(unittest.TestCase):
    def full_outputs(self):
        return {"selective": "false", **dict.fromkeys(JOBS, "true")}

    def test_valid_plans_keep_each_exact_string_flag_for_workflow_consumers(self):
        for values in itertools.product(("true", "false"), repeat=len(JOBS)):
            outputs = {"mode": "selective", **dict(zip(JOBS, values))}
            with self.subTest(outputs=outputs):
                self.assertEqual(required.normalize_plan({
                    "outcome": "success", "outputs": outputs,
                }), {"selective": "true", **dict(zip(JOBS, values))})

    def test_missing_failed_or_malformed_steps_enable_every_heavy_job(self):
        valid_outputs = {"mode": "selective", **dict.fromkeys(JOBS, "false")}
        cases = [None, [], "success", {}, {"outputs": valid_outputs}]
        for outcome in (None, "failure", "cancelled", "skipped", "", "Success", True):
            cases.append({"outcome": outcome, "outputs": valid_outputs})
        for outputs in (None, [], "false", {}, {"mode": "selective"}):
            cases.append({"outcome": "success", "outputs": outputs})
        cases.append({"outcome": "success", "outputs": dict.fromkeys(JOBS, "false")})
        for plan in cases:
            with self.subTest(plan=plan):
                self.assertEqual(required.normalize_plan(plan), self.full_outputs())

    def test_nonselective_or_nonexact_mode_and_flags_cannot_skip_any_job(self):
        valid = {"mode": "selective", **dict.fromkeys(JOBS, "false")}
        for mode in ("full", "SELECTIVE", "Selective", "selective ", "", None, True):
            with self.subTest(mode=mode):
                self.assertEqual(required.normalize_plan({
                    "outcome": "success", "outputs": {**valid, "mode": mode},
                }), self.full_outputs())
        for job in JOBS:
            missing = dict(valid)
            del missing[job]
            self.assertEqual(required.normalize_plan({
                "outcome": "success", "outputs": missing,
            }), self.full_outputs())
            for value in ("TRUE", "FALSE", "True", "False", "false ", "", None, True, False, 0, [], {}):
                with self.subTest(job=job, value=value):
                    self.assertEqual(required.normalize_plan({
                        "outcome": "success", "outputs": {**valid, job: value},
                    }), self.full_outputs())

    def test_normalize_cli_writes_the_same_safe_outputs_as_its_json_response(self):
        for payload, expected in (
            (json.dumps({"outcome": "success", "outputs": {
                "mode": "selective", "frontend": "false", "backend": "true", "tools": "false",
            }}), {"selective": "true", "frontend": "false", "backend": "true", "tools": "false"}),
            (json.dumps({"outcome": "success", "outputs": {
                "mode": "selective", **dict.fromkeys(JOBS, "FALSE"),
            }}), self.full_outputs()),
            ("{invalid", self.full_outputs()),
            ("", self.full_outputs()),
            ("null", self.full_outputs()),
            ("[]", self.full_outputs()),
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory(prefix="teachingopen-ci-normalize-") as raw:
                output = Path(raw) / "github-output"
                process = subprocess.run([
                    sys.executable, str(ROOT / "ci/check_required_jobs.py"), "--normalize",
                ], capture_output=True, text=True, env={
                    **os.environ, "CI_PLAN_JSON": payload, "GITHUB_OUTPUT": str(output),
                })
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                self.assertEqual(json.loads(process.stdout), expected)
                self.assertEqual(dict(line.split("=", 1) for line in output.read_text().splitlines()), expected)

    def test_normalize_cli_cannot_report_success_when_workflow_outputs_were_not_written(self):
        with tempfile.TemporaryDirectory(prefix="teachingopen-ci-normalize-") as raw:
            process = subprocess.run([
                sys.executable, str(ROOT / "ci/check_required_jobs.py"), "--normalize",
            ], capture_output=True, text=True, env={
                **os.environ, "CI_PLAN_JSON": "{}", "GITHUB_OUTPUT": raw,
            })
            self.assertNotEqual(process.returncode, 0)


class RequiredJobsTests(unittest.TestCase):
    def needs(self, selected=("frontend",), results=None, changes_result="success", outputs=None):
        plan = {"selective": "true", **{
            job: "true" if job in selected else "false" for job in JOBS
        }}
        if outputs is not None:
            plan = outputs
        default_results = {job: "success" if job in selected else "skipped" for job in JOBS}
        if results is not None:
            default_results = results
        return {
            "changes": {"result": changes_result, "outputs": plan},
            **{job: {"result": result} for job, result in default_results.items()},
        }

    def assert_gate(self, allowed, needs, event_name="pull_request"):
        if allowed:
            self.assertIsNone(required.check(event_name, needs))
        else:
            with self.assertRaises(ValueError):
                required.check(event_name, needs)

    def test_every_selection_combination_rejects_failed_cancelled_missing_or_unknown_jobs(self):
        states = ("success", "skipped", "failure", "cancelled", "", None, "unknown")
        for mask in itertools.product((False, True), repeat=len(JOBS)):
            selected = tuple(job for job, chosen in zip(JOBS, mask) if chosen)
            for states_by_job in itertools.product(states, repeat=len(JOBS)):
                results = dict(zip(JOBS, states_by_job))
                allowed = all(
                    results[job] == "success" if job in selected
                    else results[job] in ("success", "skipped")
                    for job in JOBS
                )
                with self.subTest(selected=selected, results=results):
                    self.assert_gate(allowed, self.needs(selected, results))
            for missing in JOBS:
                needs = self.needs(selected)
                del needs[missing]
                with self.subTest(selected=selected, missing=missing):
                    self.assert_gate(False, needs)

    def test_classifier_failure_only_passes_after_all_heavy_jobs_really_succeed(self):
        for classifier_result in ("failure", "cancelled", "skipped", "", None, "unknown"):
            for values in itertools.product(("success", "skipped", "failure", "cancelled"), repeat=3):
                results = dict(zip(JOBS, values))
                with self.subTest(classifier_result=classifier_result, results=results):
                    self.assert_gate(all(value == "success" for value in values), self.needs(
                        selected=(), results=results, changes_result=classifier_result,
                    ))

    def test_absent_or_malformed_selection_requires_all_jobs_and_never_authorizes_skip(self):
        invalid_outputs = [
            {}, None, [], "true", {"selective": "false"},
            {"selective": "true", "frontend": "false", "backend": "false"},
        ]
        valid = {"selective": "true", **dict.fromkeys(JOBS, "false")}
        for field in ("selective", *JOBS):
            for value in (True, False, "TRUE", "False", "", None, 0, "maybe"):
                invalid_outputs.append({**valid, field: value})
        for outputs in invalid_outputs:
            with self.subTest(outputs=outputs):
                needs = self.needs(selected=(), outputs=outputs)
                # Set explicitly because None represents missing outputs, not a
                # request to use the helper's normal default.
                needs["changes"]["outputs"] = outputs
                self.assert_gate(False, needs)
                for job in JOBS:
                    needs[job]["result"] = "success"
                self.assert_gate(True, needs)
        needs = self.needs(selected=())
        del needs["changes"]
        self.assert_gate(False, needs)
        for job in JOBS:
            needs[job]["result"] = "success"
        self.assert_gate(True, needs)

    def test_push_and_other_events_require_all_jobs_despite_selective_outputs(self):
        for event_name in ("push", "workflow_dispatch", "", None):
            for values in itertools.product(("success", "skipped", "failure", "cancelled"), repeat=3):
                with self.subTest(event_name=event_name, results=values):
                    self.assert_gate(all(value == "success" for value in values), self.needs(
                        selected=(), results=dict(zip(JOBS, values)),
                    ), event_name)

    def test_malformed_job_objects_and_missing_result_fields_are_rejected(self):
        for job in JOBS:
            for result_object in (None, [], "success", {}, {"conclusion": "success"}):
                with self.subTest(job=job, result_object=result_object):
                    needs = self.needs(selected=())
                    needs[job] = result_object
                    self.assert_gate(False, needs)
        for needs in (None, [], "success"):
            with self.subTest(needs=needs):
                self.assert_gate(False, needs)

    def test_required_cli_matches_success_and_failure_exit_status(self):
        for needs, allowed in (
            (self.needs(), True),
            (self.needs(results=dict.fromkeys(JOBS, "success"), changes_result="failure"), True),
            (self.needs(selected=(), changes_result="failure"), False),
            (self.needs(results={"frontend": "failure", "backend": "skipped", "tools": "skipped"}), False),
        ):
            with self.subTest(needs=needs):
                process = subprocess.run([
                    sys.executable, str(ROOT / "ci/check_required_jobs.py"),
                ], capture_output=True, text=True, env={
                    **os.environ, "CI_EVENT_NAME": "pull_request", "CI_NEEDS_JSON": json.dumps(needs),
                })
                self.assertEqual(process.returncode == 0, allowed, process.stdout + process.stderr)

    def test_required_cli_rejects_missing_or_invalid_job_result_json(self):
        for payload in ("", "{invalid", "null", "[]", "{}"):
            with self.subTest(payload=payload):
                process = subprocess.run([
                    sys.executable, str(ROOT / "ci/check_required_jobs.py"),
                ], capture_output=True, text=True, env={
                    **os.environ, "CI_EVENT_NAME": "pull_request", "CI_NEEDS_JSON": payload,
                })
                self.assertNotEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
