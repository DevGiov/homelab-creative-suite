# Architettura di Streaming: Creative Suite su Proxmox con Sunshine & Moonlight-Web-Stream

Questo documento descrive l'architettura tecnica, le modalità di distribuzione e i flussi operativi per il self-hosting della **Creative Suite** nel Homelab, sfruttando **Sunshine** (host NVENC a bassissima latenza), **Moonlight-Web-Stream** (bridge WebRTC/WebCodecs per accesso via browser senza installazione) e l'integrazione per il **Co-Authoring Live** con **`homelab-agent`**.

---

## 1. Visione d'Insieme & Diagramma dell'Architettura

L'obiettivo è eseguire le applicazioni creative direttamente su Proxmox con accelerazione GPU dedicata, trasmettendo la sessione desktop via streaming video a 60 FPS direttamente a qualsiasi browser web (laptop, desktop secondario, tablet) o a client nativi Moonlight via LAN e Tailscale.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PROXMOX VE HOST (DESKTOP-PGMTM0B - 192.168.1.69)                                                       │
│                                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Container LXC GPU (Basato su Template CT 133 / Passthrough NVIDIA)                               │  │
│  │ IP: 192.168.1.187 (creative-workstation)                                                         │  │
│  │                                                                                                  │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Virtual Desktop Session (X11 Dummy / Openbox / XFCE) + PipeWire Virtual Sink             │  │  │
│  │  │                                                                                            │  │  │
│  │  │ Applicazioni in Esecuzione:                                                                │  │  │
│  │  │  - DeckCraft  (--control 7979)                                                             │  │  │
│  │  │  - WordCraft  (--control 7981)                                                             │  │  │
│  │  │  - PhotoCraft (--control 7878)                                                             │  │  │
│  │  │  - ArtCraft   (Tauri Desktop GUI)                                                          │  │  │
│  │  │  - ... (VectorCraft, CADCraft, FilmCraft, SoundCraft)                                      │  │  │
│  │  └──────────────────────────────────────┬─────────────────────────────────────────────────────┘  │  │
│  │                                         │ Framebuffer Video & Audio                              │  │
│  │                                         ▼                                                        │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Sunshine Host Daemon                                                                       │  │  │
│  │  │  - Encoding Hardware NVENC: H.264 / HEVC / AV1                                             │  │  │
│  │  │  - Cattura Audio PipeWire Loopback                                                         │  │  │
│  │  │  - Emulazione Input via /dev/uinput                                                        │  │  │
│  │  │  - Porte: 47984-47990, 48010 (GameStream nativo)                                           │  │  │
│  │  └──────────────────────────────────────┬─────────────────────────────────────────────────────┘  │  │
│  │                                         │ Connessione Loopback GameStream                        │  │
│  │                                         ▼                                                        │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Moonlight-Web-Stream (Docker Container / Processo Rust)                                   │  │  │
│  │  │  - Web Server & Autenticazione (Porta 8080)                                                │  │  │
│  │  │  - WebRTC Media Gateway (Porte UDP 40000-40100)                                            │  │  │
│  │  │  - Forwarding GameStream ➔ WebRTC Data/Media Tracks                                        │  │  │
│  │  └──────────────────────────────────────┬─────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────┼────────────────────────────────────────────────────────┘  │
│                                            │                                                           │
│  ┌───────────────────────────────────┐     │ Porte IPC Controllo (7979, 7981, 7878...)                 │
│  │ CT 125: homelab-agent (Dev Stack) │ <───┘                                                           │
│  │  - mcp_client.py                  │     (Co-Authoring in tempo reale via MCP bridge)                │
│  │  - <app>-cli mcp --connect        │                                                                 │
│  └───────────────────────────────────┘                                                                 │
└────────────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                             │ HTTPS / WSS / WebRTC
                                             ▼
                       ┌───────────────────────────────────────────┐
                       │ CT 121: NpmLocal (192.168.1.143) / Tailscale│
                       │ Dominio: https://creative.deggio.local    │
                       └─────────────────────┬─────────────────────┘
                                             │
             ┌───────────────────────────────┴───────────────────────────────┐
             ▼                                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ Browser Web Client (Zero-Install)       │     │ Client Nativo Moonlight (Opzionale)     │
