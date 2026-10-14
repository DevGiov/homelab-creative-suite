# Creative Suite — Homelab Workspace

Suite completa di strumenti creativi open-source integrati per l'ecosistema Homelab, ospitati centralmente su Proxmox VE e controllabili tramite agenti AI (incluso [`homelab-agent`](../homelab-agent)).

---

## 🎨 Applicazioni della Suite

La suite comprende 13 applicativi specializzati:

| Applicazione | Equivalente Noti | Descrizione | Directory |
| :--- | :--- | :--- | :--- |
| **PhotoCraft** | Adobe Photoshop | Fotoritocco raster, livelli, maschere, supporto PSD/PSB, pennelli, WebGPU. | [`photocraft/`](./photocraft) |
| **VectorCraft**| Adobe Illustrator| Grafica vettoriale avanzata, tracciati Bézier, forme, tipografia, SVG. | [`vectorcraft/`](./vectorcraft) |
| **DeckCraft**  | MS PowerPoint   | Creazione presentazioni, layout, forme, grafici, tabelle, export PPTX/PDF. | [`deckcraft/`](./deckcraft) |
| **WordCraft**  | MS Word         | Elaboratore di testi, formattazione ricca, tabelle, stili, docx/odt/rtf/md. | [`wordcraft/`](./wordcraft) |
| **GridCraft**  | MS Excel        | Fogli di calcolo, formule matematiche, tabelle, formattazione, export XLSX. | [`gridcraft/`](./gridcraft) |
| **DesignCraft**| Adobe InDesign  | Impaginazione editoriale, desktop publishing multi-pagina, griglie, print. | [`designcraft/`](./designcraft) |
| **EffectCraft**| Adobe After Effects | Compositing video, grafica animata, livelli temporali, effetti visivi. | [`effectcraft/`](./effectcraft) |
| **FilmCraft**  | Adobe Premiere Pro | Montaggio video non lineare (NLE), timeline multi-traccia, tagli, export. | [`filmcraft/`](./filmcraft) |
| **SoundCraft** | Pro Tools / DAW | Digital audio workstation, registrazione, mix multitraccia, effetti, MIDI. | [`soundcraft/`](./soundcraft) |
| **LightCraft** | Adobe Lightroom | Catalogazione fotografica, sviluppo RAW, color grading non distruttivo. | [`lightcraft/`](./lightcraft) |
| **CADCraft**   | AutoCAD         | Disegno tecnico 2D, comandi da riga di comando, snap geometrici, layer. | [`cadcraft/`](./cadcraft) |
| **PdfCraft**   | Adobe Acrobat   | Visualizzazione, combinazione, divisione, compilazione e sicurezza PDF. | [`pdfcraft/`](./pdfcraft) |
| **ArtCraft**   | AI Generative Studio | Staging 2D e 3D, compositing e orchestrazione di modelli di diffusione. | [`artcraft/`](./artcraft) |

---

## 🚀 Architettura di Streaming & Accesso Cross-Device

Per evitare installazioni locali separate su ogni dispositivo e consentire un passaggio fluido tra PC principale, portatile e tablet, la suite sfrutta:

