import argparse
import sys
from allocator import (
    load_halls_csv,
    parse_hall_spec,
    load_students_csv,
    prompt_halls,
    prompt_students,
    show_results,
    distribute,
    solve_hall,
    ADJ_MODES,
)
import random
import time


def main():
    p = argparse.ArgumentParser(
        description="Exam hall seating allocation using python-constraint (CSP)"
    )
    p.add_argument("-s", "--students", help="students CSV (id,section[,name])")
    p.add_argument("--halls", help="halls CSV (hall,rows,cols)")
    p.add_argument(
        "--hall",
        action="append",
        default=[],
        help="hall spec NAE:ROWSxCOLS (repeatable), e.g. A:5x6",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="also prompt for extra students/halls after loading files",
    )
    p.add_argument(
        "-a",
        "--adjacency",
        choices=ADJ_MODES,
        default="side",
        help="adjacent = side (left/right, default), grid (+front/back), "
        "all8 (+diagonals)",
    )
    p.add_argument("-o", "--output", help="write alloction to this CSV file")
    p.add_argument(
        "--shuffle", action="store_true", help="randomise for fairer seating"
    )
    p.add_argument("--seed", type=int, help="random seed (implies --shuffle)")
    args = p.parse_args()

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
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"Error: {e}")

    if not halls or not students:
        sys.exit("Error: need at least one hall and one student.")
    names = [h[0] for h in halls]
    if len(set(names)) != len(names):
        sys.exit("Error: hall names must be unique.")
    ids = [s["id"] for s in students]
    dupes = {x for x in ids if ids.count(x) > 1}
    if dupes:
        sys.exit(f"Error: duplicate student IDs: {sorted(dupes)}")
    capacity = sum(r * c for _, r, c in halls)
    if len(students) > capacity:
        sys.exit(f"Error: {len(students)} students but only {capacity} seats.")

    rng = random.Random(args.seed) if (args.shuffle or args.seed is not None) else None
    print(
        f"\nStudents: {len(students)} | Seats: {capacity} | "
        f"Sections: {len({s['section'] for s in students})} | "
        f"Adjacency: {args.adjacency}"
    )

    placed = distribute(students, halls, rng)
    layouts = {}
    t0 = time.perf_counter()
    for name, rows, cols in halls:
        layout = solve_hall(placed[name], rows, cols, args.adjacency, rng)
        if layout is None:
            print(
                f"\nNo conflict-free arrangement exists for hall {name} "
                f"({len(placed[name])} students, {rows * cols} seats)."
            )
            print(
                "Try: adding seats/halls, using --adjacency side, or splitting "
                "large sections."
            )
            sys.exit(1)
        layouts[name] = layout
    elapsed = time.perf_counter() - t0

    show_results(halls, layouts, args.adjacency, args.output)
    print(
        f"\nSolved {len(halls)} hall CSP(s) with python-constraint in "
        f"{elapsed * 1000:.1f} ms, seat utilisation {len(students) / capacity:.0%}"
    )


if __name__ == "__main__":
    main()