│ - Qualsiasi PC, Laptop, Mac, iPad       │     │ - Workstation primaria / Tablet         │
│ - Decodifica Hardware: WebCodecs API    │     │ - Refresh rate 120Hz/144Hz              │
│ - Rendering: HTML5 <canvas> a 60 FPS    │     │ - Cattura esclusiva scorciatoie OS      │
│ - AudioWorklet a bassa latenza          │     │ - Protocollo GameStream nativo          │
└─────────────────────────────────────────┘     └─────────────────────────────────────────┘
```

---

## 2. Componenti Chiave del Flusso Video

### 2.1 Sunshine (Host Encoding NVENC)
[Sunshine](https://github.com/LizardByte/Sunshine) è il server di streaming self-hosted open-source per il protocollo GameStream/Moonlight.
- **Perché Sunshine**: A differenza dei server VNC o RDP tradizionali che comprimono immagini statiche via CPU, Sunshine cattura direttamente il framebuffer X11/Wayland e lo invia al chip **NVENC** della scheda NVIDIA per la codifica hardware video (H.264 o HEVC).
- **Latenza tipica di encoding**: **< 3 ms** a 1080p@60FPS o 1440p@60FPS.
- **Audio Virtuale**: Sunshine si collega a un sink virtuale PipeWire/PulseAudio, garantendo streaming stereo bidirezionale perfetto anche per le applicazioni DAW come SoundCraft.

### 2.2 Moonlight-Web-Stream (WebRTC Client nel Browser)
Il repository [`moonlight-web-stream`](file:///home/deggio/Desktop/coding/progetti/homelab/creative_suite/moonlight-web-stream) funge da client Moonlight incorporato in un server web:
- **Traduzione di Protocollo**: Converte i flussi audio/video e gli eventi di input di Sunshine in standard **WebRTC**.
- **Decodifica WebCodecs Client-Side**: Il browser non usa un interprete lento in software, ma richiama le API native `VideoDecoder` (WebCodecs), decodificando i frame direttamente sulla GPU locale del dispositivo che naviga la pagina.
- **Zero Dipendenze**: Nessuna applicazione da installare sul dispositivo client: è sufficiente aprire il browser web.
- **Keyboard Lock API**: In modalità a schermo intero nel browser, intercetta combinazioni di tasti come `Ctrl+W`, `Alt+Tab`, e i tasti funzione senza chiudere la scheda del browser.

---

## 3. Dinamica del "Co-Authoring Live" (Utente + `homelab-agent`)

Uno dei maggiori vantaggi dell'architettura desktop su Proxmox è la possibilità per l'utente e per l'agente AI di lavorare **contemporaneamente sullo stesso documento aperto a schermo**.

### 3.1 Come Funziona il Controllo IPC
Ogni applicazione della suite (WordCraft, DeckCraft, PhotoCraft, CADCraft, ecc.) supporta una porta di controllo IPC loopback basata su JSON-Lines:

| Applicazione | Comando di Avvio Desktop GUI | Porta IPC | Protocollo & Metodo |
| :--- | :--- | :--- | :--- |
| **DeckCraft** | `deckcraft --control 7979` | `7979` | JSON-Lines: comandi `slide.*`, `shape.*`, `design.*` |
| **WordCraft** | `wordcraft --control 7981` | `7981` | JSON-Lines: comandi `format.*`, `insert.*`, `type_text` |
| **PhotoCraft** | `photocraft --control 7878` | `7878` | Control token: livelli, filtri, crop, maschere |
| **VectorCraft**| `vectorcraft --control 7980`| `7980` | JSON-Lines: tracciati vettoriali, forme, stili |
| **CADCraft**   | `cadcraft --control 7982`   | `7982` | Disegno tecnico, snap, layer, quote |
| **SoundCraft** | `soundcraft --control 7801` | `7801` | Tracce, volumi, effetti, transport control |

### 3.2 L'Architettura MetaMCP-First: Hub Centralizzato e Universale

Invece di accoppiare gli strumenti MCP direttamente ed esclusivamente dentro `homelab-agent`, l'architettura adotta **MetaMCP (CT 107)** come hub centrale per l'intero homelab:

```text
┌────────────────────────────────────────────────────────┐
│ CT 144: creative-workstation                           │
│  - Applicazioni GUI (DeckCraft, PhotoCraft, ecc.)       │
│  - Creative Suite MCP Bridge (SSE/HTTP su porta 7900)  │
└──────────────────────────┬─────────────────────────────┘
                           │ SSE / JSON-RPC
                           ▼
