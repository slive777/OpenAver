# Installing OpenAver with an AI agent

This file is for an AI agent (Claude Code, Codex, Cursor, and similar) that a user has asked to install OpenAver and get it ready to use. Follow the steps in order. Humans can use the [README](../README.md) instead.

Setup is complete when the user is looking at their own covers in the app: the latest release installed, the app open, their video folder added, the library scanned. Naming for new videos comes after that, as one optional question.

## Rules

- Install the latest **release**. Do not clone the repository or run from source. The `main` branch is ahead of the release and its features may not exist in what you install.
- Do not guess the video folder; ask. Do not save a naming format the user has not agreed to.
- Never move, rename or delete the user's video files during setup. Nothing in this guide does.
- Take field names and current values from the running app, not from this file. This file can be newer than the installed release.
- Talk to the user in their own language.

## 1. Install

| Platform | Command |
|---|---|
| Windows x64 (PowerShell) | `irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 \| iex` |
| macOS, Apple silicon only (Terminal) | `curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh \| bash` |
| Linux x86_64 (Terminal, server edition) | `curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh \| bash` |

The installer downloads the latest release and installs to `~/OpenAver` (`%USERPROFILE%\OpenAver` on Windows). On Windows it also creates a desktop shortcut. If OpenAver is already installed, the installer upgrades it and keeps the user's settings.

The installers expect a person at the keyboard:

- Windows: the script ends with "Press Enter to close this window". Once it prints that the install is complete, the install is done; send Enter or end the process.
- Both: if OpenAver is already installed, the script asks before overwriting, and waits for the running app to be closed. Ask the user first, then answer the prompt.

If you cannot answer prompts in your shell, ask the user to paste the command into their own terminal and tell you when it finishes.

The Linux installer starts the service itself and prints the address (there is no desktop window and no overwrite prompt; a fresh install asks only whether to start on boot, while converting an old manual install or finding an old service still running asks for an extra confirmation). Skip step 2, set `BASE` to `http://127.0.0.1:<port>` (same machine as the host, no token needed), where `<port>` is the port in the address the installer printed (49152 unless the user changed it with `openaver config port`; `openaver url` prints it again), open the printed address in the user's browser, then continue from step 3. Details: [`linux-server.md`](linux-server.md).

Synology has no installer and no desktop window. Follow [`synology.md`](synology.md), skip step 2, set `BASE` to `http://<NAS address>:8765`, open that address in the user's browser, then continue from step 3.

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

### The first-run tour

The first time the app opens, a tour appears over the window. It walks the user through the same things you are about to do in steps 3 to 6: add a folder, update the library, fill in missing info, open the Browse page.

Tell the user this as soon as the app is open, and let them choose:

- **You do it.** They press "Skip" (跳過) on the tour, and you continue with step 3. The tour can be replayed later from the Help page.
- **They follow the tour themselves.** Do not run steps 3 to 6. Stay available for questions, wait until they say they are done, then continue from step 7.

Do not dismiss the tour for them and do not mark it as completed through the API.

## 3. Ask where the videos are

Ask one question only: which folder or folders hold the user's videos. Confirm each path exists.

Do not ask about naming or any other setting yet. The user should see their library first.

## 4. Add the folders

Settings are saved as one whole object.

1. `GET BASE/api/config` and take the `data` object.
2. Add each folder to `data.gallery.directories` as `{"path": "<folder>"}`. Keep entries that are already there.
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

## 7. Show the library

Open the Browse page (`BASE/showcase`) on the user's screen: in the app window, click "Showcase" (瀏覽) in the sidebar, or open that address in their browser. Confirm they can see their covers before you continue. Setup is complete at this point.

Tell the user, in two or three sentences:

- how many videos were found, and how many still lack a cover or info.
- clicking a cover opens its details.
- new videos come in through the Search page.

Do not teach more than that. For the rest, point to the first-run tour and the Help page inside the app. They match the installed version; your own explanation may not.

## 8. Then ask once about new videos

After the user has seen their library, ask one question: when new videos arrive, should OpenAver rename them and sort them into folders?

- If no, stop here. Tell them they can ask you later.
- If yes, continue below.

This setting is used when the user presses "Organize" on the Search page. Saving it changes nothing by itself. Organizing a video that is already in the library will move and rename it too, so tell the user that.

**Propose a format instead of asking for one.** Most users cannot describe a naming format, but they already have one on disk.

1. Look at how the user's existing videos are laid out: list a sample of paths in the folders from step 3.
2. Read the current settings with `GET BASE/api/config` (see `data.scraper`) and the available variables with `GET BASE/api/config/format-variables`.
3. If the existing videos follow a clear pattern, find the closest format the variables can express and show it as one concrete example path, built from the user's own data. Ask: "Your videos are mostly laid out like this. Use the same for new ones?"
4. If there is no clear pattern, say so. Show one example of the current setting instead and ask whether to keep it. Do not guess.

The parts you can set:

- whether each video gets its own folder (`create_folder`)
- the folder levels, outermost first (`folder_layers`, up to 3). Include folder levels in your example only when `create_folder` is true.
- the file name (`filename_format`)

Save only after the user agrees, the same way as step 4: `GET`, change the fields under `data.scraper`, `PUT` the whole object. If you change `folder_layers`, also set `folder_format` to the same levels joined with `/`.

Then tell the user what was saved, and that they organize a new video by dropping it on the Search page and pressing "Organize".

## After setup

For anything else, such as favourites, tags, bookmarks or custom sources, read the app's own description of its API:

```bash
curl -s BASE/api/capabilities
```

## If something goes wrong

- **No port answers.** The app is not running. Start it again (step 2) and wait a few seconds. On Windows, a missing WebView2 Runtime stops the window from opening; the installer prints the download link.
- **macOS says the app cannot be opened.** Run the installer again. It clears the quarantine flag.
- **The scan finds 0 videos.** Check the folder path, and check that the folder is reachable (network drives must be mounted).
- **A request from another computer returns 403.** OpenAver only accepts requests from the same computer unless the user turns on server mode in Settings. Run your commands on the computer where OpenAver is installed.
