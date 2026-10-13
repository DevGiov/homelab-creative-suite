# Piano Operativo di Implementazione: Creative Suite Workstation su Proxmox VE

Questo documento definisce in dettaglio tutte le specifiche tecniche, i comandi operativi, le configurazioni di sistema e i vincoli architetturali per la messa in produzione della **Creative Suite Workstation** su Proxmox VE con **Sunshine**, **Moonlight-Web-Stream** e l'integrazione di **Live Co-Authoring** con **`homelab-agent`**.

---

## 1. Parametri di Configurazione del Sistema

### 1.1 Specifiche Host e Container Target
| Parametro | Valore Assegnato | Giustificazione Tecnica / Riferimento Docs |
| :--- | :--- | :--- |
| **Proxmox VE Host** | `DESKTOP-PGMTM0B` (`192.168.1.69`) | Hypervisor fisico con Intel i7-5820K e NVIDIA Tesla V100 16GB. |
| **Target Container VMID** | **`144`** | Prossimo VMID libero progressivo (dopo CT 143 `alt-server`). |
| **Hostname Container** | `creative-workstation` | Identificativo univoco in Proxmox e nel log di rete. |
| **Template di Origine** | **CT 133 (`GpuAgy`)** | Template già predisposto con regole cgroup2 per passthrough GPU Tesla V100. |
| **Storage Pool Rootfs** | **`SSD2`** (`/dev/sda`) | **Regola Aurea dello Storage**: non usare `NassLocal` (disco difettoso). `SSD2` ha >440 GB liberi. |
| **Dimensione Disco Rootfs** | `32 GB` (iniziale) | Spazio abbondante per dipendenze Xorg, librerie, Sunshine e build della suite. |
| **Allocazione CPU** | `6 Core` | Bilanciamento sui 12 thread dell'host per compilazione e rendering fluido. |
| **Allocazione RAM / Swap** | `8 GB RAM` / `2 GB Swap` | Salvaguardia memoria host (rimangono ~5-6 GB liberi su 20 GB fisici). |
| **Indirizzo IP Statico** | **`192.168.1.189/24`** | IP verificato libero (il `.187` è occupato da device fisico LAN, `.188` è CT 143). |
| **Gateway & DNS** | `192.168.1.1` / `192.168.1.170` | Default gateway LAN e resolver DNS Pi-hole (CT 114). |

---

## 2. Architettura dei Componenti nel Container CT 144

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CT 144: creative-workstation (192.168.1.189 su SSD2)                                  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ GPU Passthrough Driver Userspace (NVIDIA 550.144.03 - libcuda, libnvidia-encode) │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
│                                           │                                            │
│  ┌────────────────────────────────────────┴─────────────────────────────────────────┐  │
│  │ Display Server Headless: Xorg con driver dummy (1920x1080@60Hz / 2560x1440)       │  │
│  │ Window Manager: Openbox o XFCE Session                                            │  │
│  │ Audio Server: PipeWire con Loopback Sink virtuale                                 │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
│                                           │                                            │
│  ┌────────────────────────────────────────┴─────────────────────────────────────────┐  │
│  │ Sunshine Host Daemon (systemd service)                                            │  │
│  │  - Cattura video X11 diretta + Codifica NVENC a < 3ms latenza                     │  │
│  │  - Cattura audio PipeWire loopback                                                │  │
│  │  - Porte native GameStream: 47984-47990, 48010                                    │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
│                                           │ Loopback GameStream (localhost)            │
│                                           ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Moonlight-Web-Stream (Docker Container / Processo Rust)                           │  │
│  │  - Web Server & Interfaccia utente browser (Porta HTTP 8080)                     │  │
│  │  - WebRTC Gateway & DataChannel (Porte UDP 40000-40100)                           │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Applicazioni Creative Suite in Background (Porte IPC Controllo)                  │  │
│  │  - DeckCraft  (--control 7979)                                                    │  │
│  │  - WordCraft  (--control 7981)                                                    │  │
│  │  - PhotoCraft (--control 7878)                                                    │  │
│  │  - VectorCraft (--control 7980)                                                   │  │
│  │  - CADCraft    (--control 7982)                                                   │  │
│  │  - SoundCraft  (--control 7801)                                                   │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Piano Dettagliato delle Fasi Operative

