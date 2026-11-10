# Grey-box library

A library of ready-made grey stand-ins: every **pose** seen from every **camera**, each rendered once as a flat grey figure (plus its
props: stool, ledge, rail, window frame) on a grey floor grid with a horizon line. Nothing here is a character; it only says
"someone sits on a stool, seen from the side, from 4.5 m away". Browse it at `/shorts/library/` (view only).

Each cell `<pose>/<camera>/` holds `board.png` (the picture), `depth.png` (white = near), `floor-depth.png` and `figure-depth.png` (the same view with everything hidden / only the figure, on the same near-far range; `insert` compares them to cut out the figure exactly), `pose.json` / `pose.png` (OpenPose skeleton)
and `meta.json` (camera, where the feet and figure box are).

## Poses

Each pose has a `group` (the browse page groups the same way). Props are grey blocks in the cell; poses are FK-checked (feet on the floor or
on their prop, hands on the rail / counter / table, nothing below the floor).

**basic**: `stand`, `walk`, `sit-stool`, `sit-ledge`, `lean-rail`, `stand-back`, `stand-window-back`, `crouch`, `lie-side`, `sit-floor`

**cinematic** (lone figures, backs, silhouettes, big spaces):
- `doorway-silhouette`: standing just in front of a door-frame block, arms loose (door frame is behind the figure, so profile cameras still see it)
- `walk-away`: mid-stride with the back to the `ws-front` camera
- `sit-bed-edge-head-down`: on the edge of a low bed block, elbows on knees, head hanging
- `rail-overlook`: forearms on a waist-high rail over a low parapet, looking out
- `look-up`: standing, head tilted up about 35 degrees
- `sit-bench`: on a bench block, hands in the lap
- `stand-umbrella`: one arm up holding an umbrella (thin pole + flat disc canopy)
- `lie-floor-up`: on the back, arms and legs a little apart, head toward +x
- `sit-window-sill`: on a sill block, knees up and feet on the sill, window frame behind

**editorial** (magazine cover / fashion poses):
- `contrapposto`: weight on one leg, hips tilted, free leg out
- `hand-on-hip`: contrapposto with one hand on the hip, elbow out
- `over-shoulder-glance`: body turned away from `ws-front`, head turned back about 120 degrees in total (shown in `pose.json` / `pose.png`; the grey head is a plain cylinder)
- `hands-in-pockets`: both hands at hip pockets
- `arms-crossed`: forearms crossed over the chest
- `lean-wall`: right shoulder on a wall block, one foot crossed in front with the knee bent
- `chair-backward`: straddling a chair block, arms on the backrest
- `seated-legs-crossed`: on a stool, one leg crossed over the other
- `chin-on-hand`: seated at a table block, one elbow on the table and the chin in that hand
- `crouch-street`: low crouch, forearms on the knees
- `kneel-one-knee`: one knee on the floor, forearm resting on the other knee
- `recline-elbow`: on the floor, propped on one elbow, one knee up

**character** (generic geometry, named for what it was made for):

| pose | for | what |
|---|---|---|
| `inspect-hand` | Saeko (chrome hand) | one forearm raised in front of the face, head tilted down at it |
| `cross-legged-deck` | Rin (cyberdeck) | sitting cross-legged on the floor, a flat box on the lap, hands on it |
| `behind-counter` | Mama Sato | standing behind a counter block, hands on it |
| `lean-cane` | Tadamori | slightly stooped, one hand on top of a cane pole |
| `adjust-visor` | Yuki | one hand at the temple, elbow forward |

## Cameras

`ews-high`, `ws-front`, `ws-back`, `ws-profile`, `ms-front`, `ms-profile`, `mcu-front`, `ots-left`, `ots-right`, `low-hero`, `top-down`
and the cinema set: `ews-low`, `ws-low-back`, `profile-close`, `high-wide`, `doorway-frame`

(`ews` extreme wide, `ws` wide, `ms` medium, `mcu` close-up; `ots-*` are over-the-shoulder with a second grey figure in the foreground;
`low-hero` looks up from knee height; `top-down` looks straight down.)

- `ews-low`: 20 m away, camera 0.4 m off the floor, 70 mm: a small figure in a big space
- `ws-low-back`: 4 m behind the figure, camera 0.3 m high
- `profile-close`: medium shot from the side, 85 mm (about the same framing as `ms-profile`, longer lens look)
- `high-wide`: 45 degrees, far (8 m out and 8 m up)
- `doorway-frame`: 3 m away, slightly off axis, 28 mm; only reads as "through a doorway" with the doorway props, but renders for every pose

## Thumbnails (original ten poses and eleven cameras; the browse page shows every cell)

