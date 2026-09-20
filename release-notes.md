# Release Notes -- v0.5.0

> Released: 2026-09-20

The 3-D viewer becomes usable, a query becomes something you can draw, and the papers behind the graph become searchable beside it.

## What changed

**`connkg viz3d` could not open at all in 0.4.0.** It died with `ZeroDivisionError: division by zero` before showing a window, on every invocation. `BrainSceneWindow` aimed the camera during construction, but framing divides by the render window's height, and a `QtInteractor` reports `(0, 0)` until it is shown -- which `launch()` only did afterwards. The window sizes its render window before composing now, and `--width`/`--height` reach it. A second way it could not be built was found by CI on the release branch and fixed here too: with `PYVISTA_OFF_SCREEN` set, a `QtInteractor` has no interactor at all, and enabling picking on it raised in the constructor. The viewer had one test, an import, which is why nothing caught this; it now has six that build the window offscreen, and five fail without the fix.

**Point at a neuron and press P.** A panel names it, gives the description the graph stores for it, and lists its strongest partner types each way. A whole cell type shares one actor, so VTK can report which type was hit but never which neuron -- and that is the question a click asks. `connectomekg.picking` carries identity beside the geometry instead: every drawn point with the neuron that owns it, resolved by nearest-point lookup, 4.4 microseconds a pick and indifferent to tubes, stride, or whether VTK propagates point data through `tube()`. Picking is bound to the key rather than a left click, because a left click is where VTK begins a rotation.

**The viewer explores without restarting.** A **Show** box takes the same specs the command does and redraws in place; a control panel toggles the whole-brain cloud, the neuropil surfaces, the floor and tubes, sets the skeleton stride, and sets a minimum synapse count -- which is what makes a multi-hop cone usable interactively, since `cone:LC4>2` is 19,866 neurons at the default threshold and 104 at 200. A toggle keeps the camera, since it changes what is drawn rather than what is being looked at.

**A query is now a thing you can draw.** `path:LPLC2>DNp01`, `cone:LC4`, `cone:DNp01>3` and `cone:DNp01<2` are strings that go anywhere a spec goes: the CLI, `--render`, the viewer's Show box. `connkg path --render` draws a path as its hops in traced skeletons, one color per hop running dark to bright along the route; `connkg cone --render` draws a cone as shells, dark at the seed and bright outward. `connkg specs` prints every form with examples, from the same list that feeds the README and the viewer's panel.

**Effective connectivity: `connkg influence`, and an `influence` MCP tool.** How much one population drives another, hop by hop and signed, as a share of the receiving neuron's input synapses averaged over those neurons -- so 0.15 reads as "the average target gets 15% of its input from the source". A negative value is net inhibition, and two routes of opposite sign cancel, which is what this answers that counting paths does not. It is anchored to an identity that holds by construction: unsigned, at hop 1, the value is the source's share of the target's input synapses, and LC4 onto DNp01 measures +0.1482 both ways on FAFB v783. Computed by propagating a sparse vector rather than raising the matrix to a power -- the matrix is 139,255 square, so one dense power would be 1.5e10 entries, while three hops over 3.7M edges take 0.02 seconds.

**The scene cap is 5,000, up from 500.** It was 500 because drawing 500 neurons meant 500 SWC parses out of a 31 GB download; 0.4.0's skeleton cache made that a filtered read of one Parquet directory. The stride is chosen by neuron count now rather than fixed at 4, so a scene holds near `SCENE_POINT_BUDGET` points whether it draws a hundred neurons or five thousand. Measured on v783: 4,000 neurons compose in 4.5 seconds and render in 0.4. `cone:LC4` is 489 neurons and `cone:DNp01<1` is 663 -- both refused before, both drawn now.

**The renders stopped being flat.** A line has no surface, so no lighting can shade it; the documentation images are drawn as tubes now, standing on a lit floor. Every scene is lit by a three-point rig replacing PyVista's five default lights, whose flaw is not that they follow the camera but that all five sit on the view axis, so every surface is lit head-on. Measured on the LPLC2-DNp01 scene: luminance 93.8 and saturation 17.5 against the default's 92.0 and 16.3. Fixing the lights in the brain's frame instead was tried and measured worse, and those numbers are recorded in the code so nobody repeats it. `--floor` used to replace the lighting with a single narrow spotlight, which left everything the cone missed dark -- the surfaces and the cloud both vanished; the shadow-casting light sits on top of the rig now.

**The source papers, as a searchable corpus.** The graph says LC4 makes 1,401 synapses onto DNp01. It does not say how the synapses were detected, how the cell types were assigned, or what a neurotransmitter prediction is worth. Eight papers, about a million characters of body text, indexed by DocKG in `papers/`: the two FlyWire papers, Eckstein on neurotransmitter classification, Matsliah on the optic lobe, Namiki on descending neurons, Morimoto on looming, Scheffer on hemibrain, Shiu on the brain model. `papers/extract.py` and `papers/README.md` are tracked; the PDFs and the text derived from them are not, since the publishers' files are theirs to distribute.

## Upgrading

`pip install -U "connectome-kg[viz3d]"`. An existing graph keeps working and every existing command behaves as before.

The 3-D viewer works for the first time:

```bash
connkg --root . --dataset fafb783 viz3d LC4 DNp01
connkg --root . --dataset fafb783 viz3d "path:LPLC2>DNp01"
connkg --root . --dataset fafb783 specs
connkg --root . --dataset fafb783 influence --from LC4 --to DNp01
```

`viz3d` and `--render` need the skeleton cache that `connkg skeletons` writes; 0.4.0's upgrade note covers it.

To search the papers, put their PDFs in `papers/` -- `papers/README.md` lists the eight and their DOIs -- then `poetry run python papers/extract.py && dockg build --repo papers`.

---

_Full changelog: [CHANGELOG.md](https://github.com/Flux-Frontiers/connectome_kg/blob/main/CHANGELOG.md)_
