# 在 Linux 伺服器上跑 OpenAver

這份文件寫給想把 OpenAver 架在**家裡那台沒有螢幕的 Linux 機器**上的人：舊主機、NAS、
Proxmox LXC（輕量的虛擬機器）、樹莓派都算。貼一行指令就裝好，之後你用**同一個網段內其他裝置的瀏覽器**操作它。

> ⛔ **不要架在公開的雲端主機上**（VPS、有公網 IP 的機器）。
> 理由見下方的安全警告——這不是「不建議」，是這套軟體的門禁根本不是為那種場景設計的。

> 🔒 **安裝之前務必看完這段。**
>
> 伺服器模式（讓其他裝置也連得進來的開關）的門禁只分兩種來源：**本機**，以及**其他所有人**。
> 安裝器已自動開啟伺服器模式，所以凡是連得到這台機器的 `49152` port 的裝置**一律放行**——
> 它**不會**去檢查對方是不是真的在你家網段內。家裡的智慧電視、訪客的手機、
> 室友的筆電都算；而如果這個 port 從網際網路連得到，**那就是全世界都算**。
>
> 所以：
>
> - **不要**把 `49152` port 轉發（port forward，在路由器上把外面的連線導進這台機器）到網際網路上
> - **不要**架在有公網 IP 的雲端主機上
> - 真的需要在外面看，請走 **Tailscale**（免費的私人網路）、WireGuard、Zero Trust 這類把裝置拉進私有網路的方式，
>   而不是把服務開到公網
> - 家裡有人共用網路的話，裝好後設一組連線密碼（見下方〈連線與設密碼〉）
>   （**預設是關閉的**，不設就等於沒有密碼）

---

## 需求

- **系統**：64 位元 Linux（x86_64），glibc 2.28 以上（Debian 10、Ubuntu 20.04、RHEL 8 之後都符合）；**不用先裝 Python**，套件已內附。
- 不支援 Alpine 這類 musl 系統（安裝器會直接告訴你並停下來）。
- `curl` 與 `tar`（幾乎所有 Linux 都內建）
- 影片檔所在的資料夾，這台機器讀得到

---

## 一行安裝

用**一般使用者**帳號（不是 root）登入這台機器（SSH 進去就可以），貼上這一行：

```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**你會看到什麼**（安裝畫面跟著系統語言走，以下以繁體中文為例）：

1. 下載進度，接著出現「✅ 安裝完成！」。
2. 一個問題：「要設定開機自動啟動嗎？(Y/n)」。直接按 Enter 就是要——機器重開之後 OpenAver 會自己起來。
   （如果是在沒有終端機的環境跑，例如腳本或自動化，它不會問，會印「沒有終端機，預設開啟自動啟動」並直接開啟。）
3. 最後印出「OpenAver 已啟動」和一行網址，例如 `http://192.168.1.100:49152`——這就是等一下要在別台裝置打的網址。

程式裝在 `~/OpenAver`（內含 Python）；你的設定、片庫資料庫、封面都在 `~/OpenAver/output/`，升級不會動它們。
另外會在 `~/.local/bin` 放一個 `openaver` 指令，後面所有操作都用它。

**開機自動啟動要注意兩件事：**

- 它靠 systemd（Linux 管背景服務的標準機制）。這台機器沒有 systemd、或 systemd 使用者服務不可用時，
  安裝器會告訴你「這台機器的 systemd 使用者服務不可用，無法設定開機自動啟動；請改用 openaver start 手動啟動」，
  OpenAver 這次仍然會啟動，只是**重開機後要自己再打一次 `openaver start`**。
- 服務已登記、但你的帳號沒有 linger（讓登出後服務也繼續跑的設定）時，登出或重開機後服務會停。
  安裝器會先自己試著處理；處理不了就會印出一行以「注意：服務已登記，但登出後會停止、重開機後不會自己起來」開頭的提醒，
  請用有管理權限的帳號執行一次：

  ```bash
  sudo loginctl enable-linger <你的帳號>
  ```

  （`<你的帳號>` 換成你登入用的名字，`whoami` 印得出來。`openaver status` 也會再提醒一次。）

如果這台機器以前照舊版文件手動裝過（`~/OpenAver` 裡有 `venv/`），安裝器會偵測到並改裝，見最下面的附錄 A。

---

## 連線與設密碼

**1. 取得網址。** 在伺服器上打：

```bash
openaver url
```

你會看到兩行，例如：

