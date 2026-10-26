"""Reorder a plan-set PDF by the SHEET NO. in the title block, reading every page (never assume a pattern).
Usage: python3 reorder_by_sheet.py in.pdf out.pdf"""
import sys
import pymupdf
from common import page_count, sheet_info

src, dst = sys.argv[1], sys.argv[2]
info = {p: sheet_info(src, p) for p in range(1, page_count(src) + 1)}
missing = [p for p, (_, n) in info.items() if n is None]
if missing:
    sys.exit(f"Could not read SHEET NO. on pages {missing}: render those title blocks with render_check.py")
order = sorted(info, key=lambda p: info[p][1])
out = pymupdf.open()
out.insert_pdf(pymupdf.open(src))  # copy, then reorder in place
out.select([p - 1 for p in order])
out.save(dst, garbage=3, deflate=True)
nums = [info[p][1] for p in order]
gaps = [(a, b) for a, b in zip(nums, nums[1:]) if b - a > 1]
dups = sorted({n for n in nums if nums.count(n) > 1})
for p in order:
    print(f"orig p{p:>3}  {info[p][0] or '?':<10} sheet {info[p][1]}")
print("Gaps in sheet numbers:", gaps or "none")
print("Duplicate sheet numbers:", dups or "none")