### Fase 2: Provisioning e Configurazione Base del Container (CT 144) (COMPLETATO ✅)
1. **Clonazione da Template**:
   Esecuzione del comando di clonazione tramite Proxmox CLI:
   ```bash
   pct clone 133 144 --hostname creative-workstation --storage SSD2 --full 1
   ```
2. **Dimensionamento Risorse & Configurazione Rete**:
   ```bash
   pct set 144 -cores 6 -memory 8192 -swap 2048
   pct resize 144 rootfs 32G
   pct set 144 -net0 name=eth0,bridge=vmbr0,firewall=1,gw=192.168.1.1,ip=192.168.1.189/24
   pct set 144 -nameserver 192.168.1.170 -searchdomain deggio.local
   pct set 144 -features nesting=1,keyctl=1
   ```
3. **Mount Storage Condiviso Progetti**:
   Creazione di una cartella progetti su storage persistente e bind-mount in `/workspace`:
   ```bash
   pct set 144 -mp0 /Nass/Nasss/Homelab/creative_suite,mp=/workspace
   ```
4. **Verifica GPU Passthrough**:
   Avvio del container e verifica dei nodi NVIDIA:
   ```bash
   pct start 144
   pct exec 144 -- nvidia-smi
   ```

---

### Fase 3: Ambiente Desktop Headless, Audio & Sunshine Server (COMPLETATO ✅)
1. **Installazione Pacchetti Grafici Headless & Window Manager**:
   Installazione di Xorg con driver dummy e Openbox per la gestione delle finestre:
   ```bash
   pct exec 144 -- apt update
   pct exec 144 -- apt install -y xserver-xorg-video-dummy x11-xserver-utils openbox dbus-x11 pipewire pipewire-media-session libuinput1
   ```
2. **Configurazione Xorg Dummy Display**:
   Configurazione di `/etc/X11/xorg.conf` con risoluzioni 1920x1080@60Hz e 2560x1440@60Hz con profondità di colore 24-bit.
3. **Configurazione Audio Virtuale**:
   Attivazione di PipeWire con sink virtuale per catturare l'output audio delle applicazioni e inoltrarlo allo stream (`/run/user/0/pipewire-0`).
4. **Installazione e Setup Sunshine**:
   - Installato pacchetto ufficiale LizardByte Sunshine `v2026.914.233613`.
   - Configurato `/root/.config/sunshine/sunshine.conf` con `system_tray = false` e logging `verbose`.
   - Credenziali Web manager: `admin / homelabcreative`.
   - Servizi systemd configurati con avvio automatico all'accensione del container.

---

### Fase 4: Gateway WebRTC (Moonlight-Web-Stream) & Routing di Rete (COMPLETATO ✅)
1. **Deployment di Moonlight-Web-Stream**:
   - Creata la directory `/opt/moonlight-web` in CT 144.
   - Configurato `docker-compose.yaml` (immagine `mrcreativ3001/moonlight-web-stream:latest`, `network_mode: host`):
     - Bind address: `0.0.0.0:8080`
     - WebRTC UDP range: `40000-40100`
     - Variabile `WEBRTC_NAT_1TO1_HOST=192.168.1.189`
   - Risolto limite quota chiavi sessione kernel host Proxmox (`kernel.keys.maxkeys = 1000000`).
   - Configurato utente `admin / homelabcreative` su Moonlight-Web.
2. **Pairing Sunshine ➔ Moonlight-Web**:
   - Eseguito handshake crittografico via API `/api/pair` e Sunshine `/api/pin`.
   - Host `creative-workstation` convalidato e accoppiato in stato `Paired` / `Free`.
   - Applicazioni rilevate: `Desktop`, `Low Res Desktop`, `Steam Big Picture`.
3. **Configurazione DNS Locale (Pi-hole - CT 114)**:
   - Creato record A: `creative.deggio.local` ➔ `192.168.1.143` (IP di NpmLocal CT 121).
