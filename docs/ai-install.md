# Installing OpenAver with an AI agent

This file is for an AI agent (Claude Code, Codex, Cursor, and similar) that a user has asked to install OpenAver and get it ready to use. Follow the steps in order. Humans can use the [README](../README.md) instead.

When you are done, the user should have: the latest release installed, the app open on their screen, their video folder added, a naming format they agreed to, and their library scanned once.

## Rules

- Install the latest **release**. Do not clone the repository or run from source. The `main` branch is ahead of the release and its features may not exist in what you install.
- Ask the user the questions in step 3. Do not guess a folder or a naming format.
- Never move, rename or delete the user's video files during setup. Nothing in this guide does.
- Take field names and current values from the running app, not from this file. This file can be newer than the installed release.
- Talk to the user in their own language.

## 1. Install

| Platform | Command |
|---|---|
| Windows x64 (PowerShell) | `irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 \| iex` |
| macOS, Apple silicon only (Terminal) | `curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh \| bash` |

The installer downloads the latest release and installs to `~/OpenAver` (`%USERPROFILE%\OpenAver` on Windows). On Windows it also creates a desktop shortcut. If OpenAver is already installed, the installer upgrades it and keeps the user's settings.

The installers expect a person at the keyboard:

- Windows: the script ends with "Press Enter to close this window". Once it prints that the install is complete, the install is done; send Enter or end the process.
- Both: if OpenAver is already installed, the script asks before overwriting, and waits for the running app to be closed. Ask the user first, then answer the prompt.

If you cannot answer prompts in your shell, ask the user to paste the command into their own terminal and tell you when it finishes.

Other platforms have no installer and no desktop window. Follow the guide below, skip step 2, set `BASE` (Synology: `http://<NAS address>:8765`; Linux: the address from the guide), open that address in the user's browser, then continue from step 3:

- Linux: [`linux-server.md`](linux-server.md)
- Synology NAS: [`synology.md`](synology.md)

## 2. Start the app

The installer does not start OpenAver. Start it yourself:

- Windows: run `%USERPROFILE%\OpenAver\OpenAver.bat`
- macOS: run `~/OpenAver/OpenAver.command`

A desktop window opens. Leave it open.

Then find the port. The app takes the first free port starting at `49152`. Try `49152`, `49153`, and so on until this returns JSON with a version:

```bash
curl -s http://127.0.0.1:49152/api/version
```

Use that address as `BASE` below. Requests from the same computer need no token.

## 3. Ask the user

Ask these before changing any setting.

**a. Where are your videos?**
One or more folders. Confirm each path exists before you save it.

**b. How should new videos be named?**
This applies only when the user later uses "Organize" on the Search page. Scanning an existing library never renames anything.

Read the current format with `GET BASE/api/config` (see `data.scraper`) and the available variables with `GET BASE/api/config/format-variables`. Build one concrete example path from the values you just read (folder levels only when `create_folder` is true, then the file name, filled in with the example values from `format-variables`) and show it to the user. Do not reuse an example from this file. Then ask whether to keep it or change it. The parts they can change:

- whether each video gets its own folder (`create_folder`)
- the folder levels, outermost first (`folder_layers`, up to 3)
- the file name (`filename_format`)

If the user has no preference, keep the default.

## 4. Save the settings

Settings are saved as one whole object.

1. `GET BASE/api/config` and take the `data` object.
2. Change only what the user asked for:
   - add each folder to `data.gallery.directories` as `{"path": "<folder>"}`. Keep entries that are already there.
   - naming fields under `data.scraper`. If you change `folder_layers`, also set `folder_format` to the same levels joined with `/`.
3. `PUT BASE/api/config` with the full `data` object as the JSON body.

Leave every other field exactly as you received it, including API keys, which come back masked. Do not send the top-level `resolved` field back.

Check that the response has `"success": true`. If it does not, show the user the error and stop.

## 5. Scan the library once

```bash
curl -N BASE/api/gallery/generate
```

This is the "Update library" button. It reads the folders and records the videos in OpenAver's own database and gallery page. It does not rename, move or edit the user's videos.

One exception: if this is an existing install and some folders are already marked read-only, the scan also downloads info for them and writes it to their output folder. Tell the user before scanning in that case.

The response is a stream (Server-Sent Events). Read it until you see an event with `"type": "done"`. If the stream reports an error or skipped folders, or ends without `done`, tell the user what it said and do not report the scan as successful.

A large library on a network drive can take several minutes. Tell the user it is running.

## 6. Offer to fill in missing covers and info

```bash
curl -s BASE/api/gallery/missing-check
```

`data.total_missing` is how many videos can be filled in: they have no cover or no info file yet, and have a recognisable ID.

- If it is `0`, skip this step.
- Otherwise tell the user the number, and that filling them in downloads covers and info from the web, writes them next to each video, and does not rename or move the video. It takes a few seconds per video. Ask whether to run it now.

If the user says yes, ask them to click "Enrich All" (一鍵補完) on the Library page (`BASE/scanner`). The button shows progress, can be stopped, and asks for confirmation on large batches. Do not call the enrich API yourself during setup.

If the user says no, tell them they can do it later with the same button.

## 7. Hand over

Tell the user, briefly:

- OpenAver is open, and the cover wall is on the Browse page (`BASE/showcase`).
- how many videos were found, and how many still lack a cover or info.
- the naming format that is saved, and that it is used only when they organize new videos from the Search page.
- the first-run tour in the app shows the same steps and can be skipped.

For anything after setup, such as favourites, tags, bookmarks or custom sources, read the app's own description of its API:

```bash
curl -s BASE/api/capabilities
```

## If something goes wrong

- **No port answers.** The app is not running. Start it again (step 2) and wait a few seconds. On Windows, a missing WebView2 Runtime stops the window from opening; the installer prints the download link.
- **macOS says the app cannot be opened.** Run the installer again. It clears the quarantine flag.
- **The scan finds 0 videos.** Check the folder path, and check that the folder is reachable (network drives must be mounted).
- **A request from another computer returns 403.** OpenAver only accepts requests from the same computer unless the user turns on server mode in Settings. Run your commands on the computer where OpenAver is installed.
