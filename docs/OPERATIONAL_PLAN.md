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
| **Indirizzo IP Statico** | **`192.168.1.187/24`** | IP libero (evita sovrapposizioni con CT 142 `scriberr` a `.186` e CT 143 a `.188`). |
| **Gateway & DNS** | `192.168.1.1` / `192.168.1.170` | Default gateway LAN e resolver DNS Pi-hole (CT 114). |

---

## 2. Architettura dei Componenti nel Container CT 144

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ CT 144: creative-workstation (192.168.1.187 su SSD2)                                  │
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

### Fase 1: Provisioning e Configurazione Base del Container (CT 144)
1. **Clonazione da Template**:
   Esecuzione del comando di clonazione tramite Proxmox CLI:
   ```bash
   pct clone 133 144 --hostname creative-workstation --storage SSD2 --full 1
   ```
2. **Dimensionamento Risorse & Configurazione Rete**:
   ```bash
   pct set 144 -cores 6 -memory 8192 -swap 2048
   pct set 144 -rootfs SSD2:32
   pct set 144 -net0 name=eth0,bridge=vmbr0,firewall=1,gw=192.168.1.1,ip=192.168.1.187/24
   pct set 144 -nameserver 192.168.1.170 -searchdomain deggio.local
   pct set 144 -features nesting=1,keyctl=1
   ```
3. **Mount Storage Condiviso Progetti**:
   Creazione di una cartella progetti su storage persistente e bind-mount in `/workspace`:
   ```bash
   pct set 144 -mp0 /Nass/Nasss/creative_workspace,mp=/workspace
   ```
4. **Verifica GPU Passthrough**:
   Avvio del container e verifica dei nodi NVIDIA:
   ```bash
   pct start 144
   pct exec 144 -- nvidia-smi
   ```

---

### Fase 2: Ambiente Desktop Headless, Audio & Sunshine Server
1. **Installazione Pacchetti Grafici Headless & Window Manager**:
   Installazione di Xorg con driver dummy e Openbox/XFCE per la gestione delle finestre:
   ```bash
   pct exec 144 -- apt update
   pct exec 144 -- apt install -y xserver-xorg-video-dummy x11-xserver-utils openbox xfce4-terminal dbus-x11 pipewire pipewire-pulse libuinput1
   ```
2. **Configurazione Xorg Dummy Display**:
   Configurazione di `/etc/X11/xorg.conf` con risoluzioni 1920x1080@60Hz e 2560x1440@60Hz con profondità di colore 24-bit.
3. **Configurazione Audio Virtuale**:
   Attivazione di PipeWire con sink virtuale per catturare l'output audio delle applicazioni e inoltrarlo allo stream.
4. **Installazione e Setup Sunshine**:
   - Download del pacchetto `.deb` ufficiale Debian di Sunshine.
   - Configurazione di `/etc/sunshine/sunshine.conf`:
     - Encoder forzato su `nvenc`
     - Preset ultra-low-latency (`p3` o `ull`)
     - Configurazione permessi `/dev/uinput`
   - Creazione del servizio systemd per avvio automatico all'accensione del container.

---

### Fase 3: Gateway WebRTC (Moonlight-Web-Stream) & Routing di Rete
1. **Deployment di Moonlight-Web-Stream**:
   - Creazione della directory `/opt/moonlight-web` in CT 144.
   - Configurazione di `docker-compose.yaml` (usando l'immagine `mrcreativ3001/moonlight-web-stream:latest` clonata nel nostro repo):
     - Bind address: `0.0.0.0:8080`
     - WebRTC UDP range: `40000-40100`
     - Network mode: `host`
2. **Pairing Sunshine ➔ Moonlight-Web**:
   - Accesso alla web UI Sunshine su `https://192.168.1.187:47990`.
   - Generazione PIN di accoppiamento da Moonlight-Web ed esecuzione del pairing sicuro.
3. **Configurazione DNS Locale (Pi-hole - CT 114)**:
   - Creazione record A: `creative.deggio.local` ➔ `192.168.1.143` (IP di NpmLocal CT 121).
4. **Configurazione Reverse Proxy (NpmLocal - CT 121)**:
   - Creazione Proxy Host: `creative.deggio.local` verso `http://192.168.1.187:8080`.
   - Abilitazione supporto WebSockets (**ON**).
   - Generazione/applicazione certificato SSL locale (Force SSL attivo).

---

### Fase 4: Distribuzione Suite Creativa & Orchestrazione Sessione
1. **Compilazione ed Installazione Binari**:
   - Installazione dei tool CLI e GUI in `/opt/creative-suite/bin`:
     `deckcraft`, `wordcraft`, `photocraft`, `vectorcraft`, `cadcraft`, `soundcraft`, `artcraft`.
2. **Script di Sessione e Autostart**:
   - Creazione dello script `/opt/creative-suite/scripts/start-session.sh` che lancia il server grafico Xorg, il window manager e predispone le porte di controllo IPC in ascolto:
     - DeckCraft: porta `7979`
     - WordCraft: porta `7981`
     - PhotoCraft: porta `7878`
     - VectorCraft: porta `7980`
     - CADCraft: porta `7982`
     - SoundCraft: porta `7801`

---

### Fase 5: Registrazione MetaMCP (CT 107) & Live Co-Authoring con `homelab-agent` (CT 125)
1. **Creative Suite MCP Bridge (CT 144)**:
   - Configurazione di un server MCP unificato (SSE/HTTP su porta `7900`) che espone i comandi IPC delle applicazioni creative (`deckcraft`, `wordcraft`, `photocraft`, `vectorcraft`, `cadcraft`, `soundcraft`).
2. **Registrazione Upstream su MetaMCP (CT 107 - `192.168.1.175:12008`)**:
   - Registrazione dell'endpoint `http://192.168.1.187:7900/sse` nel gateway MetaMCP come server `creative-suite`.
   - **Vantaggio Architetturale Chiave**: Gli strumenti diventano immediatamente disponibili con prefisso `creative-suite__*` su tutti i client connessi a MetaMCP:
     - Antigravity IDE (sulla workstation dev)
     - Claude Code, Cursor, Copilot o script di automazione
     - `homelab-agent` (CT 125) via auto-discovery dinamica di `MetaMCPClient`.
3. **Ottimizzazioni Specifiche in `homelab-agent` (CT 125)**:
   - **Rollback Transazionale (Saga LIFO)** in `tool_catalog.py`: mappatura delle azioni inverse di undo (es. cancellazione di una shape/slide creata erroneamente).
   - **Mode Policy & Permessi**: autorizzazione dei tool nel registry `metamcp` o profilo `creative`.
   - **Grounding Visivo e Sincronizzazione Streaming**: cattura di screenshot dal frame buffer/Sunshine per analisi multimodale e verifica visiva in tempo reale prima di confermare all'utente in chat.
4. **Validazione E2E in Tempo Reale**:
   - Connessione utente via browser su `https://creative.deggio.local`.
   - Invio comandi in chat ad un agente (es. `homelab-agent` o Antigravity) per manipolare un asset grafico o documento.
   - Visualizzazione del rendering dinamico a 60 FPS direttamente sullo schermo streamed.
