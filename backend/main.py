import argparse
import contextlib
import io
import os
import random
import re
import sys
import textwrap
import time

import pandas as pd

from allocator import (
    ADJ_MODES,
    count_violations,
    distribute,
    load_halls_csv,
    load_students_csv,
    parse_hall_spec,
    prompt_halls,
    prompt_students,
    row_label,
    show_results,
    solve_hall,
)


# ----------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------

ADJ_DESCRIPTION = {
    "side": "left/right neighbours",
    "grid": "left/right and front/back neighbours",
    "all8": "all 8 surrounding seats",
}


def print_inputs(halls, students, adjacency):
    """Show the input of a test case: halls, seats, students and the constraint."""
    wrap = lambda label, text: textwrap.fill(
        text, width=78, initial_indent=f"{label:<10}: ",
        subsequent_indent=" " * 12)

    print("INPUT")
    print(wrap("Halls", ", ".join(f"{n} ({r} x {c})" for n, r, c in halls)))
    for name, rows, cols in halls:
        seats = [f"{row_label(r)}{c + 1}" for r in range(rows) for c in range(cols)]
        label = f"Seats" if len(halls) == 1 else f"Seats {name}"
        print(wrap(label, " ".join(seats) if len(seats) <= 40
                   else f"{seats[0]} ... {seats[-1]} ({len(seats)} seats)"))
    shown = ", ".join(f"{s['id']} ({s['section']})" for s in students)
    sections = {}
    for st in students:
        sections[st["section"]] = sections.get(st["section"], 0) + 1
    print(wrap("Students", shown if len(students) <= 40
               else f"{len(students)} students (first: {shown.split(', ')[0]})"))
    # print(wrap("Sections", ", ".join(f"{k}: {v}" for k, v in sections.items())))
    # print(wrap("Constraint",
    #            f"adjacent students ({ADJ_DESCRIPTION[adjacency]}) must belong to "
               # f"different sections"))
    print()
def validate_inputs(halls, students):
    """Raise ValueError if the halls/students combination is unusable."""
    if not halls or not students:
        raise ValueError("need at least one hall and one student.")
    names = [h[0] for h in halls]
    if len(set(names)) != len(names):
        raise ValueError("hall names must be unique.")
    ids = [s["id"] for s in students]
    dupes = {x for x in ids if ids.count(x) > 1}
    if dupes:
        raise ValueError(f"duplicate student IDs: {sorted(dupes)}")
    capacity = sum(r * c for _, r, c in halls)
    if len(students) > capacity:
        raise ValueError(f"{len(students)} students but only {capacity} seats.")


def solve_all_halls(students, halls, adjacency, seed, shuffle):
    """Distribute students over halls and solve one CSP per hall.

    Returns (layouts, failed_hall, placed). layouts is None if a hall failed.
    """
    rng = random.Random(seed) if (shuffle or seed is not None) else None
    placed = distribute(students, halls, rng)
    layouts = {}
    for name, rows, cols in halls:
        layout = solve_hall(placed[name], rows, cols, adjacency, rng)
        if layout is None:
            return None, name, placed
        layouts[name] = layout
    return layouts, None, placed


# ----------------------------------------------------------------------------
# Batch mode: run many test cases at once
# ----------------------------------------------------------------------------
def natural_key(text):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(text))]


def load_batch(path, default_adjacency):
    """Return a list of case dicts from a directory or a manifest CSV.

    Directory : every <name>_students.csv with a matching <name>_halls.csv is a case.
                If the directory contains manifest.csv, that is used instead.
    Manifest  : CSV with columns  case,students,halls[,adjacency,expect]
                (paths are relative to the manifest; expect = solved | no_solution)
    """
    if os.path.isdir(path):
        manifest = os.path.join(path, "manifest.csv")
        if os.path.exists(manifest):
            path = manifest
        else:
            cases = []
            for fname in sorted(os.listdir(path), key=natural_key):
                m = re.fullmatch(r"(.+)_students\.csv", fname)
                if not m:
                    continue
                halls_file = os.path.join(path, f"{m.group(1)}_halls.csv")
                if os.path.exists(halls_file):
                    cases.append({"case": m.group(1),
                                  "students": os.path.join(path, fname),
                                  "halls": halls_file,
                                  "adjacency": default_adjacency,
                                  "expect": "solved"})
            return cases

    base = os.path.dirname(os.path.abspath(path))
    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip().lower() for c in df.columns]
    for col in ("case", "students", "halls"):
        if col not in df.columns:
            raise ValueError(f"{path}: manifest needs columns case,students,halls "
                             f"(optional: adjacency,expect)")
    cases = []
    for _, row in df.iterrows():
        adjacency = row.get("adjacency", "").strip() or default_adjacency
        if adjacency not in ADJ_MODES:
            raise ValueError(f"case {row['case']}: unknown adjacency '{adjacency}'")
        cases.append({"case": row["case"].strip(),
                      "students": os.path.join(base, row["students"].strip()),
                      "halls": os.path.join(base, row["halls"].strip()),
                      "adjacency": adjacency,
                      "expect": (row.get("expect", "").strip().lower() or "solved")})
    return cases


