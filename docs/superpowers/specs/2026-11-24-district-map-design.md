# District map

Status: approved 2026-11-24 (review card "district-map", kept). Owner: "go with what you think is right": the
station order stays as drawn, and the Yomi Line is always shown (a line sealed twenty years ago is common knowledge). Candidate from the studio track in `ROADMAP.md`
("clickable Kuroshio map from the location designs").

## Why

Players type where they go, but nothing shows them the city: which districts exist, where they are, which one is
heating up, who they met where. The engine already knows all of that (places and heat, pressure clocks, people,
the night clock), so the map shows engine state. It needs no new art and no model calls.

## Prior art

- **Harry Beck's Tube diagram** (Wikipedia "Tube map", verified). Beck saw that underground "only the topology of
  the route mattered". Lines run only vertically, horizontally or at 45°, stations are evenly spaced, and
  interchanges are drawn distinctly. The trade-off is that the diagram doesn't show true direction or distance.
  Kuroshio has no drawn geography, and a ride costs a stretch whatever the distance, so topology is all we have and
  all that matters. Mini Metro is built on the same style (Steam page, search snippet only).
- **Cyberpunk 2077 map critique** (interfaceingame.com, verified). The map is "overloaded with icons and no reason
  to care about any of them". The article says to be "brutal in minimising information". So the map shows at most
  two marks per district, and the detail goes on a card.
- **80 Days, Fallen London, Sunless Sea** (search snippets and fan wikis only). Routes and places open up once you
  learn of them or visit them. 80 Days' map was criticised as hard to read. So districts are always shown (they are
  the skeleton), and places inside a district are listed only once known.
- **Disco Elysium** (snippet). Fast travel only goes between waypoints already found on foot. Here, clicking only
  fills the action box and the player still sends it, so travel stays a typed, narrated move.
- **W3C WAI "Complex images" and WCAG 2.1.1, 2.5.8** (verified). A map needs a short description plus a full text
  version visible to everyone, in a `<figure>` with a caption. Everything must work from the keyboard. Targets must
  be at least 24×24 px.

## Design

### The diagram

- Two concentric loops. The inner one is the **Ring Line** (the train). The outer one is **The Loop** (the
  expressway), drawn as a road band with one station node of its own.
- Four districts sit on the Ring Line in this order, clockwise from the top: **Hanabira-chō, Ikebe Low, Kuroshio
  Docks, Ring Line hub** (the station district itself).
- **Tenjō Heights** sits above the loops on a dashed spur from Hanabira-chō, labelled "maglev · sponsor badge". The
  Ring Line doesn't stop there, as its world card says.
- **Yomi Line** is a grey dashed line under the loops, marked "sealed".
- This order is a drawing choice, not something the world file says. Once approved it becomes canon, and a line in
  the Ring Line's world card can record it later.
- The lines are an `aria-hidden` SVG. Each district is a real HTML `<button>` placed over it, at least 44 px high on
  touch. That makes them keyboard-reachable and gives a list fallback for free.

### What each district shows (at most two marks)

- **You are here:** a filled node and a "YOU" tag on the current district.
- **One state mark**, the most pressing one: a pressure clock above 0 (its pips), else a place there that isn't
  calm (its mood word: wary, tense or locked down), else nothing.

### The card (on click or Enter)

Below the diagram, not a pop-up:

- the district's approved art as a thumbnail
- name, plus mood ("Ikebe Low · wary")
- its shown pressure clock with pips
- people met there (names only)
- known places: ones the player has been to, or that a current objective or journal line names
- for the current district only, "You are here", with no travel line

A **"Go"** button puts a travel line in the action box. The player can edit it and still has to send it:

| when | line |
|---|---|
| a Ring Line district, trains running | "I take the Ring Line to <district>." |
| small hours (no trains, per the night clock) | "I take a taxi to <district>." |
| Tenjō Heights | "I take a maglev pod up to Tenjō Heights." |
| Yomi Line | "I look for a way down into the sealed Yomi Line." |
| The Loop | "I ride up onto the Loop." |

### Where it lives

- On a wide screen, a "Map" section at the top of the World panel. It collapses, and the collapsed state is kept in
  `localStorage`, like other layout settings.
- On a phone, the same section at the top of the WORLD tab. The card sits under the diagram.
- `<figure>` with a `<figcaption>`, for example: "Kuroshio. You are in Ikebe Low. 2 districts under pressure."

### Engine side

- `server/views.py` gains `"map"`, built by a new `narrator/citymap.py`. It is a list of 7 districts, each `{name,
  here, mood, clock: {filled, size} | null, people: [names], places: [names], art}`, plus `trains: bool`.
- District mood is the worst mood among that district's places in `session.places`.
- `art` comes from `place_art.location_art(<district>)`.
- No new session state. Everything is derived from what the engine already keeps.

### Testing

- Unit tests for `citymap.view`: here flag, worst mood, a clock only when shown, people by district, known places
  only, `trains` false in the small hours.
- Frontend: a node test for the travel-line choice (5 rows above). tsc and eslint clean.
- A browser check at 1280 px and 390 px (the 390 px layout was never verified for chips, so this checks both).

## Not doing

- A painted map image. A schematic needs no GPU, and an image can't show state.
- Clicking to travel without sending, or any travel cost shown on the map. A ride always costs one stretch.
- Places as their own nodes. They live on the card, and the map stays at 7 nodes.
- Fog of war on districts. All 7 are known to anyone from Kuroshio.

## Open for the owner

- The station order and the two-loop drawing (a sketch goes on the review card).
- Whether Yomi Line should show at all before the player has heard of it.