┌────────────────────────────────────────────────────────┐
│ CT 107: MetaMCP Gateway (192.168.1.175:12008)           │
│  - Upstream registrato: "creative-suite"               │
│  - Espone strumenti unificati: creative-suite__*       │
└──────────┬──────────────────┬──────────────────────────┘
           │                  │
           ▼                  ▼
┌─────────────────────────┐  ┌─────────────────────────────────────────┐
│ Client Esterni          │  │ CT 125: homelab-agent (Dev Stack)       │
│ - Antigravity IDE (dev) │  │  - Auto-discovery via MetaMCPClient      │
│ - Claude Code / Cursor  │  │  - Ottimizzazioni specifiche:            │
│ - Script e automazioni  │  │    * Rollback Transazionale (Saga LIFO)  │
│                         │  │    * Grounding Visivo multimodale        │
│                         │  │    * Sincronizzazione Live Co-Authoring  │
└─────────────────────────┘  └─────────────────────────────────────────┘
```

#### Flusso Operativo del Live Co-Authoring:
1. **Invio Comando**: L'utente chiede in chat a `homelab-agent` (o ad Antigravity):
   > *"Aggiungi una nuova slide a due colonne, imposta il titolo 'Stato Servizi Homelab' e inserisci una tabella con i container attivi."*
2. **Esecuzione Tool tramite MetaMCP**: L'agente invoca il tool `creative-suite__deckcraft_add_slide` attraverso MetaMCP.
3. **Bridge ed IPC**: Il bridge su CT 144 inoltra la richiesta sulla porta IPC loopback locale `7979` di DeckCraft.
4. **Rendering e Streaming**: DeckCraft renderizza istantaneamente la slide nel motore grafico GUI su Xorg `:0`.
5. **Feed Video a 60 FPS**: Sunshine cattura il frame aggiornato e Moonlight-Web-Stream lo proietta nel browser dell'utente a bassissima latenza. L'utente vede comparire la slide in tempo reale mentre osserva lo schermo.
6. **Grounding e Rollback**: Se l'utente chiede un annullamento (*"Annulla l'ultima modifica"*), `homelab-agent` attiva il rollback dichiarativo (Saga LIFO) registrato nel suo catalogo.

---

## 4. Storage Centralizzato e Condivisione File

Per eliminare il problema del trasferimento file tra dispositivi:
1. **Dataset Condiviso su Proxmox**:
   - Cartella condivisa `/data/creative_projects` (oppure mount NFS/SMB dal container NAS CT 128 `192.168.1.128`).
2. **Mount nel Container Workstation**:
   - Montato su `/workspace` all'interno del container LXC della workstation.
3. **Accesso Univoco**:
   - La sessione GUI accede direttamente a `/workspace`.
   - `homelab-agent` su CT 125 accede allo stesso volume (tramite bind mount o API).
   - I salvataggi e gli export (PDF, PPTX, PSD, DOCX) sono immediatamente persistiti e accessibili da qualsiasi dispositivo.

---

## 5. Specifiche di Deployment su Proxmox VE

### 5.1 Requisiti del Container LXC (Host Workstation)
- **Base OS**: Debian 12 / Ubuntu 24.04 (o clonazione da template **CT 133 GPU**).
- **GPU Passthrough**:
  - `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-modeset`, `/dev/nvidia-uvm`.
  - `/dev/dri/renderD128` (per accelerazione Mesa/Vulkan).
  - `/dev/uinput` con permessi `rw` (per l'emulazione input di Sunshine).
- **Display Headless**:
  - Pacchetto `xserver-xorg-video-dummy` con risoluzione virtuale impostata (es. `1920x1080@60Hz` o `2560x1440@60Hz`).
  - In alternativa: HDMI Dummy Plug hardware inserito nella scheda video del server Proxmox per mantenere attivo l'hardware EDID.
- **Audio**:
  - Daemon PipeWire configurato con modulo loopback per esporre la sorgente di cattura audio a Sunshine.

### 5.2 Configurazione Sunshine
File `/etc/sunshine/sunshine.conf` (o `~/.config/sunshine/sunshine.conf`):
```ini
encoder = nvenc
nvenc_preset = p3
nvenc_tune = ull
nvenc_rate_control = cbr
min_threads = 4
audio_sink = auto
origin_pin_allowed = 127.0.0.1
```

### 5.3 Configurazione Moonlight-Web-Stream (Docker Compose)
Il servizio `moonlight-web-stream` viene avviato direttamente nel container (o affiancato via Docker):

```yaml
version: "3.9"

