# Starter courtyard visual evidence

These are mechanical crops of actual local game captures, not generated images.
All ROIs are `(x, y, width, height)` after RGB-independent 1280x720 linear resize.

- `buff.png`: `(357,27,39,54)` from `courtyard_1050.png`.
- `identity_frame.png`: `(315,34,27,51)` from `courtyard_1050.png`; no account name or level.
- `story_bubble.png`: `(826,227,61,62)` from `courtyard_1050.png`.
- `story_bubble_moved.png`: `(709,227,61,62)` from `courtyard_moved_1050.png`.
- `story_bubble_native.png`: `(826,227,61,62)` from `courtyard_1280.png`.

Regression captures are in `dev_tools/fixtures/newbie_leveling/`, copied unchanged
from `oas-second-mumu-check-20260908.png`, `oas-leveling-live-start.png`, and
`oas-leveling-1280-check.png` respectively, all captured on 2026-09-08 from the
second MuMu account at level 3. The existing GameUi moon/cloud template is reused.

Only this starter courtyard and the observed three-dot NPC bubble are supported.
Unknown dialogs, tutorials, purchases and summons have no fallback click rule.
NPC suggestion requires account OCR plus three independent courtyard anchors,
an observed bubble template, a gold-ring pixel check, and exactly three aligned
pale dots. The runner must enforce account binding, repeated observations, and
the target-level stop before it acts. OCR account names are binding tokens and
can contain character-recognition errors; they are not verified display names.

The level parser accepts 1-60 and requires two 0.90-confidence OCR reads of only
the badge, after different white-pixel thresholds agree. Only actual level 3 has
been calibrated so far; other levels need real-frame regression coverage before
claiming end-to-end unattended leveling.

## Tree story scene added after the first script-issued NPC click

`story_scene_1280.png` is the unchanged evidence screenshot
`log/newbie_leveling/oas_leveling/20260908-212726-253848-paused.png`, captured
2026-09-08 at 21:27:26. The deterministic runner had clicked the courtyard NPC
once, then stopped because this next screen was not yet recognized.

Mechanical RGB-independent crops from that native 1280x720 capture:

- `story_tree_mark.png`: `(660,130,110,95)`.
- `story_shrine_window.png`: `(1096,97,149,101)`.
- `story_return.png`: `(15,15,54,55)`.
- `story_scene_bubble.png`: `(169,241,59,60)`.
- `story_scene_layout.png`: full frame resized to 320x180 using `INTER_AREA`.

`story_scene` requires both spatially independent decorations, the exact back
icon and a conservative whole-layout guard. The NPC ring/three-dot target is
checked separately: if absent/unstable, its area is `None`, but an independently
verified scene may still offer its back button. It exposes only inner NPC and back areas; account level and identity remain
`None` because they are not visible here. A runner must retain its own freshly
verified session/account guards and return to the courtyard to recheck account
data. Recognizing a back icon alone is never permission to click it.

The full-layout signature supplements small anchors to reject observed-style
modals/dialogue panels, dimming, noise and camera shifts. Tests cover opaque and
semi-transparent synthetic occlusions in several screen regions. This does not
prove rejection of every conceivable overlay; unfamiliar scene variation can
intentionally become unknown.
No future dialogue screen or generic confirmation behavior is implied.

### Measured idle animation, 2026-09-08

Twelve original native frames from
`C:/Users/OASUser/AppData/Local/Temp/oas-leveling-scene-motion/` are preserved as
`dev_tools/fixtures/newbie_leveling/story_scene_motion/*.png` (suffixes 00-11).
Inspection of frames 00, 05 and 11 showed only character/umbrella/fox idle motion;
all twelve decoration/back/bubble correlations are 0.998-1.000. The old fixed
thumbnail rejected moving clothes and umbrella tiles (mean errors 20-38 against
18), not the static scene anchors or bubble.

`story_scene_motion_min.png` and `story_scene_motion_max.png` are mechanical
per-channel pixel minima/maxima over the original scene capture and frames
**00,02,04,06,08,10**, each resized to 320x180 with `INTER_AREA`. Odd frames
**01,03,05,07,09,11 are held-out positives**, not inputs to those assets.
The same global/local residual thresholds are applied against these observed
pixel bounds; static pixels remain tight and entire character rectangles are
not ignored. All twelve frames now recognize the scene, including the six
held-out frames, while modal/dimming regressions remain rejected.

