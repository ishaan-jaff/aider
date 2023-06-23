import argparse
import json
import os
import subprocess
import time
from json.decoder import JSONDecodeError
from pathlib import Path

from aider import models
from aider.coders import Coder
from aider.dump import dump  # noqa: F401
from aider.io import InputOutput


def main():
    parser = argparse.ArgumentParser(description="Aider Benchmark")
    parser.add_argument("dirname", type=str, help="Directory name")
    parser.add_argument("--model", "-m", type=str, help="Model name")
    parser.add_argument("--edit-format", "-e", type=str, help="Edit format")
    args = parser.parse_args()

    dirname = Path(args.dirname)

    cwd = os.getcwd()

    test_dnames = sorted(os.listdir(dirname))

    total_tests = len(test_dnames)
    completed_tests = 0
    passed_tests = 0

    total_cost = 0

    for testname in test_dnames:
        dump(testname)
        results = run_test(dirname / testname, args.model, args.edit_format)
        os.chdir(cwd)

        if results:
            completed_tests += 1
            passed = results["tests_passed"]
            if passed:
                passed_tests += 1

            dump(passed_tests, completed_tests, total_tests)

            pass_rate = 100 * passed_tests / completed_tests
            dump(pass_rate)

            total_cost += results["cost"]
            dump(total_cost)

            projected_cost = total_cost * total_tests / completed_tests
            dump(projected_cost)

            print()

        ###
        # input('next?')


def run_test(testdir, model_name, edit_format):
    if not os.path.isdir(testdir):
        print("Not a dir:", testdir)
        return

    os.chdir(testdir)

    results_fname = Path(".aider.results.json")
    if results_fname.exists():
        try:
            return json.loads(results_fname.read_text())
        except JSONDecodeError:
            print(f"{testdir}/{results_fname} failed to parse, skipping")
            return

    started_fname = Path(".aider.started")
    if started_fname.exists():
        # print(f"{testdir}/{started_fname} exists, skipping")
        # return
        pass
    started_fname.touch()

    fnames = []
    for fname in os.listdir("."):
        if "test" not in fname and os.path.isfile(fname) and fname[0] != ".":
            fnames.append(fname)

    instructions = Path(".docs/instructions.md").read_text()
    instructions += (
        "\n\n=====\n\nModify these files according to the above instructions: " + " ".join(fnames)
    )

    io = InputOutput(
        pretty=True,
        yes=False,
    )

    main_model = models.Model(model_name)
    edit_format = edit_format or main_model.edit_format

    dump(main_model)
    dump(edit_format)

    coder = Coder.create(
        main_model,
        edit_format,
        io,
        os.environ["OPENAI_API_KEY"],
        fnames=fnames,
        # verbose=True,
        use_git=False,
        stream=False,
    )

    start = time.time()
    coder.run(with_message=instructions)
    dur = time.time() - start

    if coder.num_control_c:
        raise KeyboardInterrupt

    passed = run_tests()

    results = dict(
        testdir=str(testdir),
        model=main_model.name,
        edit_format=edit_format,
        tests_passed=passed,
        cost=coder.total_cost,
        duration=dur,
    )
    dump(results)

    results_fname.write_text(json.dumps(results, indent=4))
    started_fname.unlink()

    return results


def run_tests():
    test_files = [file for file in os.listdir() if file.endswith("_test.py")]
    assert len(test_files)

    all_tests_passed = True

    for test_file in test_files:
        dump(test_file)
        result = subprocess.run(["pytest", test_file], capture_output=True, text=True, timeout=60)
        print(result.stdout)
        print(result.stderr)

        if result.returncode != 0:
            all_tests_passed = False
            print(f"Test {test_file} failed with the following output:\n{result.stderr}")

    return all_tests_passed


if __name__ == "__main__":
    main()