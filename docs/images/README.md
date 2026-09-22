# Images

Most images in this directory are renders of the FlyWire FAFB v783
connectome. Regenerate them all from a built graph and the skeleton download
with `poetry run python docs/scripts/render_images.py`.

Four files are the exception, and the render script does not touch any of
them:

- `connectomekg-architecture.png` and `.pdf`, a hand-made architecture
  infographic drawn from `architecture-infographic-brief.txt` in the
  repository root. It is a diagram, not a render; the figures in it come from
  the built graph and are dated on the sheet.
- `viewer_explore.png` and `viewer_display.png`, screenshots of `connkg viz3d`
  showing `circuit:compass` with each of the two control-rail tabs open. Retake
  them by hand when the viewer's layout changes: run `connkg viz3d
  circuit:compass` against a built v783 graph with neuropil meshes fetched,
  screenshot the window, and downscale to 1400 px wide so the file stays under
  the 1000 KB `check-added-large-files` limit.

The data comes from FlyWire (https://flywire.ai):

- Dorkenwald, S. et al. (2024). Neuronal wiring diagram of an adult brain.
  *Nature* 634, 124-138.
- Schlegel, P. et al. (2024). Whole-brain annotation and multi-connectome
  cell typing of *Drosophila*. *Nature* 634, 139-152.

The data is licensed under CC BY-NC-SA 4.0
(https://creativecommons.org/licenses/by-nc-sa/4.0/). These images are
adaptations of it and are shared under the same license: non-commercial use,
with attribution, and adaptations under the same terms. The Elastic License
2.0 in the repository's `LICENSE` covers the software, not these images.