Only the tightly bounded left bubble search ROI is excluded from the page-layout
comparison, since target disappearance must not masquerade as loss of page
identity. The separate NPC template/ring/three-dot detector must still pass to
offer an NPC action. `story_layout_changed`, `story_return_unverified`, and
`story_scene_anchors_unverified` are diagnostic **unknown** observations;
`story_npc_unstable` has a verified scene/back but no NPC target.

## Second tree camera: Xiaobai dialogue and gold-eye tutorial

The original dialogue capture is
`log/newbie_leveling/oas_leveling/20260908-214201-488032-paused.png`, preserved
unchanged as `dev_tools/fixtures/newbie_leveling/story_dialogue_1280.png`.
The eight native frames from
`C:/Users/OASUser/AppData/Local/Temp/oas-leveling-dialog-continue/` are preserved
unchanged under `dev_tools/fixtures/newbie_leveling/story_eye_motion/`.
Inspection of eye frames 00,03,07 confirms a large gold-ring eye at the top
center, not a text dialogue; only foreground characters/umbrella move.

Mechanical crops from eye frame 00 (coordinates at native 1280x720):

- `story2_tree.png`: `(751,131,98,111)`.
- `story2_shrine.png`: `(1190,92,90,111)`.
- `tutorial_eye.png`: `(574,89,132,134)`.

Mechanical crops from the original Xiaobai dialogue:

- `dialogue_skip.png`: `(826,554,91,40)`, the explicit Chinese story-skip button.
- `dialogue_speaker.png`: `(345,558,67,35)`, Xiaobai's nameplate.
- `dialogue_panel.png`: `(10,634,220,76)`, the patterned dark dialogue footer.

`story_eye_layout.png` is frame 00 resized to 320x180 using `INTER_AREA`.
Its `_motion_min.png` / `_motion_max.png` bounds use only frames **00,02,04,06**;
**01,03,05,07** are held-out positives. The eye detector also requires the two
static scene decorations, exact back icon, gold annulus and bright eye motif,
and absence of dialogue anchors. The output `tutorial_area` is only the inner
eye `(618,140,44,34)`, never the entire scene or all circular icons.

`story_dialogue_layout.png` is the original dialogue's 320x180 thumbnail.
There is only one real dialogue frame. To allow the already measured foreground
idle animation without weakening static/panel checks, its min/max bounds combine
the real dialogue and explicit synthetic motion transfers from the same four
even eye frames. Only `(335,230,425,315)` and `(1190,270,90,260)` are transferred;
the speaker, skip button, dialogue footer, portrait and static scenery are not
treated as unconstrained regions. Transfers from four odd frames form additional
**synthetic**, not real-screenshot, regression cases.

`story_dialogue` requires both new-camera decorations, the back icon, Xiaobai
nameplate, actual patterned footer, explicit skip button, and its own layout
guard. It returns `story_skip_area=(846,564,48,20)` and no tutorial/NPC action.
Both variants return the verified back area `(29,29,24,24)` and leave account
identity/level as `None`; the runner's session and account checks remain required.

Regressions include all eight real eye frames, original dialogue, held-out motion,
missing anchors/buttons, wrong-scene pasted icons, dialogue covering the eye
scene, 95-percent dimming, and synthetic purchase/account/other modal panels.
Unknown overlays do not inherit a generic skip/confirm/tutorial click. These
rules support only the recorded camera/UI variants, not every future dialogue.

## Gold-eye tutorial after courtyard re-entry: explicit camera-1 variant

The original stopped screenshot
`log/newbie_leveling/oas_leveling/20260908-220233-481142-paused.png` is preserved
as `story_eye_reentry_1280.png`. Eight unchanged frames from
`C:/Users/OASUser/AppData/Local/Temp/oas-leveling-after-eye/` are preserved under
`dev_tools/fixtures/newbie_leveling/story_eye_reentry_motion/`.