```
http://192.168.1.100:49152
桌面 App 側欄連線填這個網址
```

**2. 在另一台裝置連線。** 同一個 Wi-Fi／區網內的手機、平板、電腦，用瀏覽器打開上面那個網址，就會看到 OpenAver 的畫面（第一次會有新手導覽）。
如果你用桌面 App，在側欄「連線」填同一個網址即可。

**如果它說「查不到區網 IP，請用 hostname -I 或 ip addr 自行確認」**：機器沒有對外預設路由時（純內網、沒接網際網路的環境）會查不到。改用系統指令：

```bash
hostname -I
```

它會把這台機器所有的位址一次列出來，例如 `192.168.1.100 172.17.0.1`——
**挑那個跟你其他裝置同網段的**（通常是 `192.168.x.x` 或 `10.x.x.x` 開頭那個），網址就是 `http://<那個位址>:49152`。
`172.17.x.x` 通常是 Docker 的虛擬網卡，不是你要的。真的分不出來就去路由器的
裝置清單看這台機器被分到哪個 IP。

**3. 設密碼（建議）。** 在瀏覽器開「設定」頁，頁面上方勾選「需要密碼才能連線」，
旁邊會出現密碼欄，輸入密碼（4 位英文或數字，區分大小寫），按「儲存」。
成功會顯示「密碼設定已儲存」。之後其他裝置連進來都要先輸入這組密碼。

---

## `openaver` 指令

| 指令 | 做什麼 |
|---|---|
| `openaver run` | 前景執行（關掉終端機就停）。服務與 `start` 內部用，一般不必直接跑 |
| `openaver start` | 在背景啟動，成功會印「OpenAver 已啟動」；已經在跑會印「OpenAver 已在執行」 |
| `openaver stop` | 停止：先請它自己結束，等 20 秒還沒停才強制結束，成功印「OpenAver 已停止」（已登記開機自動啟動時交給 systemd 停） |
| `openaver restart` | 先停再啟動 |
| `openaver status` | 印「狀態：在跑」或「狀態：沒跑」，加上版本、服務是否已登記、port。在跑時結束碼是 0，沒跑是 3 |
| `openaver log` | 即時看日誌（`debug.log` 與 `server.log` 最後 50 行，之後持續跟著新增），按 `Ctrl-C` 離開 |
| `openaver url` | 印區網網址 |
| `openaver config port <n>` | 改 port，範圍 1024 到 65535；存下後要 `openaver restart` 才生效 |
| `openaver reset-password` | 忘記密碼時用，見下一節 |
| `openaver autostart on` ／ `off` | 開／關開機自動啟動 |
| `openaver update [vX.Y.Z]` | 升級（或換成指定版本），見〈升級〉 |

port 固定是 `49152`，**不會**被占用時自動往後找。被別的程式占了的話：

- 沒登記開機自動啟動：`openaver start` 會當場告訴你
  「port 49152 被占用，OpenAver 沒有啟動。換一個 port：openaver config port <n>，再執行 openaver start」。
- 已登記開機自動啟動：可能只看到「啟動逾時，詳見 logs/server.log」，不一定會明講 port 被占。
  這時看 `openaver log`，或直接 `openaver config port <n>` 換一個 port，再 `openaver restart`。

如果打 `openaver` 說找不到指令，是因為 `~/.local/bin` 不在你的 PATH 裡（安裝器結尾會提醒「提示：請把 ~/.local/bin 加入 PATH」）。
可以先改打完整路徑 `~/OpenAver/openaver`，或把 `~/.local/bin` 加進 PATH。

---

## 忘記密碼 / 被鎖在外面

輸錯太多次密碼會觸發逐步拉長的鎖定（最長一小時）。不想等、或根本忘了密碼，
**在伺服器本機**跑這行：

```bash
openaver reset-password
```

服務在跑的話，它會自己重啟一次，然後印「密碼保護已關閉、所有裝置已登出」，**立即生效**。
效果是：密碼保護關閉、鎖定解除、所有已登入的裝置與 AI 助理的連線憑證一併失效。
之後想再設密碼，照〈連線與設密碼〉第 3 步重設即可。

服務目前沒在跑的話，它會印「已標記重設密碼，下次啟動生效（openaver start）」，等你下次 `openaver start` 就生效。

---

## 升級

```bash
openaver update
```

這會下載最新版並換上去。你會看到：

