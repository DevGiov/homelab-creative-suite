# Creative Suite Workstation — Execution Roadmap & Tracking Board

> **Document Status:** Active Execution Plan & Tracking Board  
> **Target Environment:** Proxmox VE (`DESKTOP-PGMTM0B` - `192.168.1.69`) / CT 144 (`192.168.1.189`)  
> **Source Specs:** [`OPERATIONAL_PLAN.md`](OPERATIONAL_PLAN.md) · [`STREAMING_ARCHITECTURE.md`](../STREAMING_ARCHITECTURE.md)  
> **Current Baseline:** v0.4.0 (CT 144 su SSD2, rootfs 64 GB, GPU V100, config versionata in [`deploy/`](../deploy))  

---

## 📊 Tabella di Avanzamento Generale

```
┌────────────────────────────────────────────────────────┬──────────┬──────────┬─────────────┬──────────────┐
│ Milestone / Componente                                 │ Priorità │ Difficoltà│ Riferimenti │ Stato        │
├────────────────────────────────────────────────────────┼──────────┼──────────┼─────────────┼──────────────┤
│ Phase 0: Architettura, Analisi Suite & Meta-Repo       │ P0       │ Bassa    │ Docs Suite  │ ✅ COMPLETATO│
│ Phase 1: Sandbox di Validazione Locale                 │ P3       │ Bassa    │ Local Dev   │ ⏭️ SKIPPED   │
│ Phase 2: Provisioning Container LXC CT 144 (Proxmox)  │ P0       │ Media    │ Template 133│ ✅ COMPLETATO│
│ Phase 3: Virtual Desktop, PipeWire & Sunshine NVENC    │ P0       │ Alta     │ NVENC / V100│ ✅ COMPLETATO│
│ Phase 4: WebRTC Gateway (Moonlight-Web), DNS & NPM     │ P1       │ Media    │ WebCodecs   │ ✅ COMPLETATO│
│ Phase 5: Registrazione MetaMCP & Live Co-Authoring     │ P1       │ Alta     │ CT 107/125  │ 🟢 CORE OK   │
│ Phase 6: Stabilizzazione (audio, NVENC, sessione, MCP) │ P0       │ Alta     │ deploy/     │ 🟢 CORE OK   │
│ Phase 7: Launcher e suite completa (12 app)            │ P0       │ Media    │ deploy/     │ 🟢 CORE OK   │
└────────────────────────────────────────────────────────┴──────────┴──────────┴─────────────┴──────────────┘
```

---

## 🗺️ Grafo delle Dipendenze

```mermaid
flowchart TD
    P0["✅ Phase 0: Analisi Suite & Meta-Repo Git"]:::done
    P1["⏭️ Phase 1: Sandbox Locale (Skipped)"]:::skipped
    P2["✅ Phase 2: Provisioning CT 144 su SSD2"]:::done
    P3["✅ Phase 3: Desktop Headless, Audio & Sunshine"]:::done
    P4["✅ Phase 4: Moonlight-Web-Stream, DNS & NPM"]:::done
    P5["🟢 Phase 5: MetaMCP & Co-Authoring (homelab-agent in sospeso)"]:::done
    P6["✅ Phase 6: Stabilizzazione & deploy versionato"]:::done
    P7["✅ Phase 7: Launcher e 12 app"]:::done

    P0 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> P5
    P5 --> P6
    P6 --> P7

    classDef done fill:#2e7d32,stroke:#1b5e20,color:#fff;
    classDef skipped fill:#757575,stroke:#424242,color:#fff;
    classDef active fill:#0277bd,stroke:#01579b,color:#fff;
    classDef pending fill:#37474f,stroke:#263238,color:#fff;
```

---

## 📌 Dettaglio Milestone e Checklist di Lavoro

### Phase 0: Architettura, Ricerca e Meta-Repository (COMPLETATO ✅)
- [x] Analisi delle 13 applicazioni della Creative Suite e mappatura delle equivalenti commerciali.
- [x] Studio dei target compilativi (Desktop nativo, Headless CLI con stdio MCP, WebAssembly con Trunk).
- [x] Analisi tecnica del flusso streaming a bassa latenza: Sunshine NVENC + Moonlight-Web-Stream (WebCodecs/WebRTC).
- [x] Clonazione del repository [`moonlight-web-stream`](../moonlight-web-stream) all'interno del workspace.
- [x] Redazione della documentazione architetturale completa: [`STREAMING_ARCHITECTURE.md`](../STREAMING_ARCHITECTURE.md).
- [x] Ispezione della documentazione di sistema Proxmox in `/root/docs` e correzione delle discrepanze VMID/IP locali.
- [x] Inizializzazione del meta-repository Git con 14 submodules e pubblicazione su GitHub (`DevGiov/homelab-creative-suite`).

