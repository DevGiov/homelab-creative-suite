# Guida all'uso dei tool MCP `creative-suite`

Come un agente AI (Claude Code, Antigravity `agy`, `homelab-agent`…) deve pilotare le app della suite tramite MetaMCP.
Questo file spiega il **flusso corretto e le trappole note**; il riferimento completo dei parametri dei tool è nel
[README](./README.md#-integrazione-agenti--co-authoring-live), il codice del bridge in [`mcp-server/server.py`](./mcp-server/server.py).

> Le parti marcate *(verificato su SoundCraft)* sono state provate dal vivo; i comandi engine variano da app ad app.

---

## 1. Come sono esposti i tool

Il bridge (CT 144, porta 7900) è aggregato da MetaMCP (`http://192.168.1.175:12008/metamcp/MetaMCP/mcp`, nessuna API key richiesta).
I 9 tool hanno prefisso `creative-suite__`:

| Client | Come si chiamano |
| :--- | :--- |
| Claude Code | `mcp__metamcp__creative-suite__<tool>` |
| Antigravity (`agy`) | `call_mcp_tool` con `ServerName: "metamcp"`, `ToolName: "creative-suite__<tool>"` |
| Altri client MCP | `creative-suite__<tool>` sul server `metamcp` |

Tool: `session_status`, `session_launch`, `session_stop`, `app_commands`, `app_command`, `app_control`, `app_cli`, `screenshot`, `workspace_files`.

**Antigravity**: in modalità non interattiva (`agy --print`) i tool che richiedono conferma vengono negati in automatico
(`Print mode: soft-denying tool confirmation "CallMcpTool"`; osservato su `proxmox-mcp/exec_lxc_command`, mentre
`session_status` passava senza regola). Per far girare i tool di scrittura servono regole
`mcp(metamcp/creative-suite__<tool>)` in `~/.gemini/antigravity-cli/settings.json` → `permissions.allow`.
Inoltre `metamcp` va configurato per `agy` via bridge stdio `mcp-remote`: il client HTTP nativo non si collega a MetaMCP
(vedi `~/.gemini/config/mcp_config.json`).

---

## 2. Regole d'oro

1. **Usa solo i tool `creative-suite__*` per pilotare le app.** Non leggere il sorgente delle app per capire i comandi
   e non usare `proxmox-mcp/exec_lxc_command` per far girare CLI o app: è più lento, costoso e può toccare il CT.
   `exec_lxc_command` serve per deploy e diagnosi del bridge (vedi [AGENTS.md](../../AGENTS.md) §3), non per lavorare nelle app.
2. **Scopri i comandi con `app_commands` (filtro per parole), non a memoria e non dal codice.**
3. **Verifica sempre leggendo lo stato** (`document.inspect`, `session.inspect`, `midi.notes`…): una risposta `ok: true`
   non dice che il risultato sia musicalmente/graficamente quello voluto.
4. **Usa gli id restituiti** dai comandi (`tracks`, `clip`…): non indovinarli.
5. **Il documento aperto è dell'utente**: prima di `session.new`/`file.open`/chiusure controlla `dirty` (vedi §5).

---

## 3. Flusso standard

```
session_status                      # l'app è installata/attiva? porta aperta?
session_launch(app[, file_path])    # se unit inactive / port_open false
app_control(app, "document.inspect")# stato del documento aperto (o ui.inspect per la GUI)
app_commands(app, filter="...")     # trova gli id e leggi i parametri
app_command(app, command, params)   # modifica live (visibile nello stream)
app_control(app, "document.inspect")# verifica
screenshot()                        # solo se serve vedere la GUI
```

`app_command` modifica il documento **aperto nella GUI**. `app_cli` lavora su file su disco con un motore **separato**
(non vede il documento aperto): salva prima dall'app (`app_control app.save {"path": ...}` o `app_command file.saveAs`)
e poi usa `app_cli`.

---

## 4. Scelta del tool

| Obiettivo | Tool |
| :--- | :--- |
| Stato workstation / app attive | `session_status` |
| Aprire / chiudere un'app (anche con un file) | `session_launch` / `session_stop` (**stop perde le modifiche non salvate**) |
| Trovare l'id di un comando | `app_commands` (filtro + limite) |
| Modificare il documento aperto | `app_command` |
| Ispezionare, salvare, screenshot interno, dialoghi | `app_control` (`document.inspect`, `ui.inspect`, `app.save`, `ui.screenshot`, `ui.dialog.confirm`) |
| Convertire / renderizzare / leggere un file | `app_cli` |
| Vedere cosa c'è in `/workspace` | `workspace_files` |
| Catturare il display | `screenshot` |

Esempi di comandi dalla descrizione del tool `app_command` (altre app): DeckCraft `slide.new`, `shape.insert`
`{"preset":"roundRect","rect":[100,100,400,200],"text":"Hi"}`; WordCraft `text.insert` `{"text":"Hello"}`, `format.bold`;
GridCraft `cell.set` `{"cell":"B2","input":"=SUM(A1:A9)"}`; PdfCraft: id di registry (`view.zoomIn`).

---

## 5. Trappole note

- **I comandi non applicabili sono nascosti.** `app_commands` esclude i comandi disabilitati (nessun documento, nessuna
  selezione, nessuna traccia…) a meno di `include_disabled: true`. Esempio *(verificato su SoundCraft)*: `midi.new_clip`
  non compare finché non esiste una traccia. In caso di dubbio: `include_disabled: true`, oppure
  `app_command engine.commands {"filter": "..."}` che restituisce anche `disabled_reason`.
- **Filtra sempre.** Le liste complete pesano 19–314 KB (SoundCraft: 520 comandi). Usa `filter` e `limit`.
- **`session.new` sostituisce la sessione corrente**, anche se non salvata *(verificato su SoundCraft)*. Controlla `dirty`
  in `document.inspect`/`session.inspect` e salva o chiedi conferma all'utente.
- **Percorsi confinati in `/workspace`** (relativi o assoluti dentro). Niente `~`, niente percorsi fuori; PhotoCraft li vuole relativi.
- **`screenshot` con `include_base64: true` produce ~120k caratteri** e supera il limite di output di molti client
  (Claude Code lo rifiuta). Di default salva solo il PNG in `/workspace/screenshots/`: usa la base64 solo se devi davvero vedere l'immagine.
- **Parametri errati = errore esplicito**, es. `bad parameters for midi.note_add: clip id required`: `clip` vuole l'**id
  numerico**, mentre `track` accetta id o nome *(verificato su SoundCraft)*.
- **Chiamate indipendenti si possono parallelizzare**, ma se l'ordine conta (creare traccia → creare clip → aggiungere note)
  falle in sequenza e usa gli id restituiti.
- **`app_cli` tronca l'output a 16k caratteri** e ammette solo le azioni in allow-list dell'app (`CLI_ACTIONS` in `deploy/apps/<app>.env`).

---

## 6. Esempio completo — SoundCraft: batteria 4/4 + linea di basso *(verificato)*

**Unità di tempo:** in SoundCraft `start_ticks`/`length_ticks` sono a **960 tick per quarto** (`PPQ = 960`).
In 4/4 una battuta = **3840 tick**; l'ottavo = 480, il sedicesimo = 240.
A 120 BPM una battuta = 96000 campioni a 48 kHz (2 s). Il default di `length_ticks` è 480 (un ottavo), non un quarto.

```jsonc
// 1. app e sessione
session_launch      {app: "soundcraft"}
app_command         {app: "soundcraft", command: "session.new", params: {name: "Groove", template: "blank"}}  // sostituisce la sessione corrente

// 2. tracce strumento (plugin disponibili: engine.plugins → drum_synth, subtractive_synth)
app_command  track.new {kind: "instrument", name: "Drums", instrument: "drum_synth"}        // → {tracks:[1]}
app_command  track.new {kind: "instrument", name: "Bass",  instrument: "subtractive_synth"} // → {tracks:[2]}

// 3. clip MIDI di 1 battuta (default) — restituisce l'id da usare per le note
app_command  midi.new_clip {track: "Drums", start: 0}   // → {clip:3, start:0, end:96000}
app_command  midi.new_clip {track: "Bass",  start: 0}   // → {clip:4, ...}

// 4. note (clip = id numerico)
midi.note_add {clip:3, pitch:36, start_ticks:0,    length_ticks:480}  // kick  beat 1
midi.note_add {clip:3, pitch:36, start_ticks:1920, length_ticks:480}  // kick  beat 3
midi.note_add {clip:3, pitch:38, start_ticks:960,  length_ticks:480}  // snare beat 2
midi.note_add {clip:3, pitch:38, start_ticks:2880, length_ticks:480}  // snare beat 4
midi.note_add {clip:3, pitch:42, start_ticks:0|480|960|…|2880, length_ticks:240}  // hi-hat chiuso a ottavi
midi.note_add {clip:3, pitch:46, start_ticks:3360, length_ticks:480}  // hi-hat aperto sull'ultimo ottavo
midi.note_add {clip:4, pitch:33, start_ticks:0,    length_ticks:900}  // basso: A1
midi.note_add {clip:4, pitch:33, start_ticks:960,  length_ticks:900}  // A1
midi.note_add {clip:4, pitch:36, start_ticks:1920, length_ticks:900}  // C2
midi.note_add {clip:4, pitch:38, start_ticks:2880, length_ticks:420}  // D2
midi.note_add {clip:4, pitch:40, start_ticks:3360, length_ticks:420}  // E2

// 5. verifica
midi.notes {clip:3}  midi.notes {clip:4}
session.inspect {detail: "summary"}
```

Mappatura del `drum_synth` (da `soundcraft/crates/dsp/src/plugins/drums.rs`): 35/36 kick, 38/40 snare, 42/44 hat chiuso, 46 hat aperto.
Per più battute: `midi.new_clip` con `length`/`end` più lungo, oppure `clip.loop`.

---

## 7. Dove cercare altro

- Tabella dei tool e app gestite: [README](./README.md#-integrazione-agenti--co-authoring-live)
- Porte, argomenti e `CLI_ACTIONS` per app: [`deploy/apps/*.env`](./deploy/apps)
- Deploy e test e2e del bridge (`mcp-e2e.py`, `apps-e2e.py`): [AGENTS.md](../../AGENTS.md) §3, [`docs/OPERATIONAL_PLAN.md`](./docs/OPERATIONAL_PLAN.md)
- Comandi di una singola app: `app_commands` sull'app in esecuzione; le istruzioni upstream stanno in `<app>/AGENTS.md` (submodule: non modificare).