| pose \ camera | ews-high | ws-front | ws-back | ws-profile | ms-front | ms-profile | mcu-front | ots-left | ots-right | low-hero | top-down |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **stand** | <img src="/shorts/library/stand/ews-high/board.jpg" width="90" alt="stand ews-high"> | <img src="/shorts/library/stand/ws-front/board.jpg" width="90" alt="stand ws-front"> | <img src="/shorts/library/stand/ws-back/board.jpg" width="90" alt="stand ws-back"> | <img src="/shorts/library/stand/ws-profile/board.jpg" width="90" alt="stand ws-profile"> | <img src="/shorts/library/stand/ms-front/board.jpg" width="90" alt="stand ms-front"> | <img src="/shorts/library/stand/ms-profile/board.jpg" width="90" alt="stand ms-profile"> | <img src="/shorts/library/stand/mcu-front/board.jpg" width="90" alt="stand mcu-front"> | <img src="/shorts/library/stand/ots-left/board.jpg" width="90" alt="stand ots-left"> | <img src="/shorts/library/stand/ots-right/board.jpg" width="90" alt="stand ots-right"> | <img src="/shorts/library/stand/low-hero/board.jpg" width="90" alt="stand low-hero"> | <img src="/shorts/library/stand/top-down/board.jpg" width="90" alt="stand top-down"> |
| **walk** | <img src="/shorts/library/walk/ews-high/board.jpg" width="90" alt="walk ews-high"> | <img src="/shorts/library/walk/ws-front/board.jpg" width="90" alt="walk ws-front"> | <img src="/shorts/library/walk/ws-back/board.jpg" width="90" alt="walk ws-back"> | <img src="/shorts/library/walk/ws-profile/board.jpg" width="90" alt="walk ws-profile"> | <img src="/shorts/library/walk/ms-front/board.jpg" width="90" alt="walk ms-front"> | <img src="/shorts/library/walk/ms-profile/board.jpg" width="90" alt="walk ms-profile"> | <img src="/shorts/library/walk/mcu-front/board.jpg" width="90" alt="walk mcu-front"> | <img src="/shorts/library/walk/ots-left/board.jpg" width="90" alt="walk ots-left"> | <img src="/shorts/library/walk/ots-right/board.jpg" width="90" alt="walk ots-right"> | <img src="/shorts/library/walk/low-hero/board.jpg" width="90" alt="walk low-hero"> | <img src="/shorts/library/walk/top-down/board.jpg" width="90" alt="walk top-down"> |
| **sit-stool** | <img src="/shorts/library/sit-stool/ews-high/board.jpg" width="90" alt="sit-stool ews-high"> | <img src="/shorts/library/sit-stool/ws-front/board.jpg" width="90" alt="sit-stool ws-front"> | <img src="/shorts/library/sit-stool/ws-back/board.jpg" width="90" alt="sit-stool ws-back"> | <img src="/shorts/library/sit-stool/ws-profile/board.jpg" width="90" alt="sit-stool ws-profile"> | <img src="/shorts/library/sit-stool/ms-front/board.jpg" width="90" alt="sit-stool ms-front"> | <img src="/shorts/library/sit-stool/ms-profile/board.jpg" width="90" alt="sit-stool ms-profile"> | <img src="/shorts/library/sit-stool/mcu-front/board.jpg" width="90" alt="sit-stool mcu-front"> | <img src="/shorts/library/sit-stool/ots-left/board.jpg" width="90" alt="sit-stool ots-left"> | <img src="/shorts/library/sit-stool/ots-right/board.jpg" width="90" alt="sit-stool ots-right"> | <img src="/shorts/library/sit-stool/low-hero/board.jpg" width="90" alt="sit-stool low-hero"> | <img src="/shorts/library/sit-stool/top-down/board.jpg" width="90" alt="sit-stool top-down"> |
| **sit-ledge** | <img src="/shorts/library/sit-ledge/ews-high/board.jpg" width="90" alt="sit-ledge ews-high"> | <img src="/shorts/library/sit-ledge/ws-front/board.jpg" width="90" alt="sit-ledge ws-front"> | <img src="/shorts/library/sit-ledge/ws-back/board.jpg" width="90" alt="sit-ledge ws-back"> | <img src="/shorts/library/sit-ledge/ws-profile/board.jpg" width="90" alt="sit-ledge ws-profile"> | <img src="/shorts/library/sit-ledge/ms-front/board.jpg" width="90" alt="sit-ledge ms-front"> | <img src="/shorts/library/sit-ledge/ms-profile/board.jpg" width="90" alt="sit-ledge ms-profile"> | <img src="/shorts/library/sit-ledge/mcu-front/board.jpg" width="90" alt="sit-ledge mcu-front"> | <img src="/shorts/library/sit-ledge/ots-left/board.jpg" width="90" alt="sit-ledge ots-left"> | <img src="/shorts/library/sit-ledge/ots-right/board.jpg" width="90" alt="sit-ledge ots-right"> | <img src="/shorts/library/sit-ledge/low-hero/board.jpg" width="90" alt="sit-ledge low-hero"> | <img src="/shorts/library/sit-ledge/top-down/board.jpg" width="90" alt="sit-ledge top-down"> |
| **lean-rail** | <img src="/shorts/library/lean-rail/ews-high/board.jpg" width="90" alt="lean-rail ews-high"> | <img src="/shorts/library/lean-rail/ws-front/board.jpg" width="90" alt="lean-rail ws-front"> | <img src="/shorts/library/lean-rail/ws-back/board.jpg" width="90" alt="lean-rail ws-back"> | <img src="/shorts/library/lean-rail/ws-profile/board.jpg" width="90" alt="lean-rail ws-profile"> | <img src="/shorts/library/lean-rail/ms-front/board.jpg" width="90" alt="lean-rail ms-front"> | <img src="/shorts/library/lean-rail/ms-profile/board.jpg" width="90" alt="lean-rail ms-profile"> | <img src="/shorts/library/lean-rail/mcu-front/board.jpg" width="90" alt="lean-rail mcu-front"> | <img src="/shorts/library/lean-rail/ots-left/board.jpg" width="90" alt="lean-rail ots-left"> | <img src="/shorts/library/lean-rail/ots-right/board.jpg" width="90" alt="lean-rail ots-right"> | <img src="/shorts/library/lean-rail/low-hero/board.jpg" width="90" alt="lean-rail low-hero"> | <img src="/shorts/library/lean-rail/top-down/board.jpg" width="90" alt="lean-rail top-down"> |
| **stand-back** | <img src="/shorts/library/stand-back/ews-high/board.jpg" width="90" alt="stand-back ews-high"> | <img src="/shorts/library/stand-back/ws-front/board.jpg" width="90" alt="stand-back ws-front"> | <img src="/shorts/library/stand-back/ws-back/board.jpg" width="90" alt="stand-back ws-back"> | <img src="/shorts/library/stand-back/ws-profile/board.jpg" width="90" alt="stand-back ws-profile"> | <img src="/shorts/library/stand-back/ms-front/board.jpg" width="90" alt="stand-back ms-front"> | <img src="/shorts/library/stand-back/ms-profile/board.jpg" width="90" alt="stand-back ms-profile"> | <img src="/shorts/library/stand-back/mcu-front/board.jpg" width="90" alt="stand-back mcu-front"> | <img src="/shorts/library/stand-back/ots-left/board.jpg" width="90" alt="stand-back ots-left"> | <img src="/shorts/library/stand-back/ots-right/board.jpg" width="90" alt="stand-back ots-right"> | <img src="/shorts/library/stand-back/low-hero/board.jpg" width="90" alt="stand-back low-hero"> | <img src="/shorts/library/stand-back/top-down/board.jpg" width="90" alt="stand-back top-down"> |
| **stand-window-back** | <img src="/shorts/library/stand-window-back/ews-high/board.jpg" width="90" alt="stand-window-back ews-high"> | <img src="/shorts/library/stand-window-back/ws-front/board.jpg" width="90" alt="stand-window-back ws-front"> | <img src="/shorts/library/stand-window-back/ws-back/board.jpg" width="90" alt="stand-window-back ws-back"> | <img src="/shorts/library/stand-window-back/ws-profile/board.jpg" width="90" alt="stand-window-back ws-profile"> | <img src="/shorts/library/stand-window-back/ms-front/board.jpg" width="90" alt="stand-window-back ms-front"> | <img src="/shorts/library/stand-window-back/ms-profile/board.jpg" width="90" alt="stand-window-back ms-profile"> | <img src="/shorts/library/stand-window-back/mcu-front/board.jpg" width="90" alt="stand-window-back mcu-front"> | <img src="/shorts/library/stand-window-back/ots-left/board.jpg" width="90" alt="stand-window-back ots-left"> | <img src="/shorts/library/stand-window-back/ots-right/board.jpg" width="90" alt="stand-window-back ots-right"> | <img src="/shorts/library/stand-window-back/low-hero/board.jpg" width="90" alt="stand-window-back low-hero"> | <img src="/shorts/library/stand-window-back/top-down/board.jpg" width="90" alt="stand-window-back top-down"> |
| **crouch** | <img src="/shorts/library/crouch/ews-high/board.jpg" width="90" alt="crouch ews-high"> | <img src="/shorts/library/crouch/ws-front/board.jpg" width="90" alt="crouch ws-front"> | <img src="/shorts/library/crouch/ws-back/board.jpg" width="90" alt="crouch ws-back"> | <img src="/shorts/library/crouch/ws-profile/board.jpg" width="90" alt="crouch ws-profile"> | <img src="/shorts/library/crouch/ms-front/board.jpg" width="90" alt="crouch ms-front"> | <img src="/shorts/library/crouch/ms-profile/board.jpg" width="90" alt="crouch ms-profile"> | <img src="/shorts/library/crouch/mcu-front/board.jpg" width="90" alt="crouch mcu-front"> | <img src="/shorts/library/crouch/ots-left/board.jpg" width="90" alt="crouch ots-left"> | <img src="/shorts/library/crouch/ots-right/board.jpg" width="90" alt="crouch ots-right"> | <img src="/shorts/library/crouch/low-hero/board.jpg" width="90" alt="crouch low-hero"> | <img src="/shorts/library/crouch/top-down/board.jpg" width="90" alt="crouch top-down"> |
| **lie-side** | <img src="/shorts/library/lie-side/ews-high/board.jpg" width="90" alt="lie-side ews-high"> | <img src="/shorts/library/lie-side/ws-front/board.jpg" width="90" alt="lie-side ws-front"> | <img src="/shorts/library/lie-side/ws-back/board.jpg" width="90" alt="lie-side ws-back"> | <img src="/shorts/library/lie-side/ws-profile/board.jpg" width="90" alt="lie-side ws-profile"> | <img src="/shorts/library/lie-side/ms-front/board.jpg" width="90" alt="lie-side ms-front"> | <img src="/shorts/library/lie-side/ms-profile/board.jpg" width="90" alt="lie-side ms-profile"> | <img src="/shorts/library/lie-side/mcu-front/board.jpg" width="90" alt="lie-side mcu-front"> | <img src="/shorts/library/lie-side/ots-left/board.jpg" width="90" alt="lie-side ots-left"> | <img src="/shorts/library/lie-side/ots-right/board.jpg" width="90" alt="lie-side ots-right"> | <img src="/shorts/library/lie-side/low-hero/board.jpg" width="90" alt="lie-side low-hero"> | <img src="/shorts/library/lie-side/top-down/board.jpg" width="90" alt="lie-side top-down"> |
| **sit-floor** | <img src="/shorts/library/sit-floor/ews-high/board.jpg" width="90" alt="sit-floor ews-high"> | <img src="/shorts/library/sit-floor/ws-front/board.jpg" width="90" alt="sit-floor ws-front"> | <img src="/shorts/library/sit-floor/ws-back/board.jpg" width="90" alt="sit-floor ws-back"> | <img src="/shorts/library/sit-floor/ws-profile/board.jpg" width="90" alt="sit-floor ws-profile"> | <img src="/shorts/library/sit-floor/ms-front/board.jpg" width="90" alt="sit-floor ms-front"> | <img src="/shorts/library/sit-floor/ms-profile/board.jpg" width="90" alt="sit-floor ms-profile"> | <img src="/shorts/library/sit-floor/mcu-front/board.jpg" width="90" alt="sit-floor mcu-front"> | <img src="/shorts/library/sit-floor/ots-left/board.jpg" width="90" alt="sit-floor ots-left"> | <img src="/shorts/library/sit-floor/ots-right/board.jpg" width="90" alt="sit-floor ots-right"> | <img src="/shorts/library/sit-floor/low-hero/board.jpg" width="90" alt="sit-floor low-hero"> | <img src="/shorts/library/sit-floor/top-down/board.jpg" width="90" alt="sit-floor top-down"> |

