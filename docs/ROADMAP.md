# Creative Suite Workstation — Execution Roadmap & Tracking Board

> **Document Status:** Active Execution Plan & Tracking Board  
> **Target Environment:** Proxmox VE (`DESKTOP-PGMTM0B` - `192.168.1.69`) / CT 144 (`192.168.1.187`)  
> **Source Specs:** [`OPERATIONAL_PLAN.md`](OPERATIONAL_PLAN.md) · [`STREAMING_ARCHITECTURE.md`](../STREAMING_ARCHITECTURE.md)  
> **Current Baseline:** v0.2.0 (Meta-repository inizializzato, submodules registrati, architettura streaming definita)  

---

## 📊 Tabella di Avanzamento Generale

```
┌────────────────────────────────────────────────────────┬──────────┬──────────┬─────────────┬──────────────┐
│ Milestone / Componente                                 │ Priorità │ Difficoltà│ Riferimenti │ Stato        │
├────────────────────────────────────────────────────────┼──────────┼──────────┼─────────────┼──────────────┤
│ Phase 0: Architettura, Analisi Suite & Meta-Repo       │ P0       │ Bassa    │ Docs Suite  │ ✅ COMPLETATO│
│ Phase 1: Sandbox di Validazione Locale                 │ P3       │ Bassa    │ Local Dev   │ ⏭️ SKIPPED   │
│ Phase 2: Provisioning Container LXC CT 144 (Proxmox)  │ P0       │ Media    │ Template 133│ 🔄 READY     │
│ Phase 3: Virtual Desktop, PipeWire & Sunshine NVENC    │ P0       │ Alta     │ NVENC / V100│ ⏳ READY     │
│ Phase 4: WebRTC Gateway (Moonlight-Web), DNS & NPM     │ P1       │ Media    │ WebCodecs   │ ⏳ READY     │
│ Phase 5: Deploy Suite, Orchestrazione & Live Co-Author │ P1       │ Alta     │ homelab-agen│ ⏳ PIANIFICATO│
└────────────────────────────────────────────────────────┴──────────┴──────────┴─────────────┴──────────────┘
```

---

## 🗺️ Grafo delle Dipendenze

```mermaid
flowchart TD
    P0["✅ Phase 0: Analisi Suite & Meta-Repo Git"]:::done
    P1["⏭️ Phase 1: Sandbox Locale (Skipped)"]:::skipped
    P2["🔄 Phase 2: Provisioning CT 144 su SSD2"]:::active
    P3["⏳ Phase 3: Desktop Headless, Audio & Sunshine NVENC"]:::pending
    P4["⏳ Phase 4: Moonlight-Web-Stream, DNS & NPM SSL"]:::pending
    P5["⏳ Phase 5: Suite Orchestration & Co-Authoring con homelab-agent"]:::pending

    P0 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> P5

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

### Phase 2: Provisioning Container LXC CT 144 su Proxmox VE (IN ARRIVO 🔄)
* **Obiettivo:** Creare il container Proxmox dedicato con accelerazione GPU NVIDIA Tesla V100 e storage rapido su `SSD2`.
* **Deliverable e Checklist:**
  - [ ] **Clonazione Container**: Clonare il template **`133` (`GpuAgy`)** nel nuovo **VMID `144`** (`hostname: creative-workstation`, `--storage SSD2`).
  - [ ] **Configurazione Risorse**: Impostare 6 Core CPU, 8 GB RAM, 2 GB Swap, 32 GB rootfs.
  - [ ] **Configurazione Rete**: Assegnare IP statico `192.168.1.187/24`, Gateway `192.168.1.1`, DNS `192.168.1.170` (Pi-hole).
  - [ ] **Mount Volume Workspace**: Configurare il bind-mount per l'archiviazione progetti condivisa su `/workspace`.
  - [ ] **Verifica GPU Passthrough**: Avviare CT 144 ed eseguire `nvidia-smi` verificando il corretto rilevamento della Tesla V100 16GB.

---

### Phase 3: Desktop Environment Virtuale, Audio & Sunshine NVENC (PRONTO ⏳)
* **Obiettivo:** Predisporre l'ambiente grafico headless e il server di streaming Sunshine a 60 FPS.
* **Deliverable e Checklist:**
  - [ ] **Installazione Pacchetti Grafici**: Installare Xorg, driver dummy (`xserver-xorg-video-dummy`), Openbox/XFCE e utility X11.
  - [ ] **Configurazione Display Headless**: Creare `/etc/X11/xorg.conf` con risoluzioni 1080p@60Hz e 1440p@60Hz.
  - [ ] **Server Audio PipeWire**: Configurare PipeWire con virtual loopback sink per cattura audio a bassa latenza.
  - [ ] **Installazione Sunshine**: Scaricare e installare il pacchetto ufficiale Debian di Sunshine.
  - [ ] **Configurazione Sunshine (`sunshine.conf`)**:
    - Abilitare encoder hardware `nvenc` con preset ultra-low-latency.
    - Configurare permessi `/dev/uinput` per mouse e tastiera virtuali.
    - Abilitare il servizio systemd per avvio automatico al boot.
  - [ ] **Test Funzionalità Sunshine**: Verificare l'avvio della Web UI di Sunshine su `https://192.168.1.187:47990`.

