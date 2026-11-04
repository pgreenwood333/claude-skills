"""Generate the VBA macro (PlaceXSNotes.bas), batch command files and run guide for one job.

  make_macro.py <work_dir>            reads <work_dir>/notes_to_add.json and <work_dir>/macro_settings.json

Writes into <work_dir>: PlaceXSNotes.bas (Windows-1252, CRLF: what the VBA editor's File > Import expects),
xsnotes_batch_DRYRUN.txt, xsnotes_batch_PLACE.txt and HOW_TO_RUN.md.
Refuses (exit 2, STOP:) when a note still needs a decision or has no side, or a setting is missing.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit("usage: make_macro.py <work_dir>")
WORK = Path(sys.argv[1])
notes = json.load(open(WORK / "notes_to_add.json"))
settings = json.load(open(WORK / "macro_settings.json"))


def stop(msg, fix):
    print(f"STOP: {msg}\nFIX: {fix}")
    sys.exit(2)


REQUIRED = {
    "job": "job number, e.g. 123456",
    "vba_project": "VBA project name the user imports into (their own, never a shared office project)",
    "group_prefix": "drawing model name prefix, e.g. 'MLUS51 - ' (named boundary group + ' - ')",
    "note_text.level": "level for the notes",
    "note_text.text_style": "text style for the notes",
    "note_text.weight": "line weight",
    "note_text.color": "color number (e.g. 15) or \"ByLevel\"",
    "grid.left_offset": "section left offset (ft)", "grid.right_offset": "section right offset (ft)",
    "placement.edge_gap": "ft in from the grid's left edge (LT notes) or right edge (RT notes)",
    "placement.top_gap": "ft below the top grid line", "placement.side_gap": "ft between side-by-side notes",
    "text_size.drawing_scale_ft_per_in": "drawing scale of the section models, ft per inch (1\"=10' -> 10)",
}

# Standard note size (engineer, 2026-11-04: "it's going to be the same every time").
# Measured on job 123456: the 8-line note "354 A" (text style _Gen_Notes, level XS_P_DRAINAGE,
# sized by OpenRoads itself) is 15.001 ft tall in a 1"=10' cross-section drawing model.
# The macro rebuilds these exact lines from the text style and scales to match, so every file
# gets the same size with no note to copy and no run order. Other drawing scales scale linearly.
STANDARD_SIZE = {
    "height": 15.001, "scale_ft_per_in": 10,
    "lines": ["354 A", "STA. 354+30.00", "SS-3 REQ'D LT", "TOP = 346.08'", "INV. = 343.00'",
              "H = 3.79'", "OPENINGS: 1 @ 18\"", "68' - 18\" RCP REQ'D."],
    "from": "DOT standard note size (_Gen_Notes, measured on job 123456)",
}
for key, what in REQUIRED.items():
    node = settings
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            stop(f"macro_settings.json is missing {key} ({what})", "ask the user and fill it in")
        node = node[part]

bad = [n["id"] for n in notes if n.get("status") in (None, "NEEDS DECISION")]
if bad:
    stop(f"{len(bad)} notes still need a decision (nearest section / cut new / skip): {', '.join(bad)}",
         "ask the user, record answers in decisions.json, re-run match_sections.py")
noside = [n["id"] for n in notes if n.get("status") != "SKIP" and n.get("side") not in ("LT", "RT")]
if noside:
    stop(f"{len(noside)} notes have no LT/RT side: {', '.join(noside)}", "ask the user which side each structure is on")
notes = [n for n in notes if n["status"] != "SKIP"]
if not notes:
    stop("no notes to place", "check notes_to_add.json")
G, P, TS = settings["grid"], settings["placement"], settings["text_size"]
GROUP = settings["group_prefix"]
PROJ = settings["vba_project"]
JOB = settings["job"]

# text size: the built-in standard unless the settings give another reference or turn it off
std = dict(STANDARD_SIZE, **(TS.get("standard") or {}))
if TS.get("use_standard", True):
    STD_H = std["height"] * float(TS["drawing_scale_ft_per_in"]) / float(std["scale_ft_per_in"])
    STD_LINES = std["lines"]
else:
    STD_H, STD_LINES = 0, []
SCRATCH = float(TS.get("scratch_height", 0) or 0)
# Engineer, 2026-11-04: every note must be the text style itself (_Gen_Notes at its own 0.01 size),
# never a copy of a nearby note (which can carry another style or a size override).
COPY_EXISTING = bool(TS.get("copy_existing", False))
# Build each note while its section model is active, so the style's annotation scale is that model's
# and the text needs no scaling (the style's own size, no override). Checked against the standard note.
STYLE_SIZE = bool(TS.get("style_size_in_section", True))
if not STD_H and not SCRATCH:
    print("note: no standard size and no scratch height - files without a note to copy will need a reference "
          "note from an earlier file (_xsnotes_textsize.txt)")
COLOR = settings["note_text"]["color"]
if isinstance(COLOR, str) and COLOR.strip().lower() == "bylevel":
    COLOR_VB = -1
elif isinstance(COLOR, int) or (isinstance(COLOR, str) and COLOR.strip().isdigit()):
    COLOR_VB = int(COLOR)
    if not 0 <= COLOR_VB <= 255:
        stop(f"note_text.color {COLOR} is out of range", "use a color number 0-255 or \"ByLevel\"")
else:
    stop(f"note_text.color {COLOR!r} is not a color number or ByLevel", "ask the user (Change Attributes shows it)")


def sta_ft(label):
    """'440+50.00 LT.' or '471+50.0000' -> 44050.0"""
    s = label.split(" ")[0]
    a, b = s.split("+")
    return int(a) * 100 + float(b)


def vb_str(s):
    """VBA string expression; degree sign via ChrW so the file stays plain ASCII."""
    parts = s.replace('"', '""').split("\u00b0")
    return ' & ChrW(176) & '.join(f'"{p}"' for p in parts)


def target_sta(n):
    return sta_ft(n["new_section_sta"]) if n["status"] == "CUT" else sta_ft(n["dgn_section"])


rows = []
for n in sorted(notes, key=lambda n: (target_sta(n), n["side"], n["id"])):
    body = [f'    t = {vb_str(n["lines"][0])}'] + [f'    t = t & vbLf & {vb_str(l)}' for l in n["lines"][1:]]
    rows.append("\n".join(body) + f'\n    AddNote "{n["id"]}", {target_sta(n):.4f}, "{n["side"]}", t')

nt = settings["note_text"]
STD_ADD = "\n".join(f"    mProbeLines.Add {vb_str(l)}" for l in STD_LINES) or "    ' (no standard)"
bas = f'''Attribute VB_Name = "PlaceXSNotes"
' ============================================================================
' Job {JOB} - place missing cross-section notes
' Generated by make_macro.py from notes_to_add.json. Do not hand-edit the note
' list below; change the JSON and regenerate.
'
' WHAT IT DOES
'   For each note whose cross-section drawing model ("{GROUP}<station>") exists
'   in the OPEN file, it places the note as one text node tucked into the top-left
'   corner of the section grid (structure LT, left-aligned) or the top-right corner
'   (structure RT, right edge on the grid edge).
'   A second note in the same corner goes beside the first, toward the centerline.
'   Text: built from text style {nt["text_style"]} at the style's own size, with
'   each section model made active while its note is built (so the drawing's
'   annotation scale applies, nothing is rescaled), and checked against the
'   standard note size before anything is placed. Existing notes are never copied.
'   Level {nt["level"]} (brought in from the level library if the file lacks it),
'   color {COLOR}, weight {nt["weight"]}. The dry run checks the level and color took.
'
' WHAT IT NEVER DOES
'   - It does not create, cut or change cross sections / named boundaries.
'   - It does not touch sheet models, the 3D model, or any reference file.
'   - It does not edit or delete existing elements (RemovePlacedNotes only
'     deletes the notes THIS macro placed, read from its own log file).
'
' HOW TO RUN (once per XS file)
'   1. Save a backup copy of the XS file first.
'   2. Open the XS file in OpenRoads Designer.
'   3. Run DryRun   -> writes a report, places nothing. Read it.
'   4. Run PlaceNotes -> places the notes, writes the same report + a log.
'   5. To undo everything this macro placed in this file: RemovePlacedNotes.
'   Report/log are written next to the DGN: <dgn name>_xsnotes_report.txt / _log.txt
'
' If anything unexpected happens it STOPS and tells you why (it never skips silently).
' ============================================================================
Option Explicit

Private Const GROUP_PREFIX As String = "{GROUP}"
Private Const NOTE_LEVEL As String = "{nt["level"]}"
Private Const NOTE_STYLE As String = "{nt["text_style"]}"
Private Const NOTE_WEIGHT As Long = {nt["weight"]}
Private Const NOTE_COLOR As Long = {COLOR_VB}          ' color number; -1 = ByLevel (left as is)
Private Const GRID_LEFT As Double = {G["left_offset"]}      ' section left offset (ft)
Private Const GRID_RIGHT As Double = {G["right_offset"]}      ' section right offset (ft)
Private Const EDGE_GAP As Double = {P["edge_gap"]}          ' ft in from the grid's left edge (LT) / right edge (RT)
Private Const TOP_GAP As Double = {P["top_gap"]}           ' ft below the top grid line
Private Const SIDE_GAP As Double = {P["side_gap"]}          ' ft between two notes side by side in one corner
' Standard note size: the note in LoadStandard, built from the text style, is STD_HEIGHT tall
' in a section drawing model. 0 = no standard (use a saved reference note or SCRATCH_HEIGHT).
Private Const STD_HEIGHT As Double = {STD_H:.4f}
' From-scratch sizing (only when there is no standard): drawn height of one capital-letter line.
Private Const SCRATCH_HEIGHT As Double = {SCRATCH}
Private Const STA_TOL As Double = 0.01         ' ft, model station match tolerance
Private Const COPY_EXISTING As Boolean = {COPY_EXISTING}   ' copy an existing note's settings (off: always the style)
Private Const STYLE_SIZE As Boolean = {STYLE_SIZE}      ' build in the section model at the style's own size
Private Const SIZE_TOL As Double = 0.03         ' allowed difference from the standard note size (3%)

Private mDry As Boolean
Private mQuiet As Boolean   ' batch mode: no dialogs, everything goes to the report
Private mReport As String
Private mLog As String
Private mTemplate As Element
Private mTemplateDiag As String
Private mStyle As TextStyle          ' used when there is no note to copy
Private mPlacedBoxes As Collection  ' boxes of notes placed this run: Array(model, left, bottom, right, top)
Private mLastK As Double             ' drawing units per ft, from the last section with offset labels
Private mScale As Double             ' size factor for notes built from the style
Private mProbeH As Double            ' drawn height of the saved reference note
Private mProbeLines As Collection    ' its text lines
Private mProbeFrom As String         ' file it came from
Private mOldStyle As TextStyle
Private mOldLevel As Level
Private mLevelImported As Boolean
Private mLastModel As String         ' last model name read while searching the model list
Private mStage As String            ' what the macro was doing, reported if an error stops it
Private mLevel As Level
Private mHome As ModelReference      ' model active when the macro started (made active again at the end)
Private mSizeInfo As String          ' first size check, for the report header
Private mPlaced As Long, mSkipped As Long, mMissing As Long

' ---------------------------------------------------------------- entry points
Public Sub DryRun()
    mQuiet = False: RunAll True
End Sub

' For MicroStation Batch Process (no dialogs). Key-in: vba run [{PROJ}]PlaceXSNotes.DryRunBatch
Public Sub DryRunBatch()
    If Not IsDefaultModel() Then Exit Sub
    mQuiet = True: RunAll True
End Sub

' For MicroStation Batch Process (no dialogs). Key-in: vba run [{PROJ}]PlaceXSNotes.PlaceNotesBatch
Public Sub PlaceNotesBatch()
    If Not IsDefaultModel() Then Exit Sub
    mQuiet = True: RunAll False
End Sub

' Batch Process may run the command file once per model. The macro handles the whole
' file in one pass, so the batch subs only do work on the file's default model and
' return immediately on every other model.
Private Function IsDefaultModel() As Boolean
    IsDefaultModel = (ActiveModelReference.Name = ActiveDesignFile.DefaultModelReference.Name)
End Function

Public Sub PlaceNotes()
    If MsgBox("Place the missing cross-section notes in this file?" & vbLf & vbLf & _
              "Make sure you saved a backup copy first." & vbLf & _
              "Tip: run DryRun first and read its report.", vbOKCancel + vbQuestion, "Place XS notes") <> vbOK Then Exit Sub
    mQuiet = False: RunAll False
End Sub

Public Sub RemovePlacedNotes()
    If Dir(OutPath("_log.txt")) = "" Then MsgBox "No log found at:" & vbLf & OutPath("_log.txt") & vbLf & "Nothing was removed.", vbExclamation: Exit Sub
    If MsgBox("Delete every note this macro placed in this file (from " & OutPath("_log.txt") & ")?", vbOKCancel + vbExclamation) <> vbOK Then Exit Sub
    MsgBox DoRemove(), vbInformation, "Place XS notes"
End Sub

' For MicroStation Batch Process (no dialogs). Key-in: vba run [{PROJ}]PlaceXSNotes.RemovePlacedNotesBatch
' Removes only the notes listed in this file's _xsnotes_log.txt; the result goes to _xsnotes_SUMMARY.txt.
Public Sub RemovePlacedNotesBatch()
    If Not IsDefaultModel() Then Exit Sub
    mQuiet = True
    If Dir(OutPath("_log.txt")) = "" Then
        WriteFile BatchSummaryPath(), Format(Now, "yyyy-mm-dd hh:nn") & vbTab & ActiveDesignFile.Name & vbTab & "REMOVE" & vbTab & _
            "no log file, nothing removed (" & OutPath("_log.txt") & ")" & vbCrLf, True
        Exit Sub
    End If
    Dim res As String: res = DoRemove()
    WriteFile BatchSummaryPath(), Format(Now, "yyyy-mm-dd hh:nn") & vbTab & ActiveDesignFile.Name & vbTab & "REMOVE" & vbTab & _
        Replace(Replace(res, vbCr, ""), vbLf, " ") & vbCrLf, True
End Sub

' Deletes the elements listed in the log (and nothing else), then renames the log so it can't run twice.
Private Function DoRemove() As String
    Dim logPath As String, f As Integer, body As String, ln As Variant, parts() As String
    Dim m As ModelReference, el As Element, n As Long, bad As String, total As Long
    logPath = OutPath("_log.txt")
    ' the log is written with LF line ends; Line Input only splits on CR, so read it whole and split on LF
    f = FreeFile: Open logPath For Binary Access Read As #f
    body = Space$(LOF(f)): Get #f, , body
    Close #f
    For Each ln In Split(Replace(body, vbCr, ""), vbLf)
        parts = Split(CStr(ln), vbTab)
        If UBound(parts) >= 2 Then
            total = total + 1
            Set m = FindModelByName(parts(1))
            If m Is Nothing Then
                bad = bad & parts(0) & ": model " & parts(1) & " not found" & vbLf
            Else
                Set el = Nothing
                On Error Resume Next
                Set el = m.GetElementByID(DLongFromString(Trim$(parts(2))))
                On Error GoTo 0
                If el Is Nothing Then
                    bad = bad & parts(0) & ": element " & parts(2) & " not found" & vbLf
                Else
                    m.RemoveElement el: n = n + 1
                End If
            End If
        End If
    Next
    ' only retire the log when every listed note was removed, so a failed run can be fixed and re-run
    If n = total And total > 0 Then Name logPath As logPath & ".removed-" & Format(Now, "yyyymmdd-hhnnss")
    DoRemove = n & " of " & total & " placed notes removed." & IIf(bad <> "", vbLf & "Not removed (log kept):" & vbLf & bad, "")
End Function

' ---------------------------------------------------------------- main
Private Sub RunAll(dry As Boolean)
    mDry = dry: mReport = "": mLog = "": mPlaced = 0: mSkipped = 0: mMissing = 0: mTemplateDiag = "": mStage = "starting": mLastModel = "": mLastK = 0: Set mPlacedBoxes = New Collection
    Rpt "Run: " & Format(Now, "yyyy-mm-dd hh:nn:ss") & IIf(mQuiet, "  (batch)", "")
    Set mLevel = FindOrImportLevel()
    If mLevel Is Nothing Then Fail "Level " & NOTE_LEVEL & " is not in this file and could not be brought in from the level library." & vbLf & _
        "Fix: open the XS file with the DOT workspace loaded, or create the level, then run again.": Exit Sub
    Set mHome = ActiveModelReference: mSizeInfo = ""
    If COPY_EXISTING Then Set mTemplate = FindTemplateNote() Else Set mTemplate = Nothing
    Set mStyle = Nothing: Set mOldStyle = Nothing: mScale = 1
    Rpt "File: " & ActiveDesignFile.FullName
    Rpt "Mode: " & IIf(dry, "DRY RUN (nothing placed)", "PLACE")
    If Not mTemplate Is Nothing Then
        ' copy an existing note, and save it as the size reference for files that have none
        Rpt "Text: copied from " & TemplateLabel() & " in model " & mTemplate.ModelReference.Name
        SaveProbe mTemplate
    Else
        ' no note to copy: build from the text style by name, scaled to match the saved reference note
        Set mStyle = ActiveDesignFile.TextStyles.Find(NOTE_STYLE)
        If mStyle Is Nothing Then Fail "Text style " & NOTE_STYLE & " is not available in this file." & vbLf & _
            "Fix: open the XS file with the DOT workspace loaded." & vbLf & vbLf & mTemplateDiag: Exit Sub
        If LoadStandard() Then
            ' standard note size: same size in every file, no run order
        ElseIf Not LoadProbe() And SCRATCH_HEIGHT <= 0 Then
            Fail "No existing note in this file to copy, no standard size, no saved reference note, and no from-scratch text height set." & vbLf & _
            "Fix: run the macro first on an XS file that has notes (it saves a reference note to " & SizeFilePath() & _
            "), or place one note by hand on any section here, or set the from-scratch text height." & vbLf & vbLf & mTemplateDiag: Exit Sub
        End If
    End If

    On Error GoTo EH
    If Not mStyle Is Nothing Then
        mStage = "setting the active text style to " & NOTE_STYLE
        SetActiveStyle
        If STYLE_SIZE Then
            mScale = 1
            Rpt "Text: built from style " & NOTE_STYLE & " at its own size in each section model" & _
                IIf(mProbeH > 0, " (checked against " & mProbeFrom & ")", " (no size check: no standard set)")
        ElseIf mProbeH > 0 Then
            mStage = "measuring the text size against the reference note"
            mScale = ProbeScale()
            Rpt "Text: built from style " & NOTE_STYLE & ", scaled x" & Format(mScale, "0.0000") & _
                " to match note '" & mProbeLines(1) & "' from " & mProbeFrom
        Else
            mStage = "sizing the text from scratch"
            mScale = ScratchScale()
            Rpt "Text: built from style " & NOTE_STYLE & ", scaled x" & Format(mScale, "0.0000") & _
                " so a capital-letter line is " & SCRATCH_HEIGHT & " tall (FROM SCRATCH - check the first note's text height before batching)"
        End If
        If mScale < 0.01 Or mScale > 100 Then Err.Raise vbObjectError + 6, , "text size factor " & mScale & " looks wrong; not placing anything."
    End If
    Rpt String(70, "-")
    Notes
    GoHome
    RestoreStyle
    RestoreLevel
    On Error GoTo 0

    Rpt String(70, "-")
    Rpt "Placed: " & mPlaced & "   Already on section (skipped): " & mSkipped & "   Section model not in this file: " & mMissing
    WriteFile OutPath("_report.txt"), mReport, False
    If Not dry And mLog <> "" Then WriteFile OutPath("_log.txt"), mLog, True
    WriteFile BatchSummaryPath(), Format(Now, "yyyy-mm-dd hh:nn") & vbTab & ActiveDesignFile.Name & vbTab & IIf(dry, "DRYRUN", "PLACE") & vbTab & _
        "placed " & mPlaced & ", skipped " & mSkipped & ", not in file " & mMissing & vbCrLf, True
    If mQuiet Then Exit Sub
    MsgBox IIf(dry, "DRY RUN - nothing placed." & vbLf & vbLf, "") & _
           "Placed: " & mPlaced & vbLf & "Already present (skipped): " & mSkipped & vbLf & _
           "Section not in this file: " & mMissing & vbLf & vbLf & "Report: " & OutPath("_report.txt"), vbInformation, "Place XS notes"
    Exit Sub
EH:
    Dim msg As String: msg = "Error " & Err.Number & ": " & Err.Description
    GoHome
    RestoreStyle
    RestoreLevel
    If Not dry And mLog <> "" Then WriteFile OutPath("_log.txt"), mLog, True
    Fail "Stopped while placing notes." & vbLf & msg & vbLf & "Step: " & mStage & vbLf & "Last model read: " & mLastModel & vbLf & vbLf & _
         "Notes placed before the stop are listed in the log; run RemovePlacedNotes to take them out." & vbLf & _
         "Report: " & OutPath("_report.txt")
End Sub

' ---------------------------------------------------------------- one note
Private Sub AddNote(id As String, secSta As Double, side As String, text As String)
    Dim m As ModelReference, lines() As String
    lines = Split(text, vbLf)
    mStage = id & ": finding section " & StaLabel(secSta)
    Set m = FindSectionModel(secSta)
    If m Is Nothing Then
        mMissing = mMissing + 1
        Rpt id & "  " & lines(0) & "  -> section " & StaLabel(secSta) & " not in this file (OK if it belongs to another XS file; if it is a new section, cut it first)"
        Exit Sub
    End If
    mStage = id & ": checking " & m.Name & " for an existing copy"
    If NoteAlreadyThere(m, lines) Then
        mSkipped = mSkipped + 1
        Rpt id & "  " & lines(0) & "  -> already on " & m.Name & ", skipped"
        Exit Sub
    End If

    Dim gridL As Double, gridR As Double, yTop As Double, k As Double, msg As String, gridInfo As String
    mStage = id & ": reading the grid in " & m.Name
    If Not GridFrame(m, gridL, gridR, yTop, k, gridInfo, msg) Then
        Err.Raise vbObjectError + 1, , id & ": can't locate the section grid in " & m.Name & " (" & msg & ")." & _
            " Fix: check the section has its grid/annotation, or place this note by hand."
    End If
    ' build at the grid's top-left; it is moved into its corner once its size is known
    Dim xLeft As Double: xLeft = gridL

    Dim tn As TextNodeElement, i As Long
    If STYLE_SIZE And mTemplate Is Nothing Then
        mStage = id & ": opening " & m.Name & " to build the note at the style's size"
        If ActiveModelReference.Name <> m.Name Then m.Activate
        CheckStyleSize m, id
    End If
    ' build the note (active text style, or the copied note's settings)
    mStage = id & ": building the text for " & m.Name
    Set tn = CreateTextNodeElement1(mTemplate, Point3dFromXYZ(xLeft, yTop, 0), Matrix3dIdentity)   ' mTemplate Nothing = active settings (style set in RunAll)
    If tn.TextLinesCount <> 0 Then Err.Raise vbObjectError + 3, , id & ": the copied text template was not empty - stopping so no text is duplicated."
    For i = 0 To UBound(lines): tn.AddTextLine lines(i): Next
    Dim sizeNote As String
    If mTemplate Is Nothing And Not STYLE_SIZE Then
        tn.ScaleAll Point3dFromXYZ(xLeft, yTop, 0), mScale, mScale, 1#
        sizeNote = " [built from style, scaled x" & Format(mScale, "0.0000") & "]"
    End If
    mStage = id & ": setting level/color/weight"
    SetSymbology tn
    CheckSymbology tn, id

    ' tuck it into the corner: LT = left edge EDGE_GAP in from the grid's left edge,
    ' RT = right edge EDGE_GAP in from the grid's right edge; top TOP_GAP under the top grid line
    Dim top As Double, r As Range3d, h As Double, w As Double
    mStage = id & ": finding free space in the corner of " & m.Name
    r = tn.Range: h = r.High.Y - r.Low.Y: w = r.High.X - r.Low.X
    If side = "LT" Then xLeft = gridL + EDGE_GAP * k Else xLeft = gridR - EDGE_GAP * k - w
    top = yTop - TOP_GAP * k
    Dim xStart As Double: xStart = xLeft
    xLeft = BesideNotesInCorner(m, side, xLeft, w, top, h, k)
    tn.Move Point3dFromXYZ(xLeft - r.Low.X, top - r.High.Y, 0)
    ' remember this note's box so a second note in this corner (same run, dry or real) goes beside it
    mPlacedBoxes.Add Array(m.Name, xLeft, top - h, xLeft + w, top)
    Dim placeInfo As String
    If Abs(xLeft - xStart) > 0.01 Then placeInfo = " (beside the other note in this corner)"
    If side = "LT" And xLeft + w > (gridL + gridR) / 2 Then placeInfo = placeInfo & " [CHECK: runs past the centerline]"
    If side = "RT" And xLeft < (gridL + gridR) / 2 Then placeInfo = placeInfo & " [CHECK: runs past the centerline]"

    If mDry Then
        Rpt id & "  " & lines(0) & "  -> would place on " & m.Name & " " & side & " corner" & placeInfo & gridInfo & sizeNote
    Else
        mStage = id & ": adding the note to " & m.Name
        m.AddElement tn
        mPlaced = mPlaced + 1
        mLog = mLog & id & vbTab & m.Name & vbTab & DLongToString(tn.ID) & vbLf
        Rpt id & "  " & lines(0) & "  -> placed on " & m.Name & " " & side & " corner" & placeInfo & gridInfo & sizeNote
    End If
End Sub

' ---------------------------------------------------------------- helpers

Private Function FindModelByName(nm As String) As ModelReference
    Dim m As ModelReference
    For Each m In ActiveDesignFile.Models
        If m.Name = nm Then Set FindModelByName = m: Exit Function
    Next
End Function

' Drawing model named GROUP_PREFIX & "471+91.4300" (not the "[Sheet]" model) at this station.
Private Function FindSectionModel(sta As Double) As ModelReference
    Dim m As ModelReference, s As String, v As Double
    mLastModel = "(first model in the list)"
    For Each m In ActiveDesignFile.Models
        s = m.Name
        mLastModel = s
        If Left$(s, Len(GROUP_PREFIX)) = GROUP_PREFIX And InStr(s, "[") = 0 Then
            v = ParseSta(Mid$(s, Len(GROUP_PREFIX) + 1))
            If v > 0 And Abs(v - sta) <= STA_TOL Then Set FindSectionModel = m: Exit Function
        End If
    Next
End Function

Private Function ParseSta(s As String) As Double
    Dim p As Long: s = Trim$(s): p = InStr(s, "+")
    If p < 2 Then Exit Function
    If Not IsNumeric(Left$(s, p - 1)) Or Not IsNumeric(Mid$(s, p + 1)) Then Exit Function
    ParseSta = CDbl(Left$(s, p - 1)) * 100# + Val(Mid$(s, p + 1))
End Function

Private Function StaLabel(v As Double) As String
    StaLabel = Int(v / 100) & "+" & Format(v - Int(v / 100) * 100, "00.00")
End Function

' Uppercase, drop spaces/periods and a trailing LT/RT, so "STA. 440+99.00 RT." = "STA 440+99.00"
Private Function Norm(ByVal s As String) As String
    s = UCase$(Replace(Replace(Trim$(s), " ", ""), ".", ""))
    If Right$(s, 2) = "LT" Or Right$(s, 2) = "RT" Then s = Left$(s, Len(s) - 2)
    Norm = s
End Function


' Already placed if a text node in the model has the note's first two lines (normalized).
Private Function NoteAlreadyThere(m As ModelReference, lines() As String) As Boolean
    Dim ee As ElementEnumerator, el As Element, tn As TextNodeElement, i As Long, a As String, b As String
    a = Norm(lines(0)): If UBound(lines) >= 1 Then b = Norm(lines(1))
    Set ee = m.Scan()
    Do While ee.MoveNext
        Set el = ee.Current
        If el.IsTextNodeElement Then
            Set tn = el.AsTextNodeElement
            For i = 1 To tn.TextLinesCount - 1
                If Norm(tn.TextLine(i)) = a Then
                    If b = "" Or Norm(tn.TextLine(i + 1)) = b Then NoteAlreadyThere = True: Exit Function
                End If
            Next
        End If
    Loop
End Function

' Grid edges and top come from the grid's own horizontal lines (works for any section width).
' Scale (drawing units per ft of offset) comes from a matching pair of offset labels, e.g. "-140"/"140".
Private Function GridFrame(m As ModelReference, ByRef gridL As Double, ByRef gridR As Double, ByRef yTop As Double, _
                           ByRef k As Double, ByRef info As String, ByRef why As String) As Boolean
    Dim ee As ElementEnumerator, maxW As Double, haveTop As Boolean, labels As Object, t As Variant, best As Double, v As Double
    Set ee = m.Scan()
    Do While ee.MoveNext: WidestLine ee.Current, maxW: Loop
    If maxW <= 0 Then why = "no horizontal grid lines found": Exit Function
    Set ee = m.Scan()
    Do While ee.MoveNext: TopLine ee.Current, maxW, gridL, gridR, yTop, haveTop: Loop
    If Not haveTop Then why = "no full-width grid line found": Exit Function

    Set labels = CreateObject("Scripting.Dictionary")
    Set ee = m.Scan()
    Do While ee.MoveNext: OffsetLabels ee.Current, labels: Loop
    k = 0: info = ""
    For Each t In labels.Keys
        v = CDbl(t)
        If v > 0 And v > best Then
            If labels.Exists(CStr(-v)) Then
                If labels(t) > labels(CStr(-v)) Then best = v: k = (labels(t) - labels(CStr(-v))) / (2 * v)
            End If
        End If
    Next
    If k <= 0 Then
        If mLastK > 0 Then k = mLastK: info = " [no offset labels; scale from an earlier section]" Else k = 1: info = " [no offset labels; assumed 1 unit = 1 ft]"
    End If
    mLastK = k
    If (gridR - gridL) / k < 100 Or (gridR - gridL) / k > 1000 Then why = "grid width " & Format((gridR - gridL) / k, "0") & " ft looks wrong": Exit Function
    If Abs((gridR - gridL) / k - (GRID_RIGHT - GRID_LEFT)) > 2 Then info = info & " [grid is " & Format((gridR - gridL) / k, "0") & " ft wide, not " & (GRID_RIGHT - GRID_LEFT) & "]"
    GridFrame = True
End Function

Private Sub WidestLine(el As Element, ByRef maxW As Double)
    Dim r As Range3d, sub_ As ElementEnumerator
    If el.IsComplexElement Then
        Set sub_ = el.AsComplexElement.GetSubElements
        Do While sub_.MoveNext: WidestLine sub_.Current, maxW: Loop
    ElseIf el.IsLineElement Then
        r = el.Range
        If (r.High.Y - r.Low.Y) < (r.High.X - r.Low.X) * 0.001 And (r.High.X - r.Low.X) > maxW Then maxW = r.High.X - r.Low.X
    End If
End Sub

Private Sub TopLine(el As Element, maxW As Double, ByRef gridL As Double, ByRef gridR As Double, ByRef yTop As Double, ByRef haveTop As Boolean)
    Dim r As Range3d, sub_ As ElementEnumerator
    If el.IsComplexElement Then
        Set sub_ = el.AsComplexElement.GetSubElements
        Do While sub_.MoveNext: TopLine sub_.Current, maxW, gridL, gridR, yTop, haveTop: Loop
    ElseIf el.IsLineElement Then
        r = el.Range
        If (r.High.Y - r.Low.Y) < maxW * 0.001 And (r.High.X - r.Low.X) >= maxW * 0.95 Then
            If Not haveTop Or r.High.Y > yTop Then yTop = r.High.Y: gridL = r.Low.X: gridR = r.High.X: haveTop = True
        End If
    End If
End Sub

' Whole-number text labels (offset axis), keyed by value, storing the label's x center.
Private Sub OffsetLabels(el As Element, labels As Object)
    Dim t As String, r As Range3d, sub_ As ElementEnumerator
    If el.IsTextElement Then
        t = Trim$(el.AsTextElement.Text)
        If t <> "" And IsNumeric(t) And InStr(t, ".") = 0 And InStr(t, ",") = 0 Then
            r = el.Range
            labels(CStr(CDbl(t))) = (r.Low.X + r.High.X) / 2
        End If
    ElseIf el.IsComplexElement Then
        Set sub_ = el.AsComplexElement.GetSubElements
        Do While sub_.MoveNext: OffsetLabels sub_.Current, labels: Loop
    End If
End Sub

' Slide the new note (width w, height h, top at "top") sideways toward the centerline until it clears
' every note on NOTE_LEVEL already in that corner - existing ones and ones placed earlier this run.
Private Function BesideNotesInCorner(m As ModelReference, side As String, ByVal xLeft As Double, w As Double, top As Double, h As Double, k As Double) As Double
    Dim moved As Boolean, ee As ElementEnumerator, el As Element, r As Range3d, guard As Long, b As Variant
    Do
        moved = False
        Set ee = m.Scan()
        Do While ee.MoveNext
            Set el = ee.Current
            If el.IsTextNodeElement Then
                If el.Level.Name = NOTE_LEVEL Then
                    r = el.Range
                    If Overlaps(r.Low.X, r.Low.Y, r.High.X, r.High.Y, xLeft, top - h, xLeft + w, top) Then
                        xLeft = NextX(side, r.Low.X, r.High.X, w, k): moved = True
                    End If
                End If
            End If
        Loop
        For Each b In mPlacedBoxes
            If b(0) = m.Name Then
                If Overlaps(b(1), b(2), b(3), b(4), xLeft, top - h, xLeft + w, top) Then
                    xLeft = NextX(side, b(1), b(3), w, k): moved = True
                End If
            End If
        Next
        guard = guard + 1
        If guard > 20 Then Err.Raise vbObjectError + 2, , "could not find free space in the corner of " & m.Name
    Loop While moved
    BesideNotesInCorner = xLeft
End Function

Private Function Overlaps(ByVal aL As Double, ByVal aB As Double, ByVal aR As Double, ByVal aT As Double, ByVal bL As Double, ByVal bB As Double, ByVal bR As Double, ByVal bT As Double) As Boolean
    Overlaps = (aL < bR And aR > bL And aB < bT And aT > bB)
End Function

' LT notes move right (toward the centerline); RT notes move left.
Private Function NextX(ByVal side As String, ByVal occL As Double, ByVal occR As Double, ByVal w As Double, ByVal k As Double) As Double
    If side = "LT" Then NextX = occR + SIDE_GAP * k Else NextX = occL - SIDE_GAP * k - w
End Function

' Text to copy settings from, best match first:
'   1. multi-line text node on NOTE_LEVEL with NOTE_STYLE
'   2. multi-line text node with NOTE_STYLE on any level (the macro sets the level itself)
'   3. single text element with NOTE_STYLE
' Searches every section drawing model. If nothing matches, mTemplateDiag lists what was seen.
Private Function FindTemplateNote() As Element
    Dim m As ModelReference, ee As ElementEnumerator, el As Element, sty As String, lv As String, key As String
    Dim best As Element, bestRank As Long, rank As Long, seen As Object, k As Variant
    Set seen = CreateObject("Scripting.Dictionary")
    bestRank = 99
    For Each m In ActiveDesignFile.Models
        If Left$(m.Name, Len(GROUP_PREFIX)) = GROUP_PREFIX And InStr(m.Name, "[") = 0 Then
            Set ee = m.Scan()
            Do While ee.MoveNext
                Set el = ee.Current
                rank = 99: sty = "": lv = ""
                On Error Resume Next
                lv = el.Level.Name
                On Error GoTo 0
                If el.IsTextNodeElement Then
                    sty = NodeStyleName(el.AsTextNodeElement)
                    key = "text node   | level " & lv & " | style " & IIf(sty = "", "(none)", sty)
                    If sty = NOTE_STYLE And el.AsTextNodeElement.TextLinesCount >= 2 Then rank = IIf(lv = NOTE_LEVEL, 1, 2)
                ElseIf el.IsTextElement Then
                    On Error Resume Next
                    sty = el.AsTextElement.TextStyle.Name
                    On Error GoTo 0
                    key = "single text | level " & lv & " | style " & IIf(sty = "", "(none)", sty)
                    If sty = NOTE_STYLE Then rank = 3
                Else
                    key = ""
                End If
                If key <> "" Then seen(key) = seen(key) + 1
                If rank < bestRank Then Set best = el: bestRank = rank
                If bestRank = 1 Then Set FindTemplateNote = best: Exit Function
            Loop
        End If
    Next
    If Not best Is Nothing Then Set FindTemplateNote = best: Exit Function
    mTemplateDiag = "Text found in the section drawing models (count, type, level, style):" & vbCrLf
    For Each k In seen.Keys
        mTemplateDiag = mTemplateDiag & "  " & seen(k) & vbTab & k & vbCrLf
    Next
    If seen.Count = 0 Then mTemplateDiag = mTemplateDiag & "  (no text at all - the drawing models may not be loaded)" & vbCrLf
End Function

' A text node has no TextStyle of its own; read it from its first text line.
Private Function NodeStyleName(tn As TextNodeElement) As String
    Dim sub_ As ElementEnumerator
    On Error Resume Next
    Set sub_ = tn.GetSubElements
    Do While sub_.MoveNext
        If sub_.Current.IsTextElement Then
            NodeStyleName = sub_.Current.AsTextElement.TextStyle.Name
            Exit Function
        End If
    Loop
End Function


' Note text height saved by a run on another XS file in the same folder (0 if none).
Private Function SizeFilePath() As String
    SizeFilePath = ActiveDesignFile.Path & "\\_xsnotes_textsize.txt"
End Function

' Size reference: the copied note's drawn height and its exact text, saved next to the DGNs.
Private Sub SaveProbe(t As Element)
    Dim r As Range3d, body As String, i As Long
    r = t.Range
    body = CStr(r.High.Y - r.Low.Y) & vbTab & "probe" & vbTab & ActiveDesignFile.Name & vbTab & t.ModelReference.Name & vbCrLf
    If t.IsTextNodeElement Then
        For i = 1 To t.AsTextNodeElement.TextLinesCount: body = body & t.AsTextNodeElement.TextLine(i) & vbCrLf: Next
    Else
        body = body & t.AsTextElement.Text & vbCrLf
    End If
    WriteFile SizeFilePath(), body, False
End Sub

Private Function LoadProbe() As Boolean
    Dim f As Integer, ln As String, parts() As String
    Set mProbeLines = New Collection: mProbeH = 0: mProbeFrom = ""
    If Dir(SizeFilePath()) = "" Then Exit Function
    f = FreeFile: Open SizeFilePath() For Input As #f
    If Not EOF(f) Then Line Input #f, ln
    parts = Split(ln, vbTab)
    If UBound(parts) < 2 Then Close #f: Exit Function
    If parts(1) <> "probe" Or Not IsNumeric(parts(0)) Then Close #f: Exit Function   ' old format: ignore
    mProbeH = CDbl(parts(0)): mProbeFrom = parts(2)
    Do While Not EOF(f)
        Line Input #f, ln
        If ln <> "" Then mProbeLines.Add ln
    Loop
    Close #f
    LoadProbe = (mProbeH > 0 And mProbeLines.Count > 0)
End Function

' The standard note size, built in (same in every file). False if the job turned it off.
Private Function LoadStandard() As Boolean
    Set mProbeLines = New Collection: mProbeH = 0: mProbeFrom = ""
    If STD_HEIGHT <= 0 Then Exit Function
{STD_ADD}
    mProbeH = STD_HEIGHT: mProbeFrom = {vb_str(std["from"])}
    LoadStandard = True
End Function

' The section model is active: the note text built from the style here must match the standard note
' (354 A = STD_HEIGHT tall). If it doesn't, stop rather than place a wrong-size note.
Private Sub CheckStyleSize(m As ModelReference, id As String)
    Dim tn As TextNodeElement, r As Range3d, v As Variant, ratio As Double
    ' the active text style should carry over when the model changes; make sure it did
    If ActiveSettings.TextStyle.Name <> NOTE_STYLE Then SetActiveStyle
    If mProbeH <= 0 Then Exit Sub
    Set tn = CreateTextNodeElement1(Nothing, Point3dFromXYZ(0, 0, 0), Matrix3dIdentity)
    For Each v In mProbeLines: tn.AddTextLine CStr(v): Next
    r = tn.Range
    If r.High.Y - r.Low.Y <= 0 Then Err.Raise vbObjectError + 7, , id & ": could not measure text built from " & NOTE_STYLE & " in " & m.Name
    ratio = (r.High.Y - r.Low.Y) / mProbeH
    If mSizeInfo = "" Then
        mSizeInfo = "Size check: the standard note built from " & NOTE_STYLE & " in " & m.Name & " is " & _
            Format(r.High.Y - r.Low.Y, "0.000") & " tall (standard " & Format(mProbeH, "0.000") & ", x" & Format(ratio, "0.000") & ")"
        Rpt mSizeInfo
    End If
    If Abs(ratio - 1) > SIZE_TOL Then Err.Raise vbObjectError + 10, , id & ": text built from " & NOTE_STYLE & " in " & m.Name & _
        " comes out x" & Format(ratio, "0.000") & " the standard size (" & Format(r.High.Y - r.Low.Y, "0.000") & " vs " & Format(mProbeH, "0.000") & _
        "). Nothing more was placed. Fix: check this model's annotation scale is the cross-section scale and the text style is " & NOTE_STYLE & ", then send this report."
End Sub

' Make the model that was active at the start active again.
Private Sub GoHome()
    On Error Resume Next
    If Not mHome Is Nothing Then
        If ActiveModelReference.Name <> mHome.Name Then mHome.Activate
    End If
End Sub

' Level, color and weight on the node and on every line in it.
Private Sub SetSymbology(tn As TextNodeElement)
    Dim se As ElementEnumerator
    tn.Level = mLevel
    tn.LineWeight = NOTE_WEIGHT
    If NOTE_COLOR >= 0 Then tn.Color = NOTE_COLOR
    Set se = tn.GetSubElements
    Do While se.MoveNext
        se.Current.Level = mLevel
        se.Current.LineWeight = NOTE_WEIGHT
        If NOTE_COLOR >= 0 Then se.Current.Color = NOTE_COLOR
    Loop
End Sub

' Read the lines back; stop (dry run included) if the level or color did not take.
Private Sub CheckSymbology(tn As TextNodeElement, id As String)
    Dim se As ElementEnumerator, bad As String
    If tn.Level.Name <> NOTE_LEVEL Then bad = "level " & tn.Level.Name
    If NOTE_COLOR >= 0 And tn.Color <> NOTE_COLOR Then bad = bad & " color " & tn.Color
    Set se = tn.GetSubElements
    Do While se.MoveNext
        If se.Current.Level.Name <> NOTE_LEVEL Then bad = bad & " line level " & se.Current.Level.Name
        If NOTE_COLOR >= 0 And se.Current.Color <> NOTE_COLOR Then bad = bad & " line color " & se.Current.Color
    Loop
    If bad <> "" Then Err.Raise vbObjectError + 9, , id & ": the note did not take level " & NOTE_LEVEL & _
        IIf(NOTE_COLOR >= 0, " / color " & NOTE_COLOR, "") & " (got" & bad & "). Nothing more was placed." & _
        " Fix: send this report; meanwhile notes can be placed with color ByLevel."
End Sub

' Build the reference note's exact text from the style (not added to any model) and compare heights.
Private Function ProbeScale() As Double
    Dim tn As TextNodeElement, r As Range3d, v As Variant
    Set tn = CreateTextNodeElement1(Nothing, Point3dFromXYZ(0, 0, 0), Matrix3dIdentity)
    For Each v In mProbeLines: tn.AddTextLine CStr(v): Next
    r = tn.Range
    If r.High.Y - r.Low.Y <= 0 Then Err.Raise vbObjectError + 7, , "could not measure text built from " & NOTE_STYLE
    ProbeScale = mProbeH / (r.High.Y - r.Low.Y)
End Function

' From scratch: build one capital-letter line from the style (not added to any model), measure it,
' and scale so it is SCRATCH_HEIGHT tall in the drawing model.
Private Function ScratchScale() As Double
    Dim tn As TextNodeElement, r As Range3d
    Set tn = CreateTextNodeElement1(Nothing, Point3dFromXYZ(0, 0, 0), Matrix3dIdentity)
    tn.AddTextLine "STA HXE"
    r = tn.Range
    If r.High.Y - r.Low.Y <= 0 Then Err.Raise vbObjectError + 8, , "could not measure text built from " & NOTE_STYLE
    ScratchScale = SCRATCH_HEIGHT / (r.High.Y - r.Low.Y)
End Function

' The note level: from this file, or brought in from the attached level library by making it active once
' (the active level is put back afterwards).
Private Function FindOrImportLevel() As Level
    Dim lv As Level
    mLevelImported = False
    Set lv = ActiveDesignFile.Levels.Find(NOTE_LEVEL)
    If lv Is Nothing Then
        On Error Resume Next
        Set mOldLevel = ActiveSettings.Level
        CadInputQueue.SendKeyin "ACTIVE LEVEL " & NOTE_LEVEL
        Set lv = ActiveDesignFile.Levels.Find(NOTE_LEVEL)
        On Error GoTo 0
        mLevelImported = Not lv Is Nothing
    End If
    Set FindOrImportLevel = lv
End Function

Private Sub RestoreLevel()
    If Not mLevelImported Or mOldLevel Is Nothing Then Exit Sub
    On Error Resume Next
    ActiveSettings.Level = mOldLevel
    mLevelImported = False
End Sub

' Make NOTE_STYLE the active text style. If it only exists in the DOT library, the key-in imports it.
Private Sub SetActiveStyle()
    Dim ok As Boolean
    On Error Resume Next
    Set mOldStyle = ActiveSettings.TextStyle
    Err.Clear
    ActiveSettings.TextStyle = mStyle
    If Err.Number <> 0 Then Err.Clear: CadInputQueue.SendKeyin "TEXTSTYLE ACTIVE " & NOTE_STYLE
    ok = (ActiveSettings.TextStyle.Name = NOTE_STYLE)
    If Err.Number <> 0 Then ok = False
    On Error GoTo 0
    If Not ok Then Err.Raise vbObjectError + 5, , "could not make " & NOTE_STYLE & " the active text style in this file." & _
        " Fix: in this file open Element > Text Styles, make " & NOTE_STYLE & " active once (that brings it in from the library), then run again."
End Sub

Private Sub RestoreStyle()
    If mStyle Is Nothing Or mOldStyle Is Nothing Then Exit Sub
    On Error Resume Next
    ActiveSettings.TextStyle = mOldStyle
    If Err.Number <> 0 Then Err.Clear: CadInputQueue.SendKeyin "TEXTSTYLE ACTIVE " & mOldStyle.Name
End Sub

Private Function TemplateLabel() As String
    If mTemplate.IsTextNodeElement Then
        TemplateLabel = "note starting '" & mTemplate.AsTextNodeElement.TextLine(1) & "' (level " & mTemplate.Level.Name & ")"
    Else
        TemplateLabel = "text '" & mTemplate.AsTextElement.Text & "' (level " & mTemplate.Level.Name & ")"
    End If
End Function

Private Function OutPath(suffix As String) As String
    Dim nm As String: nm = ActiveDesignFile.Name
    If InStrRev(nm, ".") > 0 Then nm = Left$(nm, InStrRev(nm, ".") - 1)
    OutPath = ActiveDesignFile.Path & "\\" & nm & "_xsnotes" & suffix
End Function

Private Sub WriteFile(path As String, body As String, appendTo As Boolean)
    Dim f As Integer: f = FreeFile
    If appendTo Then Open path For Append As #f Else Open path For Output As #f
    Print #f, body;
    Close #f
End Sub

Private Sub Rpt(s As String)
    mReport = mReport & s & vbCrLf
End Sub

Private Sub Fail(msg As String)
    ' Always recorded: in the file's report and in the folder-wide summary, so a batch run never fails silently.
    On Error Resume Next
    WriteFile OutPath("_report.txt"), mReport & vbCrLf & "STOPPED - " & msg & vbCrLf, False
    WriteFile BatchSummaryPath(), Format(Now, "yyyy-mm-dd hh:nn") & vbTab & ActiveDesignFile.Name & vbTab & "STOPPED" & vbTab & Replace(Replace(msg, vbCr, ""), vbLf, " ") & vbCrLf, True
    On Error GoTo 0
    If Not mQuiet Then MsgBox msg, vbCritical, "Place XS notes - stopped"
End Sub

' One summary line per file per run, in the folder that holds the DGNs.
Private Function BatchSummaryPath() As String
    BatchSummaryPath = ActiveDesignFile.Path & "\\_xsnotes_SUMMARY.txt"
End Function

' ---------------------------------------------------------------- note list ({len(rows)} notes)
' AddNote id, section station (ft), side, lines
Private Sub Notes()
    Dim t As String
{chr(10).join(rows)}
End Sub
'''

def write_crlf(path, text, enc="cp1252"):
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode(enc))


write_crlf(WORK / "PlaceXSNotes.bas", bas)
write_crlf(WORK / "xsnotes_batch_DRYRUN.txt", f"vba run [{PROJ}]PlaceXSNotes.DryRunBatch\n")
write_crlf(WORK / "xsnotes_batch_PLACE.txt", f"vba run [{PROJ}]PlaceXSNotes.PlaceNotesBatch\n")
write_crlf(WORK / "xsnotes_batch_REMOVE.txt", f"vba run [{PROJ}]PlaceXSNotes.RemovePlacedNotesBatch\n")

# run guide from the template
from collections import Counter
per_file = Counter(n.get("dgn_file", "?") for n in notes)
cuts = sorted({(n["dgn_file"], n["new_section_sta"]) for n in notes if n["status"] == "CUT"}, key=lambda c: sta_ft(c[1]))
ref_file = max(per_file, key=lambda f: per_file[f])
guide = (HERE.parent / "templates" / "HOW_TO_RUN.md").read_text()
ns = settings.get("new_sections", {})
fill = {
    "JOB": JOB, "PROJ": PROJ, "COUNT": str(len(notes)),
    "FILE_TABLE": "\n".join(f"| {f} | {c} |" for f, c in sorted(per_file.items())),
    "CUT_LIST": "\n".join(f"- {s}  ({f})" for f, s in cuts) or "- none",
    "CUT_SETTINGS": "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in ns.items() if k != "stations") or "- (same settings as the existing sections)",
    "LEVEL": nt["level"], "STYLE": nt["text_style"], "WEIGHT": str(nt["weight"]), "COLOR": str(COLOR),
    "FIRST_FILE": settings.get("first_file") or ref_file,
}
for k, v in fill.items():
    guide = guide.replace("{{" + k + "}}", v)
(WORK / "HOW_TO_RUN.md").write_text(guide)
print(f"wrote {WORK / 'PlaceXSNotes.bas'} ({len(rows)} notes), batch command files, HOW_TO_RUN.md")
print("notes per XS file: " + ", ".join(f"{f}: {c}" for f, c in sorted(per_file.items())))
if cuts:
    print(f"new sections the user must cut first: {len(cuts)}")