4. **Configurazione Reverse Proxy (NpmLocal - CT 121)**:
   - Creato Proxy Host: `creative.deggio.local` verso `http://192.168.1.189:8080`.
   - Abilitato supporto WebSockets (`allow_websocket_upgrade: true`).

---

### Fase 5: Registrazione MetaMCP (CT 107) & Live Co-Authoring via Universal Gateway
1. **Compilazione Nativa ed Esecuzione Sessione (CT 144)**:
   - Compilati con Rust 1.99 su Ubuntu 22.04 LTS:
     - `/opt/creative-suite/bin/deckcraft` (Desktop presentation GUI)
     - `/opt/creative-suite/bin/deckcraft-cli` (CLI headless e bridge IPC loopback TCP)
     - `/opt/creative-suite/bin/wordcraft-cli` (CLI headless e doc processor)
   - Avviata sessione desktop Openbox su display virtuale `:0`, con DeckCraft in ascolto per comandi di controllo sulla porta loopback `7979`.
2. **Creative Suite MCP Bridge (CT 144 - porta 7900)**:
   - Configurato server FastMCP + Starlette sotto systemd (`creative-suite-mcp.service`):
     - Supporta sia **Streamable HTTP** (`/mcp`) sia **SSE** (`/sse`).
     - Gestito Starlette `lifespan` asincrono per l'inizializzazione del session manager.
     - Disattivata protezione DNS rebinding (`enable_dns_rebinding_protection = False`) per autorizzare chiamate LAN/proxy.
   - Espone 7 tool MCP (*sostituiti in Fase 6 dai tool generici multi-app, vedi sotto*):
     - `deckcraft_app_command` (invio comandi live alla GUI: `slide.new`, `slide.inspect`, `shape.insert`, `edit.undo`, ecc.)
     - `deckcraft_cli` (operazioni headless deckcraft)
     - `wordcraft_cli` (operazioni headless wordcraft)
     - `creative_session_launch` (avvio o focus applicazione grafica su `:0`)
     - `creative_session_status` (monitoraggio display, porte IPC e finestre visibili)
     - `creative_screenshot` (cattura frame 1080p da `:0` su `/workspace/screenshots` con opzione base64)
     - `creative_workspace_files` (browsing directory condivisa `/workspace`)
3. **Registrazione Upstream su MetaMCP Gateway (CT 107 - `192.168.1.175:12008`)**:
   - Inserito server `creative-suite` (tipo `STREAMABLE_HTTP`, url `http://192.168.1.189:7900/mcp`) nel DB PostgreSQL `metamcp_db`.
   - Associato al namespace `Homelab` (`5b8f6961-2044-450f-9f63-4cf753e5c816`) sull'endpoint `MetaMCP`.
   - Tool immediatamente scoperti ed esposti globalmente con prefisso `creative-suite__*` (disponibili per Antigravity IDE, Claude, script o agenti esterni).
4. **Verifica Funzionale e Visual Grounding E2E**:
   - Eseguita chiamata a `creative-suite__deckcraft_app_command` via MetaMCP per inserire un roundRect personalizzato con testo *"Created via MetaMCP Universal Gateway!"*.
   - Eseguita cattura visiva con `creative-suite__creative_screenshot`: verificato il corretto rendering a schermo in tempo reale.
5. **Integrazione `homelab-agent` (CT 125) (IN SOSPESO ⏸️)**:
   - *In sospeso su richiesta utente per consentire test preliminari con MetaMCP tramite agenti esterni*.
   - L'implementazione successiva includerà la definizione del catalogo Saga LIFO in `tool_catalog.py`, mode policy in `mode_policy.py` e inline visual previews.


---

### Fase 6: Stabilizzazione & Deploy Versionato
Tutta la configurazione di CT 144 vive in [`deploy/`](../deploy) e si applica dal clone del meta-repo (senza submodule) in `/opt/creative-suite/repo`.

1. **Deploy di una modifica** (dalla workstation, via MCP):
   ```bash
   git push origin main
   exec_lxc_command(vmid=144, command="cd /opt/creative-suite/repo && git pull && deploy/install.sh")
   # poi riavviare solo i servizi toccati, es.:
   exec_lxc_command(vmid=144, command="systemctl restart creative-suite-mcp")   # bridge MCP
   exec_lxc_command(vmid=144, command="systemctl restart sunshine")             # sunshine.conf / apps.json
   ```