---

### Phase 1: Sandbox di Validazione Locale (SKIPPED ⏭️)
*Nota:* Saltata su richiesta dell'utente per procedere direttamente con il deployment server-side su Proxmox VE.
- [-] *Compilazione binari pilota in locale (deckcraft, wordcraft, photocraft).*
- [-] *Test protocollo MCP stdio con Antigravity locale.*

---

### Phase 2: Provisioning Container LXC CT 144 su Proxmox VE (COMPLETATO ✅)
* **Obiettivo:** Creare il container Proxmox dedicato con accelerazione GPU NVIDIA Tesla V100 e storage rapido su `SSD2`.
* **Deliverable e Checklist:**
  - [x] **Clonazione Container**: Clonato il template **`133` (`GpuAgy`)** nel nuovo **VMID `144`** (`hostname: creative-workstation`, volume `vm-144-disk-0` su `SSD2`).
  - [x] **Configurazione Risorse**: Impostati 6 Core CPU, 8 GB RAM, 2 GB Swap, esteso rootfs a 32 GB.
  - [x] **Configurazione Rete**: Assegnato IP statico `192.168.1.189/24` (il .187 era occupato da un device fisico LAN), Gateway `192.168.1.1`, DNS `192.168.1.170` (Pi-hole), searchdomain `deggio.local`.
  - [x] **Mount Volume Workspace**: Configurato bind-mount `/workspace` mappato direttamente sul dataset NAS `/Nass/Nasss/Homelab/creative_suite` (con permessi RW verificati).
  - [x] **Permessi Input Virtuale**: Configurato passthrough `/dev/uinput` (major 10, minor 223) e regola udev mode 0666 per Sunshine.
  - [x] **Verifica GPU Passthrough**: Container avviato con successo (`pct start 144`), eseguito `nvidia-smi` verificando il corretto rilevamento della Tesla V100 16GB (Driver 550.144.03, CUDA 12.4).

---

### Phase 3: Desktop Environment Virtuale, Audio & Sunshine NVENC (COMPLETATO ✅)
* **Obiettivo:** Predisporre l'ambiente grafico headless e il server di streaming Sunshine a 60 FPS.
* **Deliverable e Checklist:**
  - [x] **Installazione Pacchetti Grafici**: Installati Xorg, driver dummy (`xserver-xorg-video-dummy`), Openbox, utility X11 (`xdpyinfo`, `xdotool`, `feh`, `x11-xserver-utils`) e dipendenze Mesa/OpenGL.
  - [x] **Configurazione Display Headless**: Creato `/etc/X11/xorg.conf` con risoluzioni 1080p@60Hz e 1440p@60Hz; verificato funzionamento con `xrandr` su `DISPLAY=:0`.
  - [x] **Server Audio PipeWire**: Installati e configurati `pipewire`, `pipewire-media-session` e librerie audio client headless con socket runtime in `/run/user/0/pipewire-0`.
  - [x] **Installazione Sunshine**: Installato pacchetto ufficiale LizardByte Sunshine `v2026.914.233613` per Ubuntu 22.04 LTS con dipendenze Qt6 QPA XCB.
  - [x] **Configurazione Sunshine (`sunshine.conf`)**:
    - Abilitata modalità headless (`system_tray = false`).
    - Configurate credenziali Web manager protette (`admin / homelabcreative`).
    - Verificata disponibilità encoder hardware e software (NVENC CUDA/FFmpeg su Tesla V100 e multi-threaded `libx264`). *Rettifica Phase 6: in realtà Sunshine ripiegava su `libx264`; NVENC funziona solo dopo la build CUDA 12.9.*
    - Creati e abilitati i servizi systemd con autostart al boot (`xorg-dummy`, `openbox-session`, `pipewire-headless`, `pipewire-media-session-headless`, `sunshine`).
  - [x] **Test Funzionalità Sunshine**: Verificato l'avvio della Web UI di Sunshine su `https://192.168.1.189:47990` con risposta HTTP 200 e API JSON funzionanti sia in locale che via rete LAN. Testato reboot persistente del container.

---

