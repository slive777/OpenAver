# External AI services for OpenAver

> **繁中摘要**　OpenAver 的「AI 功能」可以接你自己架的 AI 端點。目前有兩項：**圖片相似**（讓「探索星空」多一個看封面的訊號，端點要自己架）與**人臉**（讓封面縮圖、女優頭像改以你自己架的端點找到的臉為中心）。這份文件寫給 AI 助理讀：照對應那一節架好端點、跑完一致性測試、設成開機自啟，再把網址交給使用者填進設定頁「AI 功能」裡對應的分頁（圖片相似／人臉）。翻譯不需要這份文件，直接在設定頁填金鑰即可。
>
> **EN**　OpenAver can use AI endpoints that you host yourself. Two capabilities are described here: **Image similarity** (an extra "looks alike" signal for the Explore wall; you host the endpoint) and **Faces** (face-centered crops for wall thumbnails and actress photos). This file is written for AI assistants.

## Hand this to your AI assistant（交給 AI 助理）

The settings page has a button that copies the text below, with the real address filled in. If you are an assistant and the user pasted it to you, everything you need is in this file.

> 請替我架一個 OpenAver 圖片相似端點。規格在 https://github.com/slive777/OpenAver/blob/main/docs/external-ai.md 的「圖片相似」一節，照那節的一致性測試自己驗過再回報。架好後告訴我端點網址，我會填進 OpenAver 設定頁「AI 功能 › 圖片相似」。這台 OpenAver 在 `<本機 LAN 網址>`，端點要讓這個網址連得到。請把服務設成開機自啟。

For the face endpoint, hand over this instead:

> 請替我架一個 OpenAver 人臉對焦端點。規格在 https://github.com/slive777/OpenAver/blob/main/docs/external-ai.md 的「Faces（人臉）」一節，照那節的一致性腳本自己驗過再回報。架好後告訴我端點網址，我會填進 OpenAver 設定頁「AI 功能 › 人臉」。這台 OpenAver 在 `<本機 LAN 網址>`，端點要讓這個網址連得到。請把服務設成開機自啟，並先告訴我 insightface 權重有授權限制。

Each capability section ends with its own consistency test; use the one for the capability you were asked to set up.

Rules for the assistant:

- You are done only when (1) the consistency test below passes against the address you will hand over, (2) it still passes after the service has been restarted or the machine rebooted, and (3) you have told the user the exact URL to paste.
- The URL must be reachable **from the machine that runs OpenAver**, not just from where you work. `localhost` is only right if both run on the same machine.
- Code blocks in this file marked `bash` are meant to be copied and run as-is. `$EP` is your embeddings endpoint (for example `http://192.168.1.50:8000`); `$OA` is the OpenAver address.

## Image similarity（圖片相似）

OpenAver turns each cover into a vector by calling your endpoint, stores the vectors in its own database, and mixes the "looks alike" ranking with its existing rule-based ranking. If the endpoint is off, the Explore wall quietly uses the rules only.

### Contract

`POST {EP}/v1/embeddings` with a JSON body, the same shape as OpenAI embeddings:

```json
{"model": "anything", "input": ["data:image/jpeg;base64,..."]}
```

```json
{"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": [0.01, -0.02]}], "model": "clip-vit-base-patch32"}
```

- **Request.** `Content-Type: application/json`. If the user set an API key, OpenAver sends `Authorization: Bearer <key>`; otherwise no auth header. `input` is an array; OpenAver currently sends one image per request, accept more if you can. Images are data URIs (`image/jpeg`, `image/png` or `image/webp`) whose longest side is at most 448 px. Reply `400` for an `input` string that is not an image data URI (text queries are not used yet).
- **What the image is.** For library covers OpenAver sends the **right half** of the cover (the left half carries the title text). You embed whatever you receive; do not crop again.
- **Response.** `data[0].embedding` is an array of plain numbers (no booleans, no NaN, not all zero), 128 to 4096 long, **L2-normalized** (OpenAver normalizes again, but send unit vectors anyway). `model` is a **required non-empty string** that names the model and stays the same for every reply. If it changes, OpenAver treats the index as stale and asks the user to rebuild it. If you swap the underlying model (including a different quantization), make the reported `model` change with it; if the name cannot change, ask the user to press "Delete and rebuild index" on the settings page.
- **Errors.** Use normal HTTP codes. `4xx` is never retried. `5xx` and timeouts are retried once. Timeouts: connect 5 s, read 30 s (90 s for the first request of a test, so a cold model load is fine).
- **Same input, same output.** Embedding the same image twice must give (almost) the same vector.