- **Host di Streaming**: [Sunshine](https://github.com/LizardByte/Sunshine) in esecuzione su container Proxmox LXC con GPU Passthrough NVIDIA (NVENC encoding a 60 FPS e latenza < 15ms).
- **Client Web Zero-Install**: [`moonlight-web-stream`](./moonlight-web-stream), che converte il flusso GameStream in **WebRTC** e sfrutta **WebCodecs** nel browser per la decodifica hardware locale senza dover installare alcun software client.
- **Client Nativo Opzionale**: Compatibile con qualsiasi client ufficiale [Moonlight](https://moonlight-stream.org/) (per refresh rate elevati a 120Hz e supporto nativo stilo/penna).

👉 **Consulta la guida architetturale completa**: [STREAMING_ARCHITECTURE.md](./STREAMING_ARCHITECTURE.md)

---

## 🤖 Integrazione Agenti & Co-Authoring Live

Le applicazioni della suite espongono un canale di controllo JSON-lines su loopback (`--control <port>`) e una CLI headless. Sulla workstation (CT 144) il **bridge MCP** [`mcp-server/`](./mcp-server) le rende disponibili a tutti gli agenti tramite MetaMCP (`creative-suite__*`):

👉 **Come usarli (flusso, trappole note, esempio SoundCraft)**: [`MCP_TOOLS_GUIDE.md`](./MCP_TOOLS_GUIDE.md)

| Tool | Uso |
| :--- | :--- |
| `app_commands(app, filter, limit)` | Cerca gli id dei comandi di un'app aperta (filtro per parole, max 200 risultati): le liste complete pesano 19–314 KB |
| `app_command(app, command, params)` | Esegue un comando engine nell'app aperta (modifica live visibile nello stream) |
| `app_control(app, method, params)` | Metodo raw del canale di controllo (`ui.inspect`, `document.inspect`, `ui.screenshot`, `app.save`…) |
| `app_cli(app, action, args)` | Operazione headless su file (`convert`, `render`, `info`…), azioni in allowlist per app; è un motore separato, non vede il documento aperto nella GUI; output limitato a 16k caratteri |
| `session_launch(app, file_path)` / `session_stop(app)` | Avvia/ferma l'app sul desktop virtuale (unit `creative-app@<app>`) |
| `session_status()` | Stato unit, porte di controllo e finestre visibili |
| `screenshot(filename, include_base64)` | Cattura del display `:0` in `/workspace/screenshots/` |
| `workspace_files(subpath)` | Navigazione di `/workspace` (NAS) |

App gestite dal bridge (una per file in [`deploy/apps/`](./deploy/apps), che è l'unica fonte di porte, argomenti e permessi):

| Categoria | App | Canale di controllo |
| :--- | :--- | :--- |
| Documenti | DeckCraft (7979), GridCraft (7983) | JSON-lines su loopback |
| Documenti | WordCraft (7981) | key file in `~/.config/wordcraft` |
| Documenti | PdfCraft | file di controllo con porta e token casuali |
| Grafica | PhotoCraft (7878) | token in un file, percorsi relativi a `/workspace` |
| Grafica | VectorCraft (7980), CADCraft (7982), DesignCraft (7984), LightCraft (7985) | JSON-lines su loopback |
| Audio e video | SoundCraft (7801), FilmCraft (7986), EffectCraft (7987) | JSON-lines su loopback |

DeckCraft e GridCraft partono al boot; le altre si avviano su richiesta (`session_launch`, menu, pannello o app Sunshine). Tutti i percorsi sono confinati in `/workspace`; nessuna chiamata passa da una shell.

## 🖥️ Scegliere l'app dallo stream

Dal client Moonlight (nativo o web) ci sono tre modi, tutti basati su `creative-open <app>`:

1. **Lista app di Moonlight/Sunshine**: oltre a *Desktop* compare una voce per ogni app installata; la scelta avvia l'app e la porta in primo piano. "Esci dall'app" la lascia aperta.
2. **Pannello in basso** (tint2): un pulsante per app, più la lista delle finestre aperte e l'orologio.
3. **Menu a clic destro** sul desktop (o `Ctrl+Alt+Spazio`), raggruppato per categoria; clic centrale = elenco finestre.

Il pannello, il menu e la lista Sunshine sono generati da `deploy/gen-session-config.py` solo per le app con un binario in `/opt/creative-suite/bin`.

Configurazione e deploy del CT: [`deploy/`](./deploy) (`install.sh` idempotente, `smoke-test.sh` per la verifica live).

---

## 📋 Documentazione Operativa & Roadmap

- 🤖 [**`MCP_TOOLS_GUIDE.md`**](./MCP_TOOLS_GUIDE.md) — Guida d'uso dei tool MCP `creative-suite__*` per agenti AI: flusso corretto, trappole note, esempio completo.
- 📑 [**`docs/OPERATIONAL_PLAN.md`**](./docs/OPERATIONAL_PLAN.md) — Piano operativo dettagliato con parametri di sistema, comandi Proxmox, display headless e setup Sunshine.
- 🎯 [**`docs/ROADMAP.md`**](./docs/ROADMAP.md) — Tracking board di avanzamento con stato milestone, checklist di lavoro e grafo delle dipendenze.
- 📖 [**`STREAMING_ARCHITECTURE.md`**](./STREAMING_ARCHITECTURE.md) — Architettura tecnica approfondita su NVENC, WebCodecs e WebRTC.

---

## 📂 Struttura della Directory

```
creative_suite/
├── artcraft/                 # Studio AI generativo (Rust + Tauri + React)
├── cadcraft/                 # CAD 2D in Rust
├── deckcraft/                # Presentazioni in Rust
├── designcraft/              # Desktop publishing in Rust
├── effectcraft/              # Compositing video in Rust
├── filmcraft/                # Video editor NLE in Rust
├── gridcraft/                # Fogli di calcolo in Rust
├── lightcraft/               # Photo catalog e RAW in Rust
├── deploy/                   # Config versionata di CT 144 (systemd, Sunshine, app), install e smoke test
├── mcp-server/               # Bridge MCP (FastMCP) + test pytest
├── input-relay/              # Mouse/tastiera/touch di Sunshine → Xorg (XTest) + test
├── moonlight-web-stream/     # WebRTC gateway client per lo streaming nel browser
├── pdfcraft/                 # Gestione PDF in Rust
├── photocraft/               # Fotoritocco raster in Rust
├── soundcraft/               # DAW audio in Rust
├── vectorcraft/              # Grafica vettoriale in Rust
├── wordcraft/                # Word processor in Rust
├── README.md                 # Questo file
├── MCP_TOOLS_GUIDE.md        # Guida d'uso dei tool MCP per gli agenti AI
└── STREAMING_ARCHITECTURE.md # Documentazione tecnica dettagliata su Sunshine e Moonlight
```
