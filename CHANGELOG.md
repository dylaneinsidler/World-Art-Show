# Changelog

What changed in each version of World Art Show, newest first. Every version has pictures in `screenshots\v<version>-<scene>`:
after a change, bump `VERSION`, add it here, take a picture of both screens while it's open, and commit.

## 2.13 (November 5, 2026)

Dylan: "it's displaying digital art from DeviantArt even when it's toggled off."

- **Digital art Off means nothing from DeviantArt again.** Since 2.12, Off still let in DeviantArt pieces whose tags said
  they were painted or drawn by hand, but those tags can't tell a painting on paper from one made on a tablet, so
  digital art got through. Now Off shows only the museums' paintings, drawings and prints (about 630 pieces). On still
  adds DeviantArt's art. With fewer pieces, the ones shown longest ago come round again sooner.
## 2.12 (November 3, 2026)

Dylan: "I have not been seeing new art really, and I've been seeing a lot of repeats."

- **New art every day, with Digital art still off.** "Off" used to leave out everything from DeviantArt, so the show
  was only the museums' 614 pieces, which hardly ever change. Now Off means what it says, no digital art: the
  museums' pieces plus DeviantArt's hand-made paintings, drawings, watercolors and prints (about 5,200 now, judged by
  each piece's tags, most of them made this year), with more arriving every day. On still adds the digital art.
- **No more repeats.** Once all of an artist's pieces had been shown, the show could still pick that artist and show
  one of them again, so after a few weeks most pieces were repeats. Now it only shows pieces it hasn't shown yet;
  only when every piece has had its turn does the half shown longest ago come round again.
- **One memory on the PC.** The show's own window, the Morning Screens, the Night Screens and the App Tester each
  kept their own list of what they'd shown, so each showed again what the others just had. They now share one list
  (`seen.txt`, kept by the show's server). The iPad keeps its own.
- **Fewer "workflow failed" emails.** On November 3 GitHub's publishing service failed for a moment (its own server
  error, nothing wrong with the show). The update now waits two minutes and tries again before giving up.

## 2.11 (October 31, 2026)

- **Works on one monitor.** With only one monitor, both screens now open side by side on it, each a smaller copy of what it shows on
  its own monitor, with everything working as usual. With two monitors nothing changes.

## 2.10 (October 23, 2026)

- **The art shows up right away, every time.** On October 23 the National Gallery of Denmark's picture server
  stopped answering, and the show waited 40 seconds on each of its pieces before trying another. The Morning and
  Night Screens and the iPad's cycler open the show fresh for each turn, so a turn could end on "Getting the newest
  art…" with no art at all. Now:
  - it tries three pieces from three different museums at once and shows whichever arrives first;
  - it gives up on a picture after 15 seconds, and a museum whose server doesn't answer is skipped for three
    hours, remembered from one opening to the next;
  - the next piece, already loaded during a turn, is the first piece of the next turn, so it appears in under a
    second.
- **The Art Institute of Chicago's art shows on the PC again.** Chicago turns away picture requests from a page on
  this computer, which is how the PC and the Screens run the show, so its 300-odd pieces never appeared there. The
  show now asks for pictures without saying which page wants them.
- Pictures of each version are taken with the shared picture tool now (`tools\take-screenshots.ps1`).

## 2.9 (October 11, 2026)

- **On the iPad and iPhone, swipe up for the details:** what the piece is and what it's about, the artist (born,
  where from, a short biography), a small map from the artist's country to where the piece is now, and the museum
  that has it (on view or not). It's hidden until you swipe up (or tap "Details" at the bottom left); swipe it down,
  or tap the art, to hide it again. While it's open the piece stays put. Swiping left and right still changes the piece.
- Not on the iPad yet: it goes up when you say so.

## 2.8 (October 10, 2026)

- **Both screens appear together**: each window now opens straight at full size on its own monitor (no small window jumping to full screen), and both stay dark for a moment and then appear at the same time.
- **Its own icon in the Windows taskbar** while it's open, instead of Chrome's.

## 2.7 (October 10, 2026)

- Inside the Morning and Night Screens, this app's own buttons and controls can be clicked now.
- In the Morning and Night Screens, a click on an empty part of this app closes the Screens (as before), and its buttons and controls work.

## 2.6 (October 9, 2026)

- Its name is now **Dylan's World Art Show**: the folder, the Desktop shortcut, the window and welcome screen, the
  iPad home-screen name, and the daily DeviantArt task. The web address stays the same, so the iPad app keeps working.

## 2.5 (October 9, 2026)

- **Never stalls when a museum's images stop loading:** the Art Institute of Chicago's image server started refusing
  everyone (403), and the show could give up on "Getting the newest art". Now a museum whose images fail three times
  in a row is set aside for half an hour, and the show carries on with the others.

## 2.4 (October 9, 2026)

- **"Don't show again"**: on the computer's right screen (for the app, the Morning and Night Screens and the tester), and
  on the iPad when you tap to pause. A hidden piece never comes back.
- **No male nudity or gay themes:** pieces whose titles point to them are left out. (Museums rarely tag what's in a
  picture, so the button is the sure way.)

## 2.3 (October 8, 2026)

- **Real art only, unless you turn on digital art:** the show is the museums' paintings, drawings, prints and the like.
  DeviantArt's digital art comes back with **Digital art: On**: a button on the computer's right screen (remembered for
  the app, the Morning and Night Screens and the tester), and on the iPad, a button that appears when you tap to pause.

## 2.2 (October 8, 2026)

- **Back to a new piece every minute**, now on the minute, in step with the Morning and Night Screens: each time the
  show comes up there, a new piece arrives with it.
- **Where the artist is from:** for museum artists, their hometown (city, state where there is one, and country) at the
  top of the right screen, from Wikidata, with the map's dot on that city. DeviantArt artists show their country.

## 2.1 (October 8, 2026)

- **A new piece every 10 seconds** on the computer's two screens (the iPad stays at a minute). The right screen's
  long text scrolls in time with it.
- `?theme=dark` / `?theme=light` in the address picks the look (the Morning and Night Screens use it).

## 2.0 (October 8, 2026)

- **Two screens on the computer:** the art on the left; on the right, its story, the artist, their country on a
  map, and where it came from. Back / Pause / Next, a Light / Dark switch, and an X on each screen.
- The iPad and the website are the same as before.

## 1.0

The show on the iPad and in one window on the computer.
