# Captions

## A1 stills

Use this base caption with every A1 still:

> HUGINN, a fictional 6U CubeSat (Project AESIR). The spacecraft's look is
> drawn — a standard 6U CubeSat with twin solar arrays — since its
> definition gives no panel layout or colors. It is enlarged about
> 892,000 times against Earth so it can be seen. Earth: NASA Blue Marble
> (NASA Earth Observatory). Position and orbit: the P3 runs' orbit file
> (spacecraft shown at MET 1000, 508 km over 28.1 N, 77.5 W). Ground
> station GS-RAVENSROOST is fictional, at a real public site. The Sun's
> direction is computed from the run's UTC time; the spacecraft's pose is
> drawn. The run was sunlit throughout.

Per still:

- `a1_01_wide.png` — Wide: Earth, the PASS-3 orbit (MET 0-1230), the
  ground station's ringed marker, and a pale blue dot labeled HUGINN
  marking the spacecraft's position at MET 1000.
- `a1_02_hero.png` — Hero: HUGINN's sunlit side — bus, rails, name plate,
  mode beacon, load bar, and the SA1/SA2 solar wings — over Earth's limb.
- `a1_03_payload.png` — Payload: from the foil side, Earth filling the
  lower frame, the payload barrel on the nadir face pointing down at it,
  array backs. (Reframed in A2 at the Director's ruling.)

## A2/A4 clips

Use this base caption with each clip:

> HUGINN flown from its own record (VERDA timeline): position, sunlight,
> contact, payload state, mode, and load limit state are the run's
> telemetry; brief flashes mark ODIN's requests (cyan) and BALDUR-0's
> decisions (green allow, red deny). The spacecraft's look and pose are
> drawn, enlarged about 892,000 times against Earth. The Sun's direction
> is computed from the run's UTC time. Earth: NASA Blue Marble (NASA
> Earth Observatory). Space weather appears only in runs whose record
> carries the feed; this run carries none.

Adjust the last sentence per run. The made-up fixture stills are never
captioned as a run: label them "made-up test fixture — not a run".

## A5 look-pass stills

Add to the clip caption: "Clouds and night lights are NASA composites
(Blue Marble cloud layer; Black Marble 2016), not the run's date. The
spacecraft is its real size against Earth in the follow shot; in the wide
opening shot it stays an enlarged labeled dot, as that caption says."

## A5 animated clips (true-scale follow shot)

Use this base caption with each A5 clip, in place of the A2/A4 one:

> HUGINN at its true size, camera about three meters away, Earth 500 km
> below — flown from the run's own record (VERDA timeline): position,
> sunlight, contact, payload state, mode, and load limit state are the
> run's telemetry. The spacecraft's look and pose are drawn — a standard
> 6U CubeSat with twin solar arrays — since its definition gives no
> panel layout or colors. The Sun's direction is computed from the run's
> UTC time. Earth: NASA Blue Marble (NASA Earth Observatory); clouds and
> night lights are NASA composites (Blue Marble cloud layer; Black
> Marble 2016), not the run's date. Space weather appears only in runs
> whose record carries the feed.

Per cut:

- Instrument cut (`*_a5_instrument.mp4`, for VERDA's pane): add "The thin
  line from the antenna is the ground-station radio link while in
  contact. Brief flashes mark ODIN's requests (cyan) and BALDUR-0's
  decisions (green allow, red deny); the strip shows the load limit
  state (green, amber, red)."
- Clean cut (`*_a5_clean.mp4`, for the video): no text and no data cues;
  only what a camera would see. Say so: "Clean cut: no labels or data
  cues."

Per run:

- Adjust the space-weather sentence per run, as with the A2/A4 caption.
- Where a run's epoch is marked shifted in `inputs/epochs.json`, say:
  "The Sun is set to agree with the run's record, not the campaign
  clock." The PASS-3 runs' epochs are not shifted, so their clips do
  not carry that sentence.
- `dev-ph2-p3-open-01` (the run animated first, because no scored
  PASS3 run's timeline is in the animation inputs) is not shifted and
  carries no feed: sunlit and in contact throughout the clip
  (MET 800-1225), and it shows no space weather.