### Phase 4: Moonlight-Web-Stream, DNS & Nginx Proxy Manager (COMPLETATO ✅)
* **Obiettivo:** Consentire l'accesso alla workstation da qualsiasi browser web tramite HTTP/HTTPS, WebSockets e WebRTC senza client da installare.
* **Deliverable e Checklist:**
  - [x] **Deploy Docker Moonlight-Web-Stream**:
    - Configurato `docker-compose.yaml` in `/opt/moonlight-web` su CT 144 (porte 8080 HTTP, 40000-40100/udp WebRTC, `network_mode: host`).
    - Risolto limite quota chiavi sessione kernel Proxmox (`kernel.keys.maxkeys = 1000000`, `kernel.keys.maxbytes = 25000000`).
    - Configurato volume `/opt/moonlight-web/data` con permessi corretti per utente container `moonlight` (UID/GID 999).
    - Container avviato con successo, verificato avvio al boot e logging Actix Web su porta 8080.
  - [x] **Accoppiamento (Pairing) Sunshine ➔ Web Client**:
    - Creato utente amministratore iniziale su Moonlight-Web (`admin / homelabcreative`).
    - Rilevato Sunshine host `creative-workstation` via mDNS/broadcast su rete locale.
    - Eseguito handshake crittografico di pairing su Sunshine `/api/pin`.
    - Host verificato in stato `Paired` / `Free`, con lista applicazioni attive (`Desktop`, `Low Res Desktop`, `Steam Big Picture`).
  - [x] **Configurazione DNS Pi-hole (CT 114)**:
    - Aggiunto record locale `creative.deggio.local` ➔ `192.168.1.143` (NpmLocal).
  - [x] **Configurazione Reverse Proxy (CT 121 - NpmLocal)**:
    - Creato Proxy Host per `creative.deggio.local` verso `http://192.168.1.189:8080`.
    - Abilitato supporto **WebSockets Upgrade** (`allow_websocket_upgrade: true`) per lo stream di controllo e segnalazione WebRTC.
  - [x] **Test Funzionalità Web Streaming**:
    - Verificata la risposta HTTP 200 di `http://creative.deggio.local` sia per il documento base sia per gli asset JS (`index.js`, `styles/index.js`).
    - Verificate le API di autenticazione, listing host e listing app da endpoint di rete locale.

---

