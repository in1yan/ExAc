import argparse
import random
import re
import sys
import time

import pandas as pd
from constraint import AllDifferentConstraint, Problem

ADJ_MODES = {
    "side": [(0, -1), (0, 1)],  # left / right
    "grid": [(0, -1), (0, 1), (-1, 0), (1, 0)],  # + front / back
    "all8": [
        (dr, dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)  # + diagonals
        if (dr, dc) != (0, 0)
    ],
}


# ----------------------------------------------------------------------------
# Input handling
# ----------------------------------------------------------------------------
def row_label(r):
    """0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA"""
    r += 1
    s = ""
    while r:
        r, rem = divmod(r - 1, 26)
        s = chr(65 + rem) + s
    return s


def parse_hall_spec(spec):
    """'A:5x6' or '5x6' -> (name, rows, cols)"""
    m = re.fullmatch(r"(?:(\w+)\s*:)?\s*(\d+)\s*[xX*]\s*(\d+)", spec.strip())
    if not m:
        raise ValueError(f"Bad hall spec '{spec}'. Use NAME:ROWSxCOLS, e.g. A:5x6")
    return m.group(1), int(m.group(2)), int(m.group(3))


def load_students_csv(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip().lower() for c in df.columns]

    def pick(names):
        return next((c for c in names if c in df.columns), None)

    id_col = pick(
        ["id", "student_id", "roll", "roll_no", "rollno", "reg_no", "student"]
    )
    sec_col = pick(["section", "class", "sec", "group"])
    name_col = pick(["name", "student_name"])
    if id_col is None or sec_col is None:
        raise ValueError(
            f"{path}: need an id column (id/roll/roll_no) and a section column "
            f"(section/class). Found: {list(df.columns)}"
        )
    students = []
    for _, row in df.iterrows():
        sid, sec = row[id_col].strip(), row[sec_col].strip()
        if sid and sec:
            students.append(
                {
                    "id": sid,
                    "section": sec,
                    "name": row[name_col].strip() if name_col else "",
                }
            )
    return students


def load_halls_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    for col in ("hall", "rows", "cols"):
        if col not in df.columns:
            raise ValueError(f"{path}: halls CSV needs columns hall,rows,cols")
    return [(str(r.hall).strip(), int(r.rows), int(r.cols)) for r in df.itertuples()]


def prompt_halls():
    print("\n--- Exam halls ---")
    print("Enter one hall per line as: NAME ROWS COLS   (e.g. A 5 6)")
    print("Press Enter on an empty line when done.")
    halls = []
    while True:
        try:
            line = input(f"hall {len(halls) + 1}> ").strip()
        except EOFError:
            break
        if not line:
            break
        parts = line.split()
        if len(parts) != 3 or not (parts[1].isdigit() and parts[2].isdigit()):
            print("  Format: NAME ROWS COLS (e.g. A 5 6)")
            continue
        halls.append((parts[0], int(parts[1]), int(parts[2])))
    return halls


def prompt_students():
    print("\n--- Students ---")
    print("Enter one student per line as: ID SECTION [NAME]   (e.g. S1 CSE-A Ravi)")
    print("Press Enter on an empty line when done.")
    students = []
    while True:
        try:
            line = input(f"student {len(students) + 1}> ").strip()
        except EOFError:
            break
        if not line:
            break
        parts = line.split(None, 2)
        if len(parts) < 2:
            print("  Format: ID SECTION [NAME]")
            continue
        students.append(
            {
                "id": parts[0],
                "section": parts[1],
                "name": parts[2] if len(parts) > 2 else "",
            }
        )
    return students