## Putting a stand-in into a room: `insert`

A shot picks one pose + one camera, then says where the feet go and how tall the figure is in the frame:

```
python -m tools.greybox_library insert PLATE POSE CAMERA --feet 0.45,0.9 --height 0.55 --label "C1" --out board.png
```

- `PLATE` is any room plate image; `--feet x,y` is where the feet land (0..1 of width and height); `--height` is the figure's height as a
  fraction of the frame height. The plate is darkened to 55% so the grey figure reads clearly, and a small tag (the label) sits at the figure's top.
- Two people: add `--figure POSE CAMERA x,y HEIGHT LABEL` (repeat for more), e.g. `--figure walk ws-front 0.75,0.9 0.5 "C2"`.
- `--lib DIR` points at another library (default `design-data/greybox-library`).
- Besides `board.png` you get `board.pose.json`, `board.pose.png` (the skeletons moved and scaled to match) and `board.depth.png`
  (a plate-sized depth patch, black where nothing is pasted), which later guided renders use. The patch is *per-figure relative depth*: values compare within one figure, not between two figures or against the plate.
- On the board the figure is mid-grey, its props (stool, rail, window) darker, and an over-the-shoulder foreground figure darker still, each with a light outline.

Rebuild the browse page with `python -m tools.greybox_library page`.