services:
  moonlight-web:
    image: mrcreativ3001/moonlight-web-stream:latest
    container_name: moonlight-web
    restart: unless-stopped
    network_mode: host
    environment:
      - WEBRTC_NAT_1TO1_HOST=192.168.1.187
      - WEBRTC_PORT_RANGE=40000:40100
      - BIND_ADDRESS=0.0.0.0:8080
    volumes:
      - /opt/moonlight-web/data:/moonlight-web/server
```
*(L'utilizzo di `network_mode: host` semplifica la comunicazione WebRTC UDP con i client locali).*

---

## 6. Configurazione Rete, Reverse Proxy & Sicurezza

### 6.1 Nginx Proxy Manager Locale (CT 121 - NpmLocal)
Configurazione dell'host di proxy inverso:
- **Domain Names**: `creative.deggio.local`
- **Forward Hostname / IP**: `192.168.1.187`
- **Forward Port**: `8080`
- **Cache Assets**: Off
- **Block Common Exploits**: On
- **Websockets Support**: **ON** *(Obbligatorio per la segnalazione WebRTC e i token di controllo).*
- **SSL**: Certificato SSL locale abilitato con Force SSL *(Necessario per consentire al browser di attivare le API WebCodecs e la Keyboard Lock API).*

### 6.2 DNS Locale Pi-Hole (CT 114)
Aggiungere il record locale:
- `creative.deggio.local` ➔ `192.168.1.143` (IP di NpmLocal CT 121).

### 6.3 Accesso Remoto Fuori Casa
- **Tailscale**: Il container `creative-workstation` (o il Proxmox host) fa parte della Tailnet, rendendo la suite accessibile in streaming sicuro senza dover aprire porte sul router di casa.

---

## 7. Tabella di Riepilogo Porte e Servizi

| Porta | Protocollo | Servizio | Scopo |
| :--- | :--- | :--- | :--- |
| `8080` | TCP (HTTP/WSS) | Moonlight-Web-Stream | Interfaccia Web e segnalazione WebRTC |
| `40000-40100` | UDP | WebRTC Media | Canali audio/video e input per il browser |
| `47984, 47989` | TCP | Sunshine | Web UI di amministrazione e configurazione pairing |
| `47998-48010` | UDP | Sunshine GameStream | Flusso streaming per client nativo Moonlight |
| `7979` | TCP | DeckCraft IPC | Porta controllo presentazioni per `homelab-agent` |
| `7981` | TCP | WordCraft IPC | Porta controllo documenti per `homelab-agent` |
| `7878` | TCP | PhotoCraft IPC | Porta controllo grafica raster per `homelab-agent` |
| `7980` | TCP | VectorCraft IPC | Porta controllo vettoriale per `homelab-agent` |

---

## 8. Procedura Operativa per il Test Iniziale

1. **Compilazione Locale dei Binari della Suite**:
   ```bash
   cd /home/deggio/Desktop/coding/progetti/homelab/creative_suite
   cargo build --release -p deckcraft -p deckcraft-cli
   cargo build --release -p wordcraft -p wordcraft-cli
   cargo build --release -p photocraft -p photocraft-cli
   ```
2. **Setup Container GPU su Proxmox**:
   - Clonare o preparare un container con driver NVIDIA e Xorg dummy display.
   - Installare Sunshine `.deb` ed eseguire il pairing con il browser.
3. **Avvio di Moonlight-Web-Stream**:
   - Avviare il container `moonlight-web` ed eseguire il pairing con Sunshine tramite PIN.
4. **Verifica Accesso e Co-Authoring**:
   - Connettersi via browser su `https://creative.deggio.local`.
   - Avviare `deckcraft --control 7979 &`.
   - Lanciare da terminale o da `homelab-agent`:
     ```bash
     deckcraft-cli mcp --connect 127.0.0.1:7979
     ```
   - Inviare comandi di inserimento forme o testi e verificare il riscontro visivo in streaming a 60 FPS.