def run_batch(args):
    try:
        cases = load_batch(args.batch, args.adjacency)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"Error: {e}")
    if not cases:
        sys.exit(f"Error: no test cases found in '{args.batch}'.")

    if args.output:
        os.makedirs(args.output, exist_ok=True)

    rows, mismatches = [], 0
    for case in cases:
        result = {"Case": case["case"], "Students": "-", "Seats": "-",
                  "Adjacency": case["adjacency"], "Result": "ERROR",
                  "Violations": "-", "Time (ms)": "-"}

        if not args.summary_only:
            print(f"\n{'=' * 64}\nCASE {case['case']}   (adjacency: {case['adjacency']})\n"
                  f"{'=' * 64}")
        try:
            halls = load_halls_csv(case["halls"])
            students = load_students_csv(case["students"])
            validate_inputs(halls, students)
            capacity = sum(r * c for _, r, c in halls)
            result["Students"], result["Seats"] = len(students), capacity
            if not args.summary_only:
                print_inputs(halls, students, case["adjacency"])
                print("RESULT")

            t0 = time.perf_counter()
            layouts, failed, placed = solve_all_halls(
                students, halls, case["adjacency"], args.seed, args.shuffle)
            elapsed = (time.perf_counter() - t0) * 1000
            result["Time (ms)"] = f"{elapsed:.1f}"

            if layouts is None:
                result["Result"] = "NO SOLUTION"
                if not args.summary_only:
                    print(f"No conflict-free arrangement exists for hall {failed} "
                          f"({len(placed[failed])} students).")
            else:
                result["Result"] = "SOLVED"
                result["Violations"] = sum(
                    count_violations(layouts[n], r, c, case["adjacency"])
                    for n, r, c in halls)
                out_file = (os.path.join(args.output, f"{case['case']}_allocation.csv")
                            if args.output else None)
                if args.summary_only:
                    if out_file:                      # still export, but print nothing
                        with contextlib.redirect_stdout(io.StringIO()):
                            show_results(halls, layouts, case["adjacency"], out_file)
                else:
                    show_results(halls, layouts, case["adjacency"], out_file)
        except (ValueError, FileNotFoundError) as e:
            result["Result"] = "ERROR"
            if not args.summary_only:
                print(f"Error: {e}")

        expected = "SOLVED" if case["expect"] in ("solved", "solvable", "pass") \
            else "NO SOLUTION"
        ok = result["Result"] == expected and result["Violations"] in (0, "-")
        result["Expected"] = expected
        result["Check"] = "PASS" if ok else "FAIL"
        mismatches += 0 if ok else 1
        rows.append(result)

    print(f"\n{'=' * 64}\nBATCH SUMMARY\n{'=' * 64}")
    print(pd.DataFrame(rows).to_string(index=False))
    passed = len(rows) - mismatches
    print(f"\n{passed}/{len(rows)} cases behaved as expected.")
    sys.exit(0 if mismatches == 0 else 1)


# ----------------------------------------------------------------------------
# Single run (CSV and/or interactive)
# ----------------------------------------------------------------------------
def run_single(args):
    halls, students = [], []
    try:
        if args.halls:
            halls += load_halls_csv(args.halls)
        for spec in args.hall:
            name, rows, cols = parse_hall_spec(spec)
            halls.append((name or chr(65 + len(halls)), rows, cols))
        if not halls or args.interactive:
            halls += prompt_halls()

        if args.students:
            students += load_students_csv(args.students)
        if not students or args.interactive:
            students += prompt_students()
        validate_inputs(halls, students)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"Error: {e}")

    capacity = sum(r * c for _, r, c in halls)
    print(
        f"\nStudents: {len(students)} | Seats: {capacity} | "
        f"Sections: {len({s['section'] for s in students})} | "
        f"Adjacency: {args.adjacency}"
    )

    t0 = time.perf_counter()
    layouts, failed, placed = solve_all_halls(
        students, halls, args.adjacency, args.seed, args.shuffle)
    elapsed = time.perf_counter() - t0

    if layouts is None:
        rows_, cols_ = next((r, c) for n, r, c in halls if n == failed)
        print(f"\nNo conflict-free arrangement exists for hall {failed} "
              f"({len(placed[failed])} students, {rows_ * cols_} seats).")
        print("Try: adding seats/halls, using --adjacency side, or splitting "
              "large sections.")
        sys.exit(1)

    show_results(halls, layouts, args.adjacency, args.output)
    print(
        f"\nSolved {len(halls)} hall CSP(s) with python-constraint in "
        f"{elapsed * 1000:.1f} ms, seat utilisation {len(students) / capacity:.0%}"
    )


def main():
    p = argparse.ArgumentParser(
        description="Exam hall seating allocation using python-constraint (CSP)"
    )
    p.add_argument("-s", "--students", help="students CSV (id,section[,name])")
    p.add_argument("--halls", help="halls CSV (hall,rows,cols)")
    p.add_argument("--hall", action="append", default=[],
                   help="hall spec NAME:ROWSxCOLS (repeatable), e.g. A:5x6")
    p.add_argument("-i", "--interactive", action="store_true",
                   help="also prompt for extra students/halls after loading files")
    p.add_argument("-a", "--adjacency", choices=ADJ_MODES, default="side",
                   help="adjacent = side (left/right, default), grid (+front/back), "
                        "all8 (+diagonals)")
    p.add_argument("-o", "--output",
                   help="write allocation to this CSV file "
                        "(in --batch mode: a directory, one CSV per case)")
    p.add_argument("--shuffle", action="store_true", help="randomise for fairer seating")
    p.add_argument("--seed", type=int, help="random seed (implies --shuffle)")
    p.add_argument("-b", "--batch", metavar="DIR_OR_MANIFEST",
                   help="run ALL test cases at once: a folder of caseN_students.csv / "
                        "caseN_halls.csv pairs (uses manifest.csv in it if present) "
                        "or a manifest CSV (case,students,halls[,adjacency,expect])")
    p.add_argument("--summary-only", action="store_true",
                   help="in --batch mode, print only the summary table")
    args = p.parse_args()

    if args.batch:
        if args.students or args.halls or args.hall or args.interactive:
            sys.exit("Error: --batch cannot be combined with --students/--halls/"
                     "--hall/--interactive.")
        run_batch(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