### curl

Smallest possible call (a 16x16 PNG), with an optional key:

```bash
curl -s "$EP/v1/embeddings" \
  -H "Content-Type: application/json" \
  ${EP_KEY:+-H "Authorization: Bearer $EP_KEY"} \
  -d '{"model":"any","input":["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAGUlEQVR4nGOM6jnBQApgIkn1qIZRDUNKAwBVcQHO3mdG9AAAAABJRU5ErkJggg=="]}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); v=r['data'][0]['embedding']; print('model =', r['model'], '| dim =', len(v))"
```

### Consistency test

Four assertions, the same ones the settings page "Test" button runs:

1. Dimension is the same in every reply and between 128 and 4096.
2. The **same** sample image sent twice gives cosine similarity of at least **0.99**.
3. Two **different** samples give cosine similarity below **0.9**.
4. `model` is a non-empty string and identical in all replies.

Samples are not real covers. Sample A is a masked demo image that lives in the OpenAver repository (right half taken, as above); sample B is a picture drawn by the script below, with no randomness. The script needs Python 3.9+ and Pillow, downloads sample A from GitHub, and exits with code 0 only when all four assertions pass. Save it as `check_embeddings.py`:

```python
#!/usr/bin/env python3
"""Consistency test for an OpenAver image-similarity endpoint.

Usage: python check_embeddings.py http://HOST:PORT [API_KEY]
Needs: Python 3.9+ and Pillow. Exit code 0 = pass, 1 = fail.
"""
import base64, io, json, math, sys, urllib.request
from PIL import Image, ImageDraw

BASE = sys.argv[1].rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else ""
RAW_A = "https://raw.githubusercontent.com/slive777/OpenAver/main/web/static/img/demo/sone-103.jpg"


def sample_a():  # demo cover -> right half, long edge <= 448, JPEG q90
    im = Image.open(io.BytesIO(urllib.request.urlopen(RAW_A, timeout=30).read())).convert("RGB")
    w, h = im.size
    im = im.crop((w // 2, 0, w, h))
    s = 448 / max(im.size)
    if s < 1:
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def sample_b():  # synthetic picture, fully deterministic
    im = Image.new("RGB", (448, 448), (32, 48, 160))
    d = ImageDraw.Draw(im)
    d.rectangle((36, 36, 200, 200), fill=(220, 48, 48))
    d.ellipse((220, 180, 412, 412), fill=(240, 220, 48))
    d.polygon([(224, 24), (400, 168), (48, 168)], fill=(48, 200, 72))
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6, optimize=False)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def embed(uri):
    req = urllib.request.Request(
        BASE + "/v1/embeddings",
        data=json.dumps({"model": "any", "input": [uri]}).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + KEY} if KEY else {})},
    )
    r = json.load(urllib.request.urlopen(req, timeout=90))
    v = r["data"][0]["embedding"]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v], r.get("model")


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


a, b = sample_a(), sample_b()
(a1, m1), (a2, m2), (b1, m3) = embed(a), embed(a), embed(b)
checks = {
    "dimension 128-4096 and equal": len(a1) == len(a2) == len(b1) and 128 <= len(a1) <= 4096,
    "same image twice: cosine >= 0.99": cos(a1, a2) >= 0.99,
    "two different samples: cosine < 0.9": cos(a1, b1) < 0.9,
    "'model' is a non-empty string, same every time": isinstance(m1, str) and m1 != "" and m1 == m2 == m3,
}
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"model={m1} dim={len(a1)} cos_same={cos(a1, a2):.4f} cos_diff={cos(a1, b1):.4f}")
sys.exit(0 if all(checks.values()) else 1)
```

Run it with the Python that has Pillow (the `venv` from the next section works):

```bash
python3 check_embeddings.py "$EP" ${EP_KEY:+"$EP_KEY"}
```

If you cannot reach GitHub, or the assistant runs on another machine than OpenAver and the user has switched on **server mode** (top of the settings page; if an access password is set, log in first), `GET {OA}/api/ai/sample/embeddings` returns the same two samples ready to send: `{"inputs":[A,B],"expect":{...},"steps":[...]}`.

**Run the test again after a restart or reboot.** An endpoint that passes once and disappears at the next boot silently turns the Explore wall back to rules only.