---

### Phase 4: Moonlight-Web-Stream, DNS & Nginx Proxy Manager (PRONTO ⏳)
* **Obiettivo:** Consentire l'accesso alla workstation da qualsiasi browser web tramite HTTPS e WebRTC.
* **Deliverable e Checklist:**
  - [ ] **Deploy Docker Moonlight-Web-Stream**:
    - Configurare `docker-compose.yaml` in `/opt/moonlight-web` su CT 144 (porte 8080 HTTP, 40000-40100/udp WebRTC).
    - Avviare il container e verificare la pagina di login web.
  - [ ] **Accoppiamento (Pairing) Sunshine ➔ Web Client**:
    - Generare il PIN di accoppiamento ed eseguire il pairing con Sunshine.
  - [ ] **Configurazione DNS Pi-hole (CT 114)**:
    - Aggiungere il record locale `creative.deggio.local` ➔ `192.168.1.143` (NpmLocal).
  - [ ] **Configurazione Reverse Proxy (CT 121 - NpmLocal)**:
    - Creare il Proxy Host per `creative.deggio.local` verso `http://192.168.1.187:8080`.
    - Abilitare **Websockets Support** e certificato SSL (Force SSL attivo per sbloccare WebCodecs).
  - [ ] **Test E2E Browser Streaming**: Verificare lo streaming video fluido, l'audio e la risposta ai controlli da un browser esterno.

---

### Phase 5: Orchestrazione Suite Creativa & Live Co-Authoring con `homelab-agent` (PIANIFICATO ⏳)
* **Obiettivo:** Avviare i programmi con canali di controllo attivi e collegare `homelab-agent` per la collaborazione in tempo reale.
* **Deliverable e Checklist:**
  - [ ] **Installazione Binari della Suite**: Compilare e copiare i binari della suite in `/opt/creative-suite/bin`.
  - [ ] **Script di Avvio Sessione**: Creare `/opt/creative-suite/scripts/start-session.sh` con porte IPC dedicate:
    - `deckcraft --control 7979`
    - `wordcraft --control 7981`
    - `photocraft --control 7878`
    - `vectorcraft --control 7980`
    - `cadcraft --control 7982`
    - `soundcraft --control 7801`
  - [ ] **Integrazione `homelab-agent` (CT 125)**:
    - Mappare i comandi dei client MCP verso le porte di CT 144.
    - Aggiornare `tool_catalog.py` con schemi dichiarativi di rollback.
  - [ ] **Test E2E Co-Authoring Live**:
    - Aprire la sessione di streaming nel browser su `https://creative.deggio.local`.
    - Chiedere a `homelab-agent` in chat di manipolare una presentazione o documento.
    - Verificare l'aggiornamento visivo a video a 60 FPS in tempo reale.
