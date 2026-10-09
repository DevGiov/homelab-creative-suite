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

Tutte le 12 applicazioni scritte in Rust espongono nativamente un server **Model Context Protocol (MCP)** e una porta di controllo IPC loopback:
- **Modalità Headless (`<app>-cli mcp`)**: Consente a `homelab-agent` o Antigravity di creare, modificare e convertire documenti in background senza aprire finestre grafiche.
- **Modalità Remote Bridge (`<app>-cli mcp --connect <port>`)**: Permette all'agente di inviare comandi all'applicazione GUI aperta sul desktop virtuale. L'utente osserva l'agente manipolare gli elementi in tempo reale via streaming video a 60 FPS.

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
├── moonlight-web-stream/     # WebRTC gateway client per lo streaming nel browser
├── pdfcraft/                 # Gestione PDF in Rust
├── photocraft/               # Fotoritocco raster in Rust
├── soundcraft/               # DAW audio in Rust
├── vectorcraft/              # Grafica vettoriale in Rust
├── wordcraft/                # Word processor in Rust
├── README.md                 # Questo file
└── STREAMING_ARCHITECTURE.md # Documentazione tecnica dettagliata su Sunshine e Moonlight
```
