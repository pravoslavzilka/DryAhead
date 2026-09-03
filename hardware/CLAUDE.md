# hardware/

**Never hand-edit anything in this directory — source or generated. Ask
the user first**, always, regardless of file type.

## State, not aspiration
- No KiCad sources or fab outputs exist in the repo yet. Today this
  directory holds only READMEs and a hand-maintained `bom.csv` (the parts
  list — not a KiCad-generated fab BOM).
- `.gitattributes` already has git-lfs patterns staged for when files land:
  `*.kicad_pcb`, `*.kicad_sch`, `*.kicad_pro`, `*.kicad_mod`, `*.step`,
  `*.stp`, `*.stl`, `*.f3d`, `*.dxf`.
- No gerbers, drill files, or pick-and-place exports exist or have a
  defined pattern yet.