The settings page reports a failed test as "can't reach this address" or "reached it, but the reply breaks the contract" plus one of these check names: `http_4xx`, `auth` (401/403), `http_5xx`, `not_json`, `shape`, `not_numeric`, `dim_range`, `zero_norm`, `no_model`, `dim_mismatch`, `unstable`, `not_discriminative`, `model_flapping`.

### Self-host reference

The easiest path that runs anywhere is **onnxruntime loading an ONNX file directly** (no compiler, no PyTorch). CPU is the floor; it is fast enough (about 0.1 s per cover in our test on a desktop CPU, so a few thousand covers take several minutes).

- Model: CLIP ViT-B/32, vision tower only, int8 ONNX export by Xenova. MIT license.
- Download: `https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx`
- Size: 89,117,001 bytes (about 85 MiB). SHA-256: `583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299`
- Output: 512 numbers (`image_embeds`), then L2-normalize.
- Preprocessing (CLIP standard): RGB, resize to 224x224, divide by 255, subtract mean `[0.48145466, 0.4578275, 0.40821073]`, divide by std `[0.26862954, 0.26130258, 0.27577711]`, channels first.

Use a virtual environment so the service always finds the packages it was installed with (many Linux distributions refuse `pip install` into the system Python). Pick a folder for everything: `/opt/openaver-embeddings` for a system-wide service, `~/openaver-embeddings` for a per-user service. The examples below run inside that folder.

<!-- verify:skip -->
```bash
# one-time setup: virtual environment, packages, model download (about 85 MiB)
python3 -m venv venv
venv/bin/pip install onnxruntime numpy pillow
curl -L -o vision_model_quantized.onnx https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx
```

On Windows the same thing is `python -m venv venv` and `venv\Scripts\pip install onnxruntime numpy pillow`.

A complete server in one file (standard library HTTP server plus the three packages above). Save it as `clip_server.py`, next to the model file. Run it as `venv/bin/python clip_server.py vision_model_quantized.onnx 8000`; it listens on `0.0.0.0`.

```python
"""Minimal OpenAI-style /v1/embeddings server for image similarity (CLIP ViT-B/32, CPU)."""
import base64, io, json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import onnxruntime as ort
from PIL import Image

MODEL_PATH = sys.argv[1] if len(sys.argv) > 1 else "vision_model_quantized.onnx"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
MODEL_NAME = "clip-vit-base-patch32"
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
output_name = "image_embeds"
lock = __import__("threading").Lock()


def embed(data_uri: str) -> list:
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("RGB").resize((224, 224), Image.Resampling.LANCZOS)
    x = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
    x = x.transpose(2, 0, 1)[None]
    with lock:
        v = session.run([output_name], {input_name: x})[0][0]
    v = v / np.linalg.norm(v)
    return v.astype(float).tolist()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/embeddings":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
            if not all(isinstance(s, str) and s.startswith("data:image/") for s in inputs):
                return self._send(400, {"error": "only image data URIs are supported"})
            data = [{"object": "embedding", "index": i, "embedding": embed(s)} for i, s in enumerate(inputs)]
        except Exception as e:  # noqa: BLE001
            return self._send(400, {"error": str(e)})
        self._send(200, {"object": "list", "data": data, "model": MODEL_NAME})

    def _send(self, code, obj):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
```

Faster hardware is an option, not a requirement: install the onnxruntime build for your accelerator (CUDA, ROCm, Apple CoreML, DirectML; see the "Execution Providers" page of the onnxruntime documentation) and put that provider first in the `providers=[...]` list of the script. Other models work too (SigLIP, DINOv2 and others) as long as they obey the contract. Note that a different model means a different `model` string and vectors that cannot be mixed, so OpenAver will ask the user to rebuild the index.

### Keep it running and reachable

A server started in a terminal dies when the session ends or the machine reboots. Make it a service **and** make it reachable from the machine that runs OpenAver.

- **Bind `0.0.0.0`, not `127.0.0.1`.** The reference server above already does. Open the port in the host firewall for the LAN (for example `ufw allow 8000/tcp`; on Windows, an inbound rule for that TCP port).
- **OpenAver in Docker or on a NAS:** inside a container, `localhost` means the container itself. Give OpenAver the endpoint's **LAN IP** (`http://192.168.1.50:8000`), or a Docker network name if both run under the same compose file.
- **Linux, systemd, with root** (`/etc/systemd/system/openaver-embeddings.service`, then `systemctl enable --now openaver-embeddings`):

