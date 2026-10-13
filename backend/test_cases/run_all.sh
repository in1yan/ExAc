#!/bin/bash
# Runs all 12 test cases. Case 12 is expected to fail (no valid arrangement).
cd "$(dirname "$0")"
echo "===== CASE 1 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case1_students.csv --halls case1_halls.csv -a side
echo
echo "===== CASE 2 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case2_students.csv --halls case2_halls.csv -a side
echo
echo "===== CASE 3 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case3_students.csv --halls case3_halls.csv -a side
echo
echo "===== CASE 4 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case4_students.csv --halls case4_halls.csv -a side
echo
echo "===== CASE 5 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case5_students.csv --halls case5_halls.csv -a side
echo
echo "===== CASE 6 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case6_students.csv --halls case6_halls.csv -a side
echo
echo "===== CASE 7 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case7_students.csv --halls case7_halls.csv -a side
echo
echo "===== CASE 8 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case8_students.csv --halls case8_halls.csv -a side
echo
echo "===== CASE 9 (adjacency: grid) ====="
python ../seating_allocator_pc.py -s case9_students.csv --halls case9_halls.csv -a grid
echo
echo "===== CASE 10 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case10_students.csv --halls case10_halls.csv -a side
echo
echo "===== CASE 11 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case11_students.csv --halls case11_halls.csv -a side
echo
echo "===== CASE 12 (adjacency: side) ====="
python ../seating_allocator_pc.py -s case12_students.csv --halls case12_halls.csv -a side
echo
