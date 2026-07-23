# Attachments and previews

Drop any file onto a card and it sticks; click it later and SQ shows it to you right there, spreadsheets to CAD models included.

## Attaching files

Files attach to cards two ways:

- Drop them straight onto a card on the board.
- Open the card and drop them on the attachments box (or click it to browse).

Cards with files show a paperclip chip with the count. Files go up to 100 MB each, which is generous room for meshes and archives. In the card dialog you can preview, download, or delete each file; deleting is permanent, so SQ asks first. Deleting a card also cleans up its files.

Every file in a project also appears on the project's [overview page](boards.md#the-overview-page), newest first, one click from its preview.

## Previews

Click a filename and the preview opens full screen, with a download button in the corner. What you see depends on the format:

| Format | What you see |
|---|---|
| CSV | A table, delimiter detected automatically (first 200 rows) |
| Excel (.xlsx) | The first sheet as a table, other sheet names noted |
| Word (.docx) | The document text |
| Text and code (.txt, .md, .log, .json, .yaml, .py, .gcode, .scad, and friends) | The text, up to the first 60,000 characters |
| Images (.png, .jpg, .gif, .webp, .svg, .bmp) | The image |
| PDF | The document, in your browser's PDF viewer |
| Video (.mp4, .webm, .mov, .m4v) | A player, right in the dialog |
| Audio (.mp3, .wav, .ogg, .flac, .m4a) | A player, right in the dialog |
| STL | The model in the 3D viewer |
| 3MF, OBJ | Converted automatically, same 3D viewer |
| STEP (.step, .stp), IGES (.iges, .igs) | Converted in your browser, same 3D viewer |
| Zip | A listing of what is inside, with sizes |
| SolidWorks (.sldprt, .sldasm, .slddrw, .eprt, .easm) | The preview image saved inside the file (see below) |
| Visio (.vsd, .vsdx) | The preview image saved inside the file |
| Illustrator (.ai) | The artwork as a PDF, when saved with PDF compatibility |
| DipTrace (.dip) | No preview; a note explains what to export instead |
| Anything else | A download link |

## 3D models

STL models render in a spin-and-zoom viewer built into the page: drag to rotate, scroll or pinch to zoom. 3MF and OBJ files convert automatically and land in the same viewer; extremely dense meshes (past two million triangles) are declined with a suggestion to open them in a slicer instead.

STEP and IGES models are converted right in your browser. The converter ships with SQ, so nothing is fetched from the internet and it works offline; the first STEP preview loads the converter, which takes a few extra seconds, and later previews are quick.

## SolidWorks files, honestly

SolidWorks files preview as an image, not as live geometry. SQ digs out the preview picture the file carries inside itself, the same one Windows Explorer shows, and displays that.

Why not full 3D? SolidWorks geometry is a proprietary, sealed format. Reading it properly takes a commercially licensed CAD kernel; that is how the big quoting sites import SolidWorks, and it is not something a self-hosted tracker can ship. So SQ shows you the honest best it can and tells you so in the preview.

A few particulars:

- Vendor download sites (McMaster-Carr and friends) often hand out STEP files wearing SolidWorks names. SQ checks the file's actual contents, so those open in the full 3D viewer.
- The newest SolidWorks format keeps even its preview image in a sealed container SQ cannot read yet; those files say so plainly instead of pretending.
- A file saved with the "Save preview picture" option off carries no image at all; SQ tells you that too.

For real 3D on the card, export from SolidWorks: **STEP** for a model others can also use, or **STL** for a quick in-browser preview. Attach it next to the original.

Visio diagrams work the same way: the embedded preview image shows, and for the full drawing, export a PDF from Visio and attach that.

## A few format notes

- **Illustrator**: an .ai file saved with PDF compatibility is a PDF at heart, and previews as one. Saved without it, SQ asks you to re-save with the option on.
- **DipTrace**: the format carries nothing SQ can read; export a PDF or Gerber set from DipTrace and attach it alongside.
- Anything SQ cannot preview still attaches, downloads, and counts on the paperclip chip. The squirrel hoards everything; it just cannot open every nut.