This failure was **not only idle animation**. Returning to the courtyard and
re-entering restored camera 1, while the tutorial eye remained fixed at screen
coordinates `(574,89,132,134)`. In all eight new frames, the camera-2 tree score
was about -0.03 and shrine 0.647, below 0.95; the original camera-1 shrine was
1.000. Its old tree-mark crop `(660,130,110,95)` was partially covered by the
screen-space eye and fell to 0.284. The eye itself scored 0.966 and back 1.000.
Widening animation tolerances or camera-2 search areas would not address that.

`story1_tree_paper.png` is a mechanical `(760,305,128,85)` crop from the earlier
real `story_scene_1280.png`, outside the eye's bounds. It has zero mean pixel
difference against the corresponding re-entry region. The explicit camera-1-eye
detector requires this paper charm, the original shrine window, exact back,
gold-ring/white-eye target, and no dialogue controls; it does not repurpose a
single generic tree or return template to identify every camera.

`story_eye_camera1_layout.png` is new frame 00 at 320x180 (`INTER_AREA`). Its
`_motion_min.png` / `_motion_max.png` use only **00,02,04,06**. Four odd frames
**01,03,05,07** and the original stopped screenshot are held-out real positives.
The measured motion bounds apply only to explicit observed foreground areas:

- Pink character/umbrella: `(90,325,200,325)`.
- Fox: `(330,340,210,170)`.
- Player character/clothing: `(485,225,255,360)`.
- Right character/carried shrine: `(1025,265,250,280)`.

These rectangles are **not ignored masks**. Pixels inside must remain within
the locally observed color/pose bounds, under the original residual thresholds;
all pixels outside use the strict static reference, including environment and
controls. Tests place opaque panels wholly inside each character rectangle and
still reject them. Full dimming, dialogue/purchase panels, missing anchors and
unobserved camera translation also remain unknown.

Any model of variable foreground pixels increases ambiguity for an overlay that
closely resembles those same pixels; finite visual tests cannot rule out every
possible overlay. The bounded pixel constraints, independent scenery/control
anchors, no-dialogue checks, and runner's repeated observations/account guards
are retained together. Newly observed cameras or poses still require evidence;
this change is not a global relaxation of scene recognition.

## Selectively dark Yin-Yang reveal, camera 1

The real stopped screenshot `20260908-221127-921810-paused.png` is preserved as
`story_reveal_1280.png`. Original eight frames from the temp `oas-leveling-yinyang`
directory and four independently later frames from `oas-leveling-yinyang-heldout`
are preserved under fixture folders `story_reveal_motion` and
`story_reveal_heldout`. All thirteen real frames pass the reveal detector.

Mechanical crops from the stopped screenshot:

- `reveal_shrine.png`: `(1096,97,149,101)`.
- `reveal_mountain.png`: `(115,78,130,125)`.
- `reveal_floor.png`: `(320,590,720,110)`.
- `reveal_return.png`: `(15,15,54,55)`, actual dark-effect back button.
- `reveal_question.png`: `(870,264,59,65)`.
- `reveal_question_glyph.png`: `(889,278,21,34)`.

`reveal_paper_0.png` through `_3.png` are `(455,156,110,76)` crops from even
frames **00,02,04,06**. Only this fixed low-light crop receives Gaussian blur
sigma 3 to remove fine flicker before matching (correlation >=0.95 and mean
absolute RGB error <=3). `reveal_paper.png` retains the initial raw calibration
crop and is not an extra runtime variant. Odd frames and the four later frames
are held out; there is no whole-image gamma adjustment.

The reveal is not modeled as a generic dim screen. Three independent dark
environment patches, the paper charm and back button must match, while the
observed pink/cyan/gold character regions must retain their bright color
fractions and combined brightness. The brown question bubble and white question
glyph must agree spatially. Only then is `story_reveal` returned with inner
`npc_story_area=(891,282,16,26)` and `return_area=(29,29,24,24)`; account values
remain unknown and other action fields remain empty.

Purple ghosts roam across the middle of the scene, so this detector does not
attempt to fit every ghost position with a whole-frame pose template. Tests
reject black screens with pasted controls, uniformly darkened ordinary scenes,
missing environment/character/control evidence, further dimming and obvious
modal/footer occlusion. A specially placed, previously unseen overlay that
avoids all checked regions is not ruled out by finite tests. Support is limited
to this recorded camera-1 reveal step, not subsequent dialogue or battle pages.