# ----------------------------------------------------------------------------
# CSP model
# ----------------------------------------------------------------------------
def distribute(students, halls, rng=None):
    """Deal students to halls so every section is spread proportionally to capacity."""
    cap = {name: rows * cols for name, rows, cols in halls}
    free = dict(cap)
    order = list(students)
    if rng:
        rng.shuffle(order)
    order.sort(key=lambda s: s["section"])  # stable: groups sections together
    placed = {name: [] for name in cap}
    for st in order:
        target = max(free, key=lambda h: (free[h] / cap[h], free[h]))
        placed[target].append(st)
        free[target] -= 1
    return placed


def seat_pairs(rows, cols, mode):
    """Unique adjacent seat pairs ((r1,c1),(r2,c2)) in a rows x cols hall."""
    pairs = set()
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ADJ_MODES[mode]:
                r2, c2 = r + dr, c + dc
                if 0 <= r2 < rows and 0 <= c2 < cols:
                    pairs.add(tuple(sorted([(r, c), (r2, c2)])))
    return pairs


def solve_hall(hall_students, rows, cols, mode, rng=None):
    """Build and solve the CSP for one hall. Returns {(r,c): student or None} or None."""
    seats = [(r, c) for r in range(rows) for c in range(cols)]
    name_of = {rc: f"{row_label(rc[0])}{rc[1] + 1}" for rc in seats}

    # Domain values are indices into `people`. Empty seats are modelled as
    # placeholder "students" that each have a unique section, so they never conflict.
    people = list(hall_students)
    section_id = {}
    sec = []
    for st in people:
        sec.append(section_id.setdefault(st["section"], len(section_id)))
    for k in range(len(seats) - len(people)):
        people.append(None)
        sec.append(-(k + 1))

    # python-constraint tries values from the end of the domain list, so reverse
    # it to try students in input order (or shuffle for random seating).
    domain = list(range(len(people)))[::-1]
    if rng:
        rng.shuffle(domain)

    problem = Problem()  # BacktrackingSolver + forward checking
    problem.addVariables(list(name_of.values()), domain)
    problem.addConstraint(AllDifferentConstraint(), list(name_of.values()))
    for a, b in seat_pairs(rows, cols, mode):
        problem.addConstraint(lambda x, y: sec[x] != sec[y], (name_of[a], name_of[b]))

    solution = problem.getSolution()
    if solution is None:
        return None
    return {rc: people[solution[name_of[rc]]] for rc in seats}


def count_violations(layout, rows, cols, mode):
    bad = 0
    for a, b in seat_pairs(rows, cols, mode):
        sa, sb = layout.get(a), layout.get(b)
        if sa and sb and sa["section"] == sb["section"]:
            bad += 1
    return bad


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
def show_results(halls, layouts, mode, out_path):
    multi = len(halls) > 1
    print("\n=== Seating Allocation ===")
    records, total_bad = [], 0
    for name, rows, cols in halls:
        layout = layouts[name]
        for r in range(rows):
            for c in range(cols):
                st = layout[(r, c)]
                if st:
                    label = f"{row_label(r)}{c + 1}"
                    print(f"{name + '-' if multi else ''}{label} -> {st['id']}")
                    records.append(
                        {
                            "hall": name,
                            "seat": label,
                            "student_id": st["id"],
                            "name": st["name"],
                            "section": st["section"],
                        }
                    )

    for name, rows, cols in halls:
        print(f"\n=== Hall {name} ({rows} x {cols}) ===")
        grid = [
            [
                f"{layouts[name][(r, c)]['id']} ({layouts[name][(r, c)]['section']})"
                if layouts[name][(r, c)]
                else "-"
                for c in range(cols)
            ]
            for r in range(rows)
        ]
        print(
            pd.DataFrame(
                grid,
                index=[row_label(r) for r in range(rows)],
                columns=range(1, cols + 1),
            ).to_string()
        )
        total_bad += count_violations(layouts[name], rows, cols, mode)

    print(f"\nConstraint Violations: {total_bad}")
    if out_path:
        pd.DataFrame(records).to_csv(out_path, index=False)
        print(f"Saved allocation to {out_path}")
