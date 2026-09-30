# World Art Show

A desktop window that shows art by living artists from around the world, a new piece every 60 seconds.

- **Hand-made and digital art by artists alive today**, from museum collections and artists around the world. No photography.
- **Travels the world:** each piece is picked by country first, so it isn't mostly the countries museums collect most. The same artist doesn't come back until hundreds of others have had a turn, and pieces don't repeat.
- **Same frame every time:** each piece is shown whole, never cropped, and the space around it is filled with a soft, blurred copy of the piece.
- **Bottom right:** the artist, their country, the title and year, and the link to the piece at its source.

## What you need

- Windows 10 or 11 with Google Chrome or Microsoft Edge
- An internet connection: the images load from the museums' own servers

No accounts or API keys needed.

## Setup

1. Put this folder somewhere permanent.
2. Right-click `install.ps1` > **Run with PowerShell**.

This adds a **World Art Show** shortcut to your Desktop. Double-click it to open the show.

## Using it

| | |
|---|---|
| **→** | next piece now |
| **←** | back to the previous piece |
| **Space** | pause / resume |
| **F** or double-click | full screen (Esc to leave) |
| Click the link | opens the piece's page at the museum |

Close it like any other window. Double-clicking the shortcut while it's open brings it to the front.

While the window is minimized or covered by other windows, the show waits, so each piece gets its full minute on screen.

## Where the art comes from

All free, public collection data:

- [Art Institute of Chicago](https://www.artic.edu/open-access/public-api) (USA)
- [Minneapolis Institute of Art](https://collections.artsmia.org/) (USA)
- [SMK – National Gallery of Denmark](https://open.smk.dk/en) (Denmark)
- [Wikidata](https://www.wikidata.org/) and [Wikimedia Commons](https://commons.wikimedia.org/): paintings, drawings, prints, murals and digital art from around the world

Only artists with a recorded birth year, no recorded death, and born in 1925 or later are included. Museums can take years to record a death, so every museum artist is also checked against Wikidata (matching name and birth year).

## Refreshing the collection

The list of works lives in `catalog.js`. To pick up new acquisitions and drop artists who have since died, rebuild it (needs Python 3):

```
python tools/build_catalog.py --fresh
```

It prints how many works, artists and countries it found, and any nationalities it didn't recognize (add those to `tools/countries.py`).
