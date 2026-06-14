# Piano Player

Roblox piano automation. Drop in a sheet or MIDI file, hit play.

![Piano Player](/screenshot.png)

---

## Download

Grab the latest **`PianoPlayer.exe`** from the [Releases page](https://github.com/RainBryan/PianoPlayer/releases/latest).

Run it once — that's it. No installer, no console window, no Python required.

You can also get it from [rainbryan.com](https://rainbryan.com).

> **Windows SmartScreen warning:** Since the .exe is unsigned, Windows may
> warn you the first time you run it. Click **More info → Run anyway**.

---

## What it does

- Plays **sheet notation** (like `c d e f g` or `[ceg]` chords) at any BPM
- Plays **MIDI files** with their original timing — drag in a `.mid`, it transposes to fit the Roblox piano automatically
- **Queue songs** to play one after another
- **Favorites** so your best songs are always one click away
- Built-in **note expression**: hold notes, fermatas, staccato, swing, BPM changes mid-song
- Global hotkeys work while Roblox is focused

## Hotkeys

| Key | Action |
| --- | ------ |
| `F6` | Play |
| `F7` | Pause / Resume |
| `F8` | Stop |

## Is this against Roblox TOS?

Piano Player only sends standard keyboard input — the exact same keys you'd
press yourself. It does not read game memory, modify the client, or
automate anything inside Roblox. It's equivalent to using a macro keyboard
or having a friend type for you. **Use at your own discretion.**

---

## Running from source

```sh
git clone https://github.com/RainBryan/PianoPlayer.git
cd PianoPlayer
pip install -r requirements.txt
python app.py
```

Tested on Python 3.10+. Windows 10/11 are the primary targets; macOS works
but requires granting accessibility permissions (System Settings → Privacy
& Security → Accessibility) so `pynput` can simulate keypresses.

## Building the .exe yourself

```sh
build\build.bat
```

Produces `dist/PianoPlayer.exe` (~30 MB, single file).

---

## Known Bugs/Errors/Issues

- `PianoPlayer.exe` Gets flagged as a virus 
- Pausing then stopping a song breaks the resume function
- Pausing a MIDI song and then resuming will halt the piano display

For any other bugs, errors, or issues, please report them to me via Discord or GitHub.

## Thank you for your support!

---

## Credits

Made by **[RainBryan](https://rainbryan.com)** · [@RainBryan192](https://www.roblox.com/users/559231096/profile) on Roblox
Made using Claude AI

## License

[See LICENSE](LICENSE)
