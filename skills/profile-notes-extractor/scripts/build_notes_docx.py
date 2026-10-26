"""Write notes.json to a Word doc: notes stacked in station order, a blank line between notes, NO bold anywhere.
Usage: python3 build_notes_docx.py notes.json out.docx "Title"
Format matches reference/us51-profile-notes-example.docx: Arial 10 pt, 1" margins, 0 pt spacing,
Heading 1 title (not bold), one paragraph per note line."""
import json, sys
from docx import Document
from docx.shared import Pt, Inches

notes = json.load(open(sys.argv[1]))
d = Document()
normal = d.styles["Normal"]
normal.font.name = "Arial"
normal.font.size = Pt(10)
normal.font.bold = False
normal.paragraph_format.space_after = Pt(0)
for s in d.sections:
    s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(1)
d.styles["Heading 1"].font.bold = False  # Word's Heading 1 is bold by default
title = d.add_heading(sys.argv[3], 1)
for r in title.runs:
    r.bold = False
for i, n in enumerate(notes):
    for t in n["lines"]:
        d.add_paragraph().add_run(t).bold = False
    if i < len(notes) - 1:
        d.add_paragraph()
d.save(sys.argv[2])
bold = sum(1 for p in Document(sys.argv[2]).paragraphs for r in p.runs if r.bold)
print(f"{len(notes)} notes -> {sys.argv[2]} (bold runs: {bold})")
