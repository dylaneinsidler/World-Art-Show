# Dylan's World Art Show

New art by living artists from around the world, a piece a minute: two screens on the PC and a home-screen
web app on the iPad (see README.md for what's in it and how it works). Dylan isn't a programmer: explain things
in plain English, do the installing, launching and checking yourself, and never use a paid service.

## Every new version

Any change Dylan asks for that changes the app makes a new version. After making and testing it:

1. Bump `VERSION`: 2.5 → 2.6 for changes and additions, 3.0 for a big redesign.
2. Add the version to the top of `CHANGELOG.md`, in plain English.
3. Run `.\tools\take-screenshots.ps1` (since 2.10: the shared picture tool; it starts `launch.ps1 -Preview -Port 47236`
   first and stops it after). It writes `screenshots\v<version>-<scene>.jpg`, both screens side by side, for the scenes
   in `tools\screenshots.json`. Look at them. Never replace an older version's pictures.
4. Point the picture at the top of `README.md` at the new version's folder.
5. Commit everything, screenshots included, and tag the commit `v<version>`.
6. Only if the change is meant for the iPad, and after asking Dylan once: merge (not rebase) GitHub's DeviantArt
   commits (the PC sends picks straight to GitHub), then push the commit and the tag. GitHub rebuilds the art
   list and the iPad site (`.github\workflows\update.yml`). Otherwise commit locally only.
7. Open the show from the Desktop shortcut so Dylan sees it.

## Things to know

- Named "World Art Show" until 2.6: the web address (World-Art-Show), the AppData folder (WorldArtShow) and the
  Screens' catalog key ('Art Show') keep the old name on purpose; the iPad app and the App Store link depend on it.
- The show runs from a copy in `AppData\Local\WorldArtShow\app` that `start.ps1` refreshes from this folder (the
  path is in the copy's `source.txt`). `launch.ps1` runs a tiny web server on `http://localhost:47233` and opens
  `index.html?desktop` on the left monitor and `about.html` on the right as Chrome kiosk windows. If this folder
  moves or is renamed, run `install.ps1` again.
- The art list (`catalog.json`, not kept in git) always comes from https://dylaneinsidler.github.io/World-Art-Show/,
  rebuilt by `tools\build_catalog.py` on GitHub every 3 hours and on every push.
- Test without the full-screen windows: run `launch.ps1 -Preview -Port 47236` in `powershell.exe -MTA` (without
  `-MTA` it restarts itself hidden), open `http://localhost:47236/index.html?desktop&theme=dark` and
  `.../about.html?theme=dark`, then stop that PowerShell; it never ends by itself. Port 47233 is the show, 47234
  the App Tester, 47235 the Morning and Night Screens. Without `?desktop`, `index.html` is the iPad version.
- Light / Dark, Digital art and "Don't show again" are saved in `AppData\Local\WorldArtShow` (`theme.txt`,
  `digital.txt`, `hidden.txt`) and shared by every copy, previews included: don't click them while testing.
- DeviantArt: the key is in `AppData\Local\WorldArtShow\deviantart-key.txt` (never in this folder or git; never
  show it). `tools\fetch_deviantart.py` runs when the show opens (at most every 6 hours) and from the daily
  "Dylan's World Art Show - DeviantArt picks" task, and uploads `deviantart.json` with git's saved GitHub sign-in; its
  log is `deviantart.log` there. Commits go to GitHub, so keep keys and AppData files out of them.
- The Morning and Night Screens show the AppData copy and pick up edits made here within a minute while they're
  open (7 to 10:30 AM, 8 to 11:30 PM).
- When starting `powershell.exe` from the PowerShell 7 tool, clear `$env:PSModulePath` first.
- Loading the art (2.10): the first piece of an opening races three pieces from different museums; a picture
  gets 15 s; a server that times out is skipped for 3 hours (`worldArtShow.hostDown` in localStorage, kept between
  openings because the Screens and the iPad cycler reopen the show every turn); the loaded next piece is saved as
  `worldArtShow.ready` for the next opening. `<meta name="referrer" content="no-referrer">` stays: the Art Institute
  of Chicago answers 403 to a localhost Referer. The National Gallery of Denmark (iip.smk.dk) wasn't answering at all
  on 2026-10-23.