2. **Verifica**:
   ```bash
   exec_lxc_command(vmid=144, command="/opt/creative-suite/repo/deploy/smoke-test.sh")
   exec_lxc_command(vmid=144, command="/opt/creative-suite/mcp-server/.venv/bin/python3 /opt/creative-suite/repo/deploy/mcp-e2e.py")
   ```
   In locale: `cd mcp-server && pytest` (39 test, nessun CT richiesto).
3. **Servizi** (tutti `enabled`): `xorg-dummy`, `openbox-session`, `pipewire-headless`, `pipewire-media-session-headless`, `pipewire-pulse-headless`, `sunshine`, `creative-suite-mcp`, `docker` (Moonlight-web), `creative-app@deckcraft`, `creative-app@gridcraft`. WordCraft è on demand (`AUTOSTART=no` in `deploy/apps/wordcraft.env`).
4. **Aggiungere un'app**: compilare `<app>` e `<app>-cli` in `/opt/creative-suite/bin`, creare `deploy/apps/<app>.env` (`CONTROL_PORT` univoca, `CLI_ACTIONS`, `OPEN_METHOD`), `install.sh`, `systemctl restart creative-suite-mcp`. Il bridge la espone senza modifiche al codice.
5. **Sunshine**: pacchetto locale `2026.914.233613+homelab.cuda12.9.sm70` in `apt-mark hold` (le build ufficiali CUDA 13 non supportano la V100). Per aggiornarlo: `deploy/sunshine/build-sunshine.sh <tag>` (~1h, ~12 GB).
6. **Build delle app Rust**: sorgenti in `/workspace/src/<app>` al commit del submodule, `CARGO_TARGET_DIR=/opt/creative-suite/build/target`, `cargo build --release -j 4 -p <app> -p <app>-cli`.
7. **Backup pre-Fase 6**: `/workspace/backups/ct144-pre-fix-2026-10-13.tgz` (snapshot Proxmox non disponibile per via del bind mount `mp0`).
8. **Input dello stream** (mouse/tastiera/touch/penna): Sunshine crea dispositivi uinput `libvirtualhid *` che Xorg nel CT non può hot-plugare (niente udev). Catena: host udev → `/dev/input` nel CT → `virtualhid-relay.service` ([`input-relay/relay.py`](../input-relay/relay.py)) → XTest su `:0`. Verifica: `python3 /opt/creative-suite/repo/deploy/input-e2e.py`.
9. **Configurazione lato host Proxmox** (non gestita da `install.sh`, applicata a mano il 2026-10-13):
   - `/etc/udev/rules.d/99-sunshine-virtualhid.rules` ← [`deploy/host/99-sunshine-virtualhid.rules`](../deploy/host/99-sunshine-virtualhid.rules) (`udevadm control --reload-rules`)
   - righe di [`deploy/host/ct144-input.conf`](../deploy/host/ct144-input.conf) in coda a `/etc/pve/lxc/144.conf` (backup in `/root/144.conf.bak-20261013-150415`), poi riavvio del CT.

### Client Moonlight nativo
1. **Host**: aggiungere manualmente `192.168.1.189` (IP del CT). `creative.deggio.local` punta a NpmLocal e serve solo il client web: non usarlo in Moonlight.
2. **Pairing**: Moonlight mostra un PIN → `https://192.168.1.189:47990` (certificato self-signed) → login Sunshine → scheda *PIN* → inserire PIN e nome del dispositivo.
3. **App**: *Desktop*.
4. **Impostazioni consigliate**: 1920×1080 (risoluzione massima del display virtuale), 60 FPS, codec **HEVC** o H.264 (la V100 non fa AV1), bitrate 20–40 Mbps in LAN, HDR off, *Optimize mouse for remote desktop* **on** (mouse assoluto), *Play audio on PC* **off** (l'audio va al client).
5. **Porte** (se c'è un firewall in mezzo): TCP 47984, 47989, 48010; UDP 47998–48000, 48002, 48010. Il firewall Proxmox è disattivato.