```ini
[Unit]
Description=OpenAver image embeddings
After=network-online.target

[Service]
ExecStart=/opt/openaver-embeddings/venv/bin/python /opt/openaver-embeddings/clip_server.py /opt/openaver-embeddings/vision_model_quantized.onnx 8000
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
```

- **Linux, systemd, without root** (a per-user service; save it as `~/.config/systemd/user/openaver-embeddings.service`). There is no `User=`, and `%h` means your home folder:

```ini
[Unit]
Description=OpenAver image embeddings
After=network-online.target

[Service]
ExecStart=%h/openaver-embeddings/venv/bin/python %h/openaver-embeddings/clip_server.py %h/openaver-embeddings/vision_model_quantized.onnx 8000
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
```

<!-- verify:skip -->
```bash
# start it now and at every login; "linger" makes it start at boot even when nobody is logged in
mkdir -p ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now openaver-embeddings
loginctl enable-linger "$USER"
```

- **macOS, launchd** (`~/Library/LaunchAgents/com.openaver.embeddings.plist`, then `launchctl load ~/Library/LaunchAgents/com.openaver.embeddings.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.openaver.embeddings</string>
  <key>ProgramArguments</key><array>
    <string>/Users/me/openaver-embeddings/venv/bin/python</string><string>/Users/me/openaver-embeddings/clip_server.py</string>
    <string>/Users/me/openaver-embeddings/vision_model_quantized.onnx</string><string>8000</string>
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
```

- **Windows, Task Scheduler** (run in an elevated prompt; use the full path of the Python that has the packages installed):

```bat
schtasks /Create /TN "OpenAver Embeddings" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "C:\openaver-embeddings\venv\Scripts\python.exe C:\openaver-embeddings\clip_server.py C:\openaver-embeddings\vision_model_quantized.onnx 8000"
```

- **Docker** (`Dockerfile` next to the two files, then `docker compose up -d`):

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir onnxruntime numpy pillow
COPY clip_server.py vision_model_quantized.onnx /app/
CMD ["python", "/app/clip_server.py", "/app/vision_model_quantized.onnx", "8000"]
```

```yaml
services:
  embeddings:
    build: .
    ports: ["8000:8000"]
    restart: unless-stopped
```

After setting up the service, restart it (or reboot), then **run the consistency test again from the machine that runs OpenAver** (or at least from another machine on the LAN).

### Cloud bridge

A hosted embeddings service can stand in for the self-hosted server, but most of them do not use the OpenAI request shape for images, so you need a thin adapter in front: a small program that exposes `POST /v1/embeddings` as above, converts the data URI to whatever the provider wants, calls the provider with its key, normalizes the vector and fills `model`. Example: Jina's CLIP models take images as `{"image": "<url or base64>"}` objects in `input` at `https://api.jina.ai/v1/embeddings`; check the provider's current documentation for the exact request and the size limits before you write the adapter (OpenAver has not tested any cloud provider). Remember that cover images then leave the user's network; tell the user.

## Faces（人臉）

OpenAver asks an endpoint you host to find the faces in a cover, so that wall thumbnails, the lightbox "re-detect" button and actress photos cropped from a cover can be centered on the face. If the endpoint is off or unreachable, OpenAver quietly falls back to its built-in method.

- **What is sent.** The **whole** cover (no left/right crop), rotated upright, longest side at most **650 px**, as a JPEG (quality 90) data URI. Only covers of uncensored titles whose focus point is automatic are sent; censored titles and covers the user focused by hand never are.
- **What you return.** Every face you find, as normalized boxes. OpenAver picks the main face itself.
- **Model name.** `model` is a required non-empty string that names the model and stays the same for every reply. OpenAver remembers which model produced each stored focus point. If the name changes, OpenAver re-focuses the whole library by itself the next time it sees the new name (after the settings-page test passes and the user presses Save, or during a scan). If you swap the underlying model but the name cannot change, ask the user to use the "刪除並重新對焦" button on the settings page.
- **Errors and timeouts.** Use normal HTTP codes. `4xx` is never retried; `5xx` and most timeouts are retried once. Timeouts run from 4 s (a manual click) to 30 s (background work); the first request of a test waits up to 90 s, so a cold model load is fine.

### Contract

`POST {EP}/v1/faces`:

```json
{"input": "data:image/jpeg;base64,...", "with_embedding": false}
```

```json
{"faces": [{"box": [0.41, 0.12, 0.2, 0.31], "score": 0.98, "embedding": null}], "model": "insightface-buffalo_l"}
```

- `box` is `[x, y, w, h]`, **normalized 0 to 1**, top-left corner plus width and height, relative to the image you received.
- No face found: reply `200` with `"faces": []`. It is not a 404, and it is not a 5xx: OpenAver stores "no face" as a real answer.
- `with_embedding` is a JSON boolean. OpenAver always sends `false`; reply with `"embedding": null`.
- Images are data URIs (`jpeg`/`png`/`webp`). Optional auth is `Authorization: Bearer <key>`, same as image similarity.

### curl

A 16x16 PNG has no face, so a healthy endpoint answers `200` with an empty `faces` list:

```bash
curl -s "$EP/v1/faces" \
  -H "Content-Type: application/json" \
  ${EP_KEY:+-H "Authorization: Bearer $EP_KEY"} \
  -d '{"input":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAGUlEQVR4nGOM6jnBQApgIkn1qIZRDUNKAwBVcQHO3mdG9AAAAABJRU5ErkJggg==","with_embedding":false}' \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print('model =', r['model'], '| faces =', len(r['faces']))"
```

### Consistency test

Four assertions, the same ones the settings page "Test" button runs:

1. `faces` is a list.
2. At least **1** face is found in the sample image.
3. The highest-scoring box has its center within **0.1** (normalized) of the known face center **(0.5, 0.3)**, on each axis.
4. `model` is a non-empty string.

The sample is a synthetic portrait (not a real cover) that lives in the OpenAver repository. The script below downloads it from GitHub, prepares it exactly as OpenAver does (upright, longest side at most 650 px, JPEG q90), and exits with code 0 only when all four assertions pass. It needs Python 3.9+ and Pillow. Save it as `check_faces.py`:

```python
#!/usr/bin/env python3
"""Consistency test for an OpenAver faces endpoint.

Usage: python check_faces.py http://HOST:PORT [API_KEY]
Needs: Python 3.9+ and Pillow. Exit code 0 = pass, 1 = fail.
"""
import base64, io, json, sys, urllib.request
from PIL import Image, ImageOps

BASE = sys.argv[1].rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else ""
RAW = "https://raw.githubusercontent.com/slive777/OpenAver/main/web/static/img/ai-samples/face-sample.jpg"
EXPECT_CENTER = (0.5, 0.3)  # known face center, normalized
TOLERANCE = 0.1             # allowed distance on each axis
MIN_FACES = 1


def sample():  # whole image, upright, long edge <= 650, JPEG q90
    im = Image.open(io.BytesIO(urllib.request.urlopen(RAW, timeout=30).read()))
    im = ImageOps.exif_transpose(im).convert("RGB")
    s = 650 / max(im.size)
    if s < 1:
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def detect(uri):
    req = urllib.request.Request(
        BASE + "/v1/faces",
        data=json.dumps({"input": uri, "with_embedding": False}).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + KEY} if KEY else {})},
    )
    return json.load(urllib.request.urlopen(req, timeout=90))


r = detect(sample())
faces, model = r.get("faces"), r.get("model")
is_list = isinstance(faces, list)
best = max(faces, key=lambda f: f["score"]) if is_list and faces else None
cx = cy = None
if best is not None:
    x, y, w, h = best["box"]
    cx, cy = x + w / 2, y + h / 2
checks = {
    "'faces' is a list": is_list,
    f"at least {MIN_FACES} face found": is_list and len(faces) >= MIN_FACES,
    f"best box center within {TOLERANCE} of {EXPECT_CENTER} on each axis": best is not None
    and abs(cx - EXPECT_CENTER[0]) <= TOLERANCE and abs(cy - EXPECT_CENTER[1]) <= TOLERANCE,
    "'model' is a non-empty string": isinstance(model, str) and model != "",
}
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"model={model} faces={len(faces) if is_list else '?'} center={None if cx is None else (round(cx, 3), round(cy, 3))}")
sys.exit(0 if all(checks.values()) else 1)
```

Run it with the Python that has Pillow:

```bash
python3 check_faces.py "$EP" ${EP_KEY:+"$EP_KEY"}
```

If you cannot reach GitHub, or the assistant runs on another machine than OpenAver and the user has switched on **server mode** (top of the settings page; if an access password is set, log in first), `GET {OA}/api/ai/sample/faces` returns the same sample ready to send: `{"inputs":[A],"expect":{"center":[0.5,0.3],"tolerance":0.1,"min_faces":1},"steps":[...]}`.

**Run the test again after a restart or reboot.** An endpoint that passes once and disappears at the next boot silently sends face finding back to the built-in method.

The settings page reports a failed test as "can't reach this address" or "reached it, but the reply breaks the contract" plus one of these check names: `http_4xx`, `auth` (401/403), `http_5xx`, `not_json`, `shape`, `box`, `score`, `no_model`, `no_face`, `center_off`.

### Self-host reference

OpenAver does not ship a server; the consistency test above is the acceptance test, so use whatever stack fits the machine.

- **Runtime.** onnxruntime on CPU is the floor and is enough. CoreML (Apple silicon), CUDA or MLX are optional accelerators.
- **Model.** Preferred: the SCRFD detector from insightface `buffalo_l` (`det_10g.onnx`), loaded **directly with onnxruntime** (you do not need the full insightface package). SCRFD is the most stable choice for small faces, side views and multi-person covers. RetinaFace-R50 is about as accurate and about twice as slow; YOLOv8-face is faster but weaker on side views. Report a stable `model` such as `insightface-buffalo_l`.
- **Where to get it.** One public copy of `det_10g.onnx` is `https://huggingface.co/immich-app/buffalo_l/resolve/main/detection/model.onnx` (about 17 MB; save it as `det_10g.onnx`). The input size is dynamic.
- **What your server has to do with SCRFD.** Letterbox the decoded RGB image to 640×640 (keep aspect ratio, pad bottom/right), normalize each channel as `(pixel - 127.5) / 128`, run the model, decode the three strides (8, 16, 32) with 2 anchors per cell (box = anchor center ± distance × stride), keep scores ≥ 0.5, apply NMS at IoU 0.4, then undo the letterbox scale and divide by the original width/height to get the normalized `box`.
- **License.** The insightface pretrained models are for **non-commercial research use only**; tell the user before installing them.

Four things that bit a real Mac Mini setup:

1. **EXIF.** Do not rotate the image by its EXIF tag. OpenAver already sends it upright, and the box must be relative to the pixels you decode.
2. **`with_embedding`.** Read it as a JSON boolean. Do not pass the raw value to code that treats any non-empty value as true.
3. **Cold start.** The first request after the model was idle or just loaded can take 1.5 to 3 seconds. Keep the model loaded between requests.
4. **Worker timeouts.** If your server runs the model in worker processes with a time limit, answer a worker that timed out (`worker_timeout`) with `503`, not with `200` and an empty `faces` list. An empty list means "no face found" and OpenAver stores it; a `503` is retried once and then falls back to the built-in method.

### Keep it running and reachable

Same rules as image similarity (see **Keep it running and reachable** under *Image similarity* above): bind `0.0.0.0`, open the firewall, use the LAN IP when OpenAver runs in Docker or on a NAS, and register the service with systemd, launchd, Task Scheduler or Docker `restart: unless-stopped`. Those examples start `clip_server.py`; replace the script name, service name and port with your face server's. If OpenAver runs on the same machine, binding `127.0.0.1` is enough.

### Cloud bridge

None verified yet. If you build one, remember that cover images then leave the user's network; tell the user.

## OpenAver endpoints for assistants

These endpoints run on the machine that hosts OpenAver (`$OA`). `GET $OA/api/capabilities` lists them with their risks, and tells you how to authenticate when the user has set an access password. From another machine the user must first switch on **server mode** at the top of the settings page.

#### Get the sample images

```bash
curl -s "$OA/api/ai/sample/embeddings" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['inputs']), 'inputs;', d['expect'])"
```

#### Run the consistency test against the saved settings

An empty body tests what the user saved on the settings page. Pass `url`, `api_key` and `model` to test something else. This writes nothing.

```bash
curl -s -X POST "$OA/api/ai/similar/test" -H "Content-Type: application/json" -d '{}'
```

Example reply (the exact values depend on the endpoint):

```json
{
  "ok": true,
  "elapsed_ms": 296,
  "model": "clip-vit-base-patch32",
  "dim": 512
}
```

Failure replies carry `"ok": false` plus `kind` (`unreachable` or `contract`) and `check` (one of the names listed above).

#### Check the index status

```bash
curl -s "$OA/api/ai/similar/status"
```

```json
{
  "running": true,
  "job_kind": "build",
  "done": 160,
  "indexed": 160,
  "total": 2308,
  "pending": 2148,
  "unreadable": 0,
  "unreachable": false,
  "kind": null,
  "check": null,
  "model": "clip-vit-base-patch32",
  "last_success_at": 1793402847.8335638,
  "model_changed": false,
  "complete": false
}
```

- `running`: an index job is running right now (`job_kind` says whether it is a full `build` or an `incremental` top-up after a scan).
- `indexed` and `total`: covers that already have a vector, and covers in the library.
- `pending`: covers still waiting. `running: false` with `pending > 0` means the index is incomplete (stopped, interrupted, or new covers arrived).
- `unreadable`: covers whose image file could not be read and were skipped. `indexed + unreadable + pending = total`. Calling `POST $OA/api/ai/similar/index` again retries them once (for example after a NAS comes back).
- `unreachable`: the endpoint could not be reached the last time OpenAver tried.
- `model_changed`: the endpoint now answers with a different `model` than the index was built with; the index must be rebuilt.

#### Build or rebuild the index (ask the user first)

Sends roughly one request to the user's endpoint for every cover in the library (thousands), and if the model changed it replaces the existing vectors. **Get the user's confirmation before calling it.** It runs the consistency test first and refuses to start when the test fails. The reply has `status` set to `started`, `already_running`, or `test_failed` (the last one also carries `kind` and `check`). The settings page has a Stop button; stopping keeps what is already computed, and starting again only fills in the missing ones and gives covers that could not be read one more try.

```bash
curl -s -X POST "$OA/api/ai/similar/index"
```

```json
{
  "ok": true,
  "status": "started"
}
```

#### Delete and rebuild the index (ask the user first)

Use this only when the user says the model behind the endpoint was swapped but the reported `model` name stayed the same (otherwise the call above is enough). It runs the consistency test first and **deletes nothing if the test fails**; if it passes, it **deletes every stored vector** and recomputes all of them, so it sends one request per cover (thousands, tens of minutes). Until it finishes, similar-cover results use the rule-based ordering. It refuses while an index job is running. **Get the user's confirmation before calling it.** The reply has the same `status` values as the call above.

```bash
curl -s -X POST "$OA/api/ai/similar/index/rebuild"
```

#### Faces: get the sample image

```bash
curl -s "$OA/api/ai/sample/faces" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['inputs']), 'input;', d['expect'])"
```

`inputs[0]` is the sample as a data URI ready to send (upright, longest side at most 650 px, JPEG). `expect` is `{"center": [0.5, 0.3], "tolerance": 0.1, "min_faces": 1}`.

#### Faces: run the consistency test against the saved settings

An empty body tests what the user saved on the settings page (AI features › Faces). Pass `url`, `api_key` and `model` to test something else. This writes nothing and does not start any re-focusing.

```bash
curl -s -X POST "$OA/api/ai/faces/test" -H "Content-Type: application/json" -d '{}'
```

```json
{
  "ok": true,
  "elapsed_ms": 412,
  "model": "insightface-buffalo_l"
}
```

Failure replies carry `"ok": false` plus `kind` (`unreachable` or `contract`) and `check` (one of the names listed under the Faces consistency test). Once a test passes and the user presses Save on the settings page, OpenAver re-focuses the whole library by itself; you do not need to start it, and it is not offered to assistants.

#### Faces: check the status

```bash
curl -s "$OA/api/ai/faces/status"
```

```json
{
  "using": "external",
  "observed": true,
  "last_success_at": 1793402847.8335638,
  "running": true,
  "job_kind": "model_change",
  "processed": 120,
  "total": 480,
  "pending": 360,
  "unreadable": 0,
  "stopped_reason": null,
  "kind": null,
  "check": null,
  "target_model": "insightface-buffalo_l"
}
```

- `using`: `external` when OpenAver is using the endpoint; `local` when it uses the built-in method (the feature is off, or the endpoint is unreachable; then `kind` and `check` say why).
- `observed`: OpenAver has had at least one successful reply from the endpoint. `last_success_at` is when (Unix seconds).
- `running`, `processed`, `total`, `pending`: the library-wide re-focus job. `running: false` with `pending > 0` means it stopped or was interrupted; the user can continue it on the settings page. `stopped_reason` says why it stopped (for example the endpoint became unreachable).
- `unreadable`: covers whose image file could not be read and were skipped.