### Phase 5: Registrazione MetaMCP (CT 107) & Live Co-Authoring via Universal Gateway (IN CORSO / COMPLETATO CORE 🟢)
* **Obiettivo:** Esporre gli strumenti di controllo della Suite Creativa tramite **MetaMCP** (`CT 107`) come hub centralizzato per renderli universalmente disponibili (Antigravity, Claude, script esterni e `homelab-agent`), testando la manipolazione live del desktop prima di passare all'integrazione personalizzata in `homelab-agent`.
* **Deliverable e Checklist:**
  - [x] **Installazione Binari & Demoni di Controllo (CT 144)**:
    - Compilazione nativa su CT 144 (`Ubuntu 22.04 LTS`, `glibc 2.35`) con `rustc 1.99.0`:
      - `/opt/creative-suite/bin/deckcraft` (Desktop presentation GUI con supporto `--control`)
      - `/opt/creative-suite/bin/deckcraft-cli` (Controllo headless e bridge IPC verso la GUI)
      - `/opt/creative-suite/bin/wordcraft-cli` (Document conversions, inspect e headless operations)
    - Sessione desktop Openbox attiva su `:0` con DeckCraft avviato e in ascolto su socket loopback TCP porta `7979`.
  - [x] **Creative Suite MCP Bridge Server (CT 144)**:
    - Sviluppato server FastMCP/Starlette su porta `7900` (`creative-suite-mcp.service`) con supporto sia per **Streamable HTTP** (`/mcp`) sia per **SSE** (`/sse`).
    - Implementati e testati 7 tool centrali:
      - `deckcraft_app_command`: invio comandi live alla GUI (`slide.new`, `slide.inspect`, `shape.insert`, `edit.undo`, ecc.).
      - `deckcraft_cli`: operazioni headless su presentazioni.
      - `wordcraft_cli`: operazioni headless su documenti WordCraft.
      - `creative_session_launch`: avvio e focus automatico dei software grafici su `:0`.
      - `creative_session_status`: stato in tempo reale di porte IPC, finestre X11 attive e display virtuale.
      - `creative_screenshot`: frame capture istantaneo con FFmpeg a 1080p con salvataggio su `/workspace/screenshots` e supporto base64.
      - `creative_workspace_files`: navigazione filesystem nel NAS condiviso `/workspace`.
    - Gestito correttamente il ciclo di vita asincrono (`lifespan`) Starlette e disattivata la DNS rebinding protection per consentire richieste proxy e LAN.
  - [x] **Registrazione Upstream su MetaMCP (CT 107)**:
    - Registrato upstream `creative-suite` di tipo `STREAMABLE_HTTP` con URL `http://192.168.1.189:7900/mcp` nel database PostgreSQL di MetaMCP (`metamcp_db`).
    - Mappato nel namespace `Homelab` (`5b8f6961-2044-450f-9f63-4cf753e5c816`) associato all'endpoint primario `MetaMCP` (`192.168.1.175:12008`).
    - Verificata la discovery immediata dei 7 tool con prefisso namespace `creative-suite__*` su chiamata standard JSON-RPC `tools/list`.
  - [x] **Test E2E Co-Authoring Live via MetaMCP**:
    - Testata la chiamata a `creative-suite__creative_session_status` via MetaMCP Gateway: visualizzazione corretta della finestra `DeckCraft` e porta `7979` attiva.
    - Testata la manipolazione live con `creative-suite__deckcraft_app_command`: inserita forma `roundRect` con testo *"Created via MetaMCP Universal Gateway!"* su slide 2.
    - Testata la cattura con `creative-suite__creative_screenshot`: confermata visivamente la presenza delle modifiche grafiche renderizzate in tempo reale sul virtual display `:0` ad accelerazione GPU.
  - [ ] **Discovery Dinamica & Ottimizzazioni Specifiche in `homelab-agent` (CT 125) (IN SOSPESO ⏸️)**:
    - *(Lasciato temporaneamente in sospeso su richiesta esplicita dell'utente, per consentire prima testing approfondito via MetaMCP con altri agent)*.
    - Da implementare successivamente: registrazione schemi di Rollback Saga LIFO in `tool_catalog.py`, policy profili in `mode_policy.py`, e visual feedback inline in chat.

---

### Phase 6: Stabilizzazione & Deploy Versionato (2026-10-13)
* **Obiettivo:** Rendere la workstation affidabile (audio, encoding hardware, sessione persistente), sicuro il bridge MCP ed estendere la suite a WordCraft e GridCraft, con configurazione e test nel repo.
* **Deliverable e Checklist:**
  - [x] **Config versionata** in [`deploy/`](../deploy): unit systemd, Sunshine, Moonlight, Xorg, `apps/*.env`; `install.sh` idempotente; deploy = `git pull && deploy/install.sh` in `/opt/creative-suite/repo`.
  - [x] **Audio**: il server Pulse di PipeWire non era mai avviato (`Couldn't connect to pulseaudio`). Nuova unit `pipewire-pulse-headless` + `PULSE_SERVER` per Sunshine → `pactl` vede *PulseAudio (on PipeWire)* e un sink.
  - [x] **NVENC**: Sunshine 2026.914 ufficiale è compilato con CUDA 13.1 senza Volta (sm_70) → `cudaErrorInsufficientDriver` e fallback a `libx264`. Aggiornare il driver host **non** risolve. Build da sorgente con CUDA 12.9.1 ([`deploy/sunshine/build-sunshine.sh`](../deploy/sunshine/build-sunshine.sh)), pacchetto `2026.914.233613+homelab.cuda12.9.sm70` in `apt-mark hold` → `Found H.264/HEVC encoder: *_nvenc`. AV1 non supportato dalla V100.
  - [x] **Sessione persistente**: unit template `creative-app@<app>`; DeckCraft e GridCraft partono al boot, WordCraft on demand. `apps.json` di Sunshine ripulito (output `HDMI-1` inesistente, Steam non installato).
  - [x] **WordCraft + GridCraft** compilati (v0.3.0, commit dei submodule) e installati in `/opt/creative-suite/bin`; porte 7981 / 7983 (GridCraft ha default 7979 come DeckCraft).
  - [x] **Bridge MCP v2** ([`mcp-server/server.py`](../mcp-server/server.py)): registry dichiarativo da `deploy/apps`, trasporto JSON-lines diretto, sessioni via systemd, niente `shell=True` (chiusa una shell injection in `creative_session_launch`), path confinati a `/workspace` (chiuso un path traversal). Tool rinominati (breaking): `app_command`, `app_control`, `app_cli`, `session_launch`, `session_stop`, `session_status`, `screenshot`, `workspace_files`.
  - [x] **Test**: 39 test pytest in `mcp-server/tests` (42) e `input-relay/tests` (13); [`deploy/smoke-test.sh`](../deploy/smoke-test.sh) (32 controlli live); [`deploy/mcp-e2e.py`](../deploy/mcp-e2e.py) (22 controlli via client MCP reale). Tutto verde anche **dopo `pct reboot 144`**.
  - [x] **Rootfs 32 → 64 GB** (build CUDA/Rust).
  - [x] **Input nello stream** (segnalato dall'utente: stream "congelato", nessun input). Sunshine inietta mouse/tastiera via uinput (`libvirtualhid *`), ma nel CT unprivileged non c'è udev, Xorg non aveva driver di input e i nodi restavano nell'host (`root:input 0660`). Fix: regola udev host solo per i device `libvirtualhid` ([`deploy/host/`](../deploy/host)), bind di `/dev/input` nel CT, demone [`input-relay`](../input-relay) evdev → XTest. Verificato con [`deploy/input-e2e.py`](../deploy/input-e2e.py) (6/6) e 13 test unitari.
  - [x] **Audio nello stream**: in sessione Sunshine falliva `set-default-sink: Not supported` (pipewire-media-session senza moduli `metadata`/`default-nodes`). Abilitati da `install.sh`.
  - [x] **Bridge stateless**: dopo il reboot MetaMCP restava su una sessione MCP inesistente (`Session not found`) → `stateless_http=True` + test di regressione.
  - [ ] **Stream E2E manuale**: aprire `creative.deggio.local`, avviare *Desktop*, verificare input, audio udibile e `nvidia-smi` con sessione encoder attiva.
* **Problemi noti:**
  - **WordCraft 0.3.0 ridisegna in continuo** quando la finestra è visibile (0% minimizzato). Sul display dummy ogni frame passa da Mesa llvmpipe (GL software): ~380% CPU a riposo, ~100% con `LP_NUM_THREADS=1`. Mitigato con avvio on demand + 1 thread llvmpipe; da segnalare upstream (`storytold/wordcraft`).
  - Le app egui renderizzano in **software** (llvmpipe): lo Xorg `dummy` non ha GLX accelerato. Un X server su driver NVIDIA headless eliminerebbe il costo, ma richiede `nvidia-modeset` e privilegi oltre l'LXC unprivileged attuale.
  - Lo script upstream `linux_build.sh` ignora `--num-processors` nello step di build (`ninja` senza `-j`): con 8 GB di RAM satura il CT e mette in swap l'host.


---

### Phase 7: Launcher e suite completa (2026-10-13)
* **Obiettivo:** scegliere l'app dentro lo stream (chiudendo le finestre restava lo schermo nero) e avere tutte le app Rust installate e pilotabili.
* **Deliverable e Checklist:**
  - [x] **Launcher**: voce per app nella lista Sunshine/Moonlight, pannello tint2 sempre visibile (launcher + task bar + orologio) e menu a clic destro (`Ctrl+Alt+Spazio`), tutti generati da `deploy/apps/*.env` per le sole app installate; "Esci dall'app" lascia l'app aperta. Entry point unico `creative-open <app>`.
  - [x] **9 app compilate** con `deploy/build-apps.sh` (47 min totali, nessun fallimento): CADCraft 4, DesignCraft 5, VectorCraft 5, SoundCraft 2, PdfCraft 6, PhotoCraft 5, LightCraft 7, EffectCraft 6, FilmCraft 4 minuti. ArtCraft esclusa (Tauri/React, non Rust).
  - [x] **Bridge**: PhotoCraft (token, percorsi relativi) e PdfCraft (file di controllo con porta dinamica, risposte JSON-RPC, `ui.command`); `session_launch` porta la finestra in primo piano. 72 test.
  - [x] **Verifica**: `apps-e2e.py` 12/12 (lancio, finestra, `ui.inspect` autenticato, elenco comandi, screenshot letti uno per uno); `panel-e2e.py` (clic reale sul pannello e clic destro) ; `mcp-e2e.py` 31/31; `input-e2e.py`; `smoke-test.sh` dopo `pct reboot 144`.
  - [ ] **Prova manuale dal client Moonlight**: lista app con 13 voci, scelta di un'app, input e audio.
* **Problemi trovati e risolti:**
  - **PhotoCraft** apriva ogni volta il dialogo "Switched to CPU rendering" (`--safe-gpu` non lo evita): ora la preferenza CPU è scritta da `deploy/provision-photocraft.py`.
  - **SoundCraft** non trovava nessuna scheda audio (ALSA): `/etc/asound.conf` → PulseAudio; compare come flusso PipeWire.
  - **FilmCraft** richiede `libgtk-3-dev libxdo-dev` (menu bar `muda`).
  - `mcp-e2e.py` perdeva app avviate se falliva a metà (corretto: copre solo le app con un edit noto, il resto è in `apps-e2e.py`).
* **Problemi noti:**
  - **WordCraft e SoundCraft** consumano ~100% di una CPU a riposo (ridisegno continuo sul GL software con `LP_NUM_THREADS=1`); tutte le altre 0%. Sono on demand.
  - **LightCraft** usa ~300% di CPU nei primi secondi (generazione delle foto demo) e poi 0%.
  - DeckCraft e GridCraft restano `AUTOSTART=yes` come in Phase 6: all'avvio compaiono due finestre sovrapposte. Mettere `AUTOSTART=no` in `deploy/apps/{deckcraft,gridcraft}.env` dà un desktop pulito con il pannello.
  - Build in `/opt/creative-suite/build/target` occupa 13 GB; `cargo clean` quando serve spazio.

### Collaudo dei tool MCP (2026-10-14)
Ogni tool è stato esercitato via MetaMCP con casi d'uso reali; i risultati sono verificati sui file prodotti, non solo sull'`ok` del tool.

| Flusso | Esito |
|---|---|
| GridCraft: 7 celle + formula `=SUM(B2:B3)*1.22` → `.xlsx` → `cat --csv`/`--formulas`/`info` | 2111,21; formula conservata |
| WordCraft: titolo, testo grassetto, elenco → `.docx` → `text`/`info`/PDF/PNG | testo e struttura corretti |
| PdfCraft (canale con file di controllo): apre il PDF, `ui.state`, `ui.set zoom`, `view.theme.dark`, screenshot | testo, elenco e segnalibro nel PDF |
| DeckCraft: 2 slide con forme → `app.export .pptx` → PDF → testo letto da PdfCraft | entrambe le slide |
| PhotoCraft (token, percorsi relativi): `image.adjustments.invert` → PNG | pixel FF7A00→0085FF verificati |
| CADCraft: `cmdline.input` (cerchio r=5, linea) → DXF → `info` → SVG | geometria esatta |
| VectorCraft: `shape.rectangle/ellipse` → SVG (dialogo `svgOptions` confermato) → `info`/PNG | 2 tracciati |
| EffectCraft, DesignCraft, LightCraft, SoundCraft, FilmCraft | comandi live ok (composizione+livelli, cornice, `develop.set`, traccia click, tracce) |

**Problemi trovati e risolti**
- Gli elenchi di comandi pesano **19–314 KB** (VectorCraft 304 KB): nuovo `app_commands` con filtro e limite; `app_cli` tronca a 16k caratteri con indicazione.
- `app_cli` usa un motore headless **separato** (EffectCraft `info` mostrava il progetto demo, non quello aperto): ora scritto nella descrizione del tool.
- `session_status` mostrava la porta casuale di un PdfCraft fermo: ora `null` finché non è in esecuzione.
- VectorCraft *Salva con nome* `.svg` apre un dialogo in attesa: documentato (`ui.dialog.confirm`).

### Audio di SoundCraft e selettori file (2026-10-14)
- **SoundCraft non "non suonava"**: è una DAW e un progetto vuoto è silenzio. Verificato: importato un WAV (`file.import_audio`) + `transport.play`, il monitor del sink segna −21,7 dB medi mentre suona (silenzio −91 dB). Catena app → ALSA → Pulse → sink Sunshine → Moonlight-web → browser confermata anche dall'ascolto di un tono di prova.
- **Selettori file ("Apri/Importa/Salva") non funzionavano in nessuna app**: `rfd` usa il portale XDG via D-Bus e nel CT non c'erano né bus di sessione né portale (l'app non mostrava nulla, quindi i file si potevano caricare solo da un agente). Aggiunti `dbus-session.service`, `xdg-desktop-portal` + backend GTK (`portals.conf default=gtk`), `DBUS_SESSION_BUS_ADDRESS` nelle app, segnalibri `/workspace` nel selettore. Verificato con [`deploy/dialog-e2e.py`](../deploy/dialog-e2e.py): Ctrl+O → selettore → percorso → DeckCraft apre `demo.pptx` (2 slide).
- **Comportamento da sapere**: `rfd::FileDialog` è sincrono, quindi finché il selettore è aperto l'app (e il suo canale di controllo) non risponde; si chiude con Annulla/Invio o Esc.