- 約 10 到 20 秒這段時間沒有服務，之後自動恢復，**瀏覽器不用重新登入**。
- 設定、片庫、密碼都不會動（都在 `~/OpenAver/output/`）。
- 換好之後如果新版起不來，會自動退回升級前的版本。
- 已經是最新版時，會印「已是最新版本（x.y.z），沒有需要更新的」，什麼都不動。

**另一種做法**：重貼〈一行安裝〉那一行指令。效果相同——裝過的機器會走升級，不會當成全新安裝。

**指定版本或退回舊版**：

```bash
openaver update vX.Y.Z
```

把 `X.Y.Z` 換成想要的版號（可以到 [Releases 頁面](https://github.com/slive777/OpenAver/releases)查）。
只能選有 Linux 版的版本，也就是 0.18.14 起；更舊的會印「這個版本（vX.Y.Z）沒有 Linux 版」。

**沒有「一鍵更新」按鈕。** 說明頁與通知中心有新版時，會提示你在主機執行 `openaver update`。
瀏覽器、桌面 App、AI 助理都不能觸發更新——只有在這台主機上打指令才算數，這是刻意的安全護欄，不是壞掉。

---

## 疑難排解

- **連不進去、瀏覽器顯示無法連線** → 先在伺服器上打 `openaver status`，確認是「狀態：在跑」。
  再檢查防火牆有沒有放行 49152（例如 `sudo ufw allow 49152/tcp`）。如果你改過 port，網址要用 `openaver url` 印出來的新的。
- **連得到但顯示 `Forbidden`** → 代表伺服器模式沒有開著。安裝器每次安裝或升級都會自動開啟它，
  所以通常是設定檔（`~/OpenAver/output/config.json`）被刪掉或手動改過。修法是重裝同一個版本讓它再開一次：
  `openaver update vX.Y.Z`，版號填 `openaver status` 印的「版本」前面加 `v`。
  （不指定版號的 `openaver update` 在已是最新版時會直接略過，不會重新開啟。）
- **一直停在登入畫面** → 忘了密碼，見上面〈忘記密碼〉：`openaver reset-password`。
- **啟動不了，或 `openaver status` 結束碼是 3** → 看日誌：`openaver log`，或直接打開 `~/OpenAver/logs/server.log`。
  如果是 port 被占，`openaver start` 會直接告訴你，照它說的 `openaver config port <n>` 換一個，再 `openaver start`。
  已登記開機自動啟動的話，port 被占時你看到的會是「啟動逾時，詳見 logs/server.log」，原因寫在 `server.log` 裡，處理方式一樣。
- **登出或重開機之後服務停了** → 帳號沒有 linger，請用有管理權限的帳號執行一次：

  ```bash
  sudo loginctl enable-linger <你的帳號>
  ```

- **升級失敗或中斷：先試 `openaver update`；若指令本身跑不動，重貼安裝那一行。** 依你看到的畫面：
  - 「無法取得安裝程式（請檢查網路），沒有動任何檔案」→ 沒動任何東西，網路通了再試一次就好。
  - 「這次沒有完成，已還原成這次之前的版本與服務狀態」→ 已經退回升級前的版本，可以照常使用；原因看它上面的訊息或 `~/OpenAver/logs/server.log`。
  - 「還原沒有完全成功」→ 舊版的檔案可能還在 `~/OpenAver/.prev` 裡，**先不要刪**，處理好之後再重貼安裝那一行。
- **其他** → 日誌在 `~/OpenAver/logs/debug.log` 與 `~/OpenAver/logs/server.log`；開 issue 時附上就好查很多。

---

## 其他

- **別用 root 裝。** root 寫進你片庫的 NFO（記著片名、女優、標籤的資料檔）和封面，之後你自己的帳號改不動。
  安裝器偵測到你是 root 會提醒，但不會擋你。
- ARM64 有打包但未在實機測試過，遇到問題請[開 issue](https://github.com/slive777/OpenAver/issues)。

---

## 附錄 A　不想用內附 Python 的人

### 舊手動安裝想改用一行安裝

如果你以前照舊版文件手動裝過（`~/OpenAver` 裡有 `venv/`），直接貼上面的一行安裝即可。它會先問你一次「要繼續改裝嗎？(y/N)」，同意後：

- 舊的程式檔與 `venv/` 會搬到 `~/OpenAver/.old-install/`，確認沒問題可以自己刪。
- `output/`（設定、片庫、封面）和你自己放在裡面的東西都不動。

**沒有終端機時**（腳本、自動化）它問不了，會直接拒絕。要同意的話加上 `OPENAVER_YES=1`：

```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | OPENAVER_YES=1 bash
```

（或寫成 `... | bash -s -- --yes`。）

**舊的 systemd 服務要先停掉。** 舊服務還在跑時，安裝器會請你先關；沒有終端機的話則直接拒絕。停法：

```bash
sudo systemctl disable --now openaver
```

之後想把舊服務移除，再刪掉 `/etc/systemd/system/openaver.service`，並跑 `sudo systemctl daemon-reload`。

### 手動安裝（自備 Python）

不想用內附的 Python、想自己管環境的話，可以照下面做。這條路**沒有 `openaver` 指令**，啟動、升級、重設密碼都要自己打指令。
它和一行安裝用同一個 `~/OpenAver`，二擇一。上方的公網警告同樣適用，只是這裡的 port 是 `8000`。

需要 Python 3.12 與 `venv` 模組（Debian／Ubuntu：`sudo apt install python3.12 python3.12-venv`），以及 `curl`、`tar`。

下載最新正式版、解壓、裝套件：

```bash
LATEST=$(curl -fsSL https://api.github.com/repos/slive777/OpenAver/releases/latest \
         | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)

mkdir -p ~/OpenAver && cd ~/OpenAver
curl -fsSL "https://github.com/slive777/OpenAver/archive/refs/tags/$LATEST.tar.gz" \
  | tar xz --strip-components=1

python3 -m venv venv
grep -v '^pywebview' requirements.txt > /tmp/openaver-req.txt
venv/bin/pip install -r /tmp/openaver-req.txt
```

`pywebview` 是桌面版開視窗用的，沒有圖形環境的機器裝不起來也用不到，所以排除。

開啟伺服器模式（只需做一次；不開的話，其他裝置連進來一律拿到 `403 Forbidden`）：

```bash
venv/bin/python -c "from core.data_layout import bootstrap_data_layout; bootstrap_data_layout(); from core.config import mutate_config; mutate_config(lambda c: c.setdefault('general', {}).__setitem__('server_mode', True))"
```

啟動（前景執行，關掉終端機就停）：

```bash
venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

網址是 `http://<這台機器的區網 IP>:8000`，IP 用 `hostname -I` 查。

開機自動啟動（systemd）：

```bash
sudo tee /etc/systemd/system/openaver.service > /dev/null <<'EOF'
[Unit]
Description=OpenAver
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=CHANGE_ME
WorkingDirectory=/home/CHANGE_ME/OpenAver
ExecStart=/home/CHANGE_ME/OpenAver/venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now openaver
```

三個 `CHANGE_ME` 換成你的使用者名稱（`whoami`），`User=` 要填讀得到影片資料夾的那個使用者。

升級：把上面「下載、解壓、裝套件」那段再跑一次（蓋在原目錄上，`output/` 不受影響），然後重啟（`sudo systemctl restart openaver`）。

忘記密碼：

```bash
venv/bin/python -c "from core.access_auth import set_auth; set_auth(enabled=False, pin='')"
```

⚠️ **跑完一定要重啟伺服器**，否則沒有效果——執行中的伺服器把密碼設定快取在記憶體裡，不會發現另一個行程改了資料庫。

---

## 附錄 B　Docker（實驗性，官方 image 規劃中）

> **先說結論：不想折騰的話，別用這段。**
> 上面的 CLI 安裝功能完全一樣，而且步驟更少。
> **官方 Docker image 已在規劃中**——等它出來再用，是完全合理的選擇。

**在 NAS 上未驗證，僅供參考。** 下面這份設定在 **x86_64 Linux + Docker 29** 上實際建置並
執行過（網頁開得起來、設定存得進去），但**沒有**在 Synology／QNAP／樹莓派這類目標 NAS
環境上跑過，也沒有長期使用的驗證。路徑、UID、port 都要照你的環境改。

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN grep -v '^pywebview' requirements.txt > /tmp/req-server.txt \
 && pip install --no-cache-dir -r /tmp/req-server.txt \
 && rm /tmp/req-server.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

同一層放一份 `.dockerignore`，否則 `COPY . .` 會把 `venv/`、`output/`、`.git/` 一起塞進 image：

```
.git
venv
output
node_modules
tests
```

### docker-compose.yml

```yaml
services:
  openaver:
    build: .
    ports:
      - "8000:8000"
    # 換成你自己的：id -u 與 id -g 印出來的數字。理由見下方〈UID/GID〉
    user: "1000:1000"
    environment:
      # 不能省，理由見下方〈為什麼要設 HOME〉
      - HOME=/app
    volumes:
      # 整個專案目錄掛進去，不是只掛設定檔。理由見下方〈為什麼掛整個目錄〉
      - ./:/app
      # 你的片庫（左邊換成實際路徑；右邊那個路徑就是你在 OpenAver 裡會看到的路徑）
      - /srv/media/av:/media/av
    restart: unless-stopped
```

### 啟動

```bash
LATEST=$(curl -fsSL https://api.github.com/repos/slive777/OpenAver/releases/latest \
         | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)

mkdir -p ~/OpenAver && cd ~/OpenAver
curl -fsSL "https://github.com/slive777/OpenAver/archive/refs/tags/$LATEST.tar.gz" \
  | tar xz --strip-components=1

# 把上面三份檔案（Dockerfile / .dockerignore / docker-compose.yml）放進這個目錄，然後：
echo '{"general": {"server_mode": true}}' > web/config.json
docker compose up -d --build
```

**`server_mode` 必須先開。** 從 host 或別台裝置連進容器時，來源位址是 Docker 的橋接網段
（`172.17.0.1` 之類，不是 loopback），沒開伺服器模式一律 `403 Forbidden`——實測如此。

### 升級

程式碼是從 host 掛進去的，所以升級不必重建 image：

```bash
LATEST=$(curl -fsSL https://api.github.com/repos/slive777/OpenAver/releases/latest \
         | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)

cd ~/OpenAver
curl -fsSL "https://github.com/slive777/OpenAver/archive/refs/tags/$LATEST.tar.gz" \
  | tar xz --strip-components=1
docker compose restart
```

你自己寫的 `Dockerfile`、`.dockerignore`、`docker-compose.yml` 不在壓縮檔裡，覆蓋解壓不會蓋掉它們。

只有 `requirements.txt` 有變動時才需要 `docker compose up -d --build`。

### 為什麼掛整個目錄，不是只掛設定檔

直覺上會想寫 `- ./data/config.json:/app/web/config.json` 只掛一個檔案。**那樣會壞。**

OpenAver 存設定用的是「先寫暫存檔再 `os.replace` 換過去」的原子寫入，
而 Docker 的單一檔案 bind mount 擋掉 `os.replace`，實測噴：

```
OSError: [Errno 16] Device or resource busy: '/app/web/tmpXXXX.tmp' -> '/app/web/config.json'
```

症狀是**網頁直接 500**，不是「設定沒存到」這種好認的樣子。
把整個專案目錄掛進去，設定檔（`output/config.json`）就是目錄裡的普通檔案，這個問題不存在，
資料庫與其他資料（同在 `output/`）也一併留在 host 上。

### 為什麼要設 HOME

OpenAver 的日誌寫在 `~/OpenAver/logs/`。而 `user:` 指定一個容器內 `/etc/passwd` 沒有的
UID 時，`HOME` 會變成 `/`，程式一啟動就想在根目錄建資料夾：

```
PermissionError: [Errno 13] Permission denied: '/OpenAver'
```

容器**連起都起不來**。設 `HOME=/app` 之後日誌會落在專案目錄下的 `OpenAver/logs/debug.log`。

### UID/GID：容器化自架媒體庫最常見的隱形雷

比路徑掛錯更難查的是權限。host 端資料夾的擁有者，跟容器內執行程式的使用者 UID/GID 對不上時：

- **讀不了** → 掃描跑完「找到 0 部影片」，但路徑明明是對的
- **寫不了** → 掃到了，但 NFO 和封面存不進去，或整理／改名靜默失敗

兩種都很像「路徑掛錯」，成因卻完全不同。

**反過來也一樣糟：不設 `user:` 的話容器用 root 跑**，它寫出來的 `config.json`、資料庫、
還有寫進你片庫的 NFO 與封面**全部變成 root 所有**——你自己的帳號從此改不動那些檔案，
得 `sudo chown` 才救得回來。這是實測踩到的，不是假設。

做法是先查出你自己與片庫資料夾的 UID/GID：

```bash
id -u; id -g                      # 你自己
stat -c '%u:%g' /srv/media/av     # 片庫資料夾的擁有者
```

兩邊一致的話，把那組數字填進 compose 的 `user:` 就好。不一致的話，
填的那個 UID 必須對片庫資料夾有讀取權限（要 OpenAver 寫 NFO／封面的話還要寫入權限），
專案目錄本身也一樣。
