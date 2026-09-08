# Subito.it MacBook Pro Hunter 🍏💻

Sistema automatizzato multi-agente per scovare e notificare in tempo reale affari su:
1. **MacBook Pro 14" e 16" Apple Silicon funzionanti** (M1 Pro/Max, M2 Pro/Max, M3 series, M4 series con almeno 16 GB RAM e 512 GB SSD) sotto la soglia affare impostata.
2. **MacBook Pro rotti / per parti di ricambio / da riparare (esclusivamente MacBook Pro con chip Apple Silicon: almeno M1 o superiore)** a meno di **300 €**.

---

## 🤖 Architettura Multi-Agente

Come specificato nelle direttive di progetto in `GEMINI.md`:

1. **Agente 1: Market Research & Pricing Analyst** (`config_modelli.json`)
   - Mappa le specifiche hardware ufficiali e le configurazioni standard dei MacBook Pro 14" e 16" dal 2021 a oggi.
   - Fornisce prezzi medi stimati dell'usato e soglie massime d'acquisto per considerare l'annuncio un "affare".
   - Include la configurazione `mbp_broken_any` per modelli MacBook Pro rotti/ricambi almeno M1 (< 300€).
   - Facilmente modificabile a mano dall'utente per cambiare le soglie o attivare/disattivare modelli.

2. **Agente 2: NLP & Query Pattern Specialist** (`patterns_ricerca.json` + `nlp_matcher.py`)
   - Gestisce typo, abbreviazioni private (`macbook pro`, `mbp`, `14p`, `16"`, `16giga`, `1tb`).
   - Riconosce ed estrae chip Apple Silicon (`M1`, `M1 Pro/Max`, `M2`, `M2 Pro/Max`, `M3`, `M3 Pro/Max`, `M4`, `M4 Pro/Max`).
   - **Gestione modelli guasti/ricambi**: se l'annuncio presenta token di rottura (`rotto`, `ricambi`, `schermo rotto`, `non si accende`, `blocco icloud`), verifica che sia tassativamente un **MacBook Pro** con **almeno chip M1** (esclusi categoricamente MacBook Air e chip Intel) e con prezzo **< 300 €**.
   - **Filtro accessori assoluti**: scarta automaticamente cover, custodie, caricatori, caricabatterie, batterie sfuse, cavi, scatole vuote, adattatori e pellicole.

3. **Agente 3: Scraper & Telegram Bot Notificatore** (`scraper.py`)
   - Effettua lo scraping efficiente estraendo direttamente lo stato Next.js (`__NEXT_DATA__`) con titolo, corpo completo dell'annuncio, prezzo e località.
   - Mantiene la cronologia degli annunci già esaminati in `seen_ads.json` per evitare duplicati.
   - Invia notifiche push istantanee su Telegram differenziando chiaramente i MacBook Pro funzionanti dagli annunci per parti di ricambio:
     * *Funzionanti:* alert classico con modello stimato, soglia max e link.
     * *Rotti (< 300€):* alert dedicato `🔧 MACBOOK PRO ROTTO / PER RICAMBI (< 300€)!` con chip rilevato e avviso guasto.

---

## 🚀 Installazione Rapida

### 1. Prerequisiti
- Python 3.9 o superiore.
- `pip` e `curl`.

### 2. Installazione dipendenze
```bash
pip install -r requirements.txt
```

### 3. Configurazione Telegram Bot (.env)
Copia il file di esempio e inserisci i parametri del tuo bot Telegram:
```bash
cp .env.example .env
```

Modifica `.env`:
```ini
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
CHECK_INTERVAL_MINUTES=30
```

---

## 🛠️ Utilizzo

### Esecuzione singola (One-shot)
Controlla tutti gli annunci presenti al momento ed esce:
```bash
python3 scraper.py --once
```

### Modalità Simulazione (Dry Run)
Esegue la scansione senza inviare messaggi reali su Telegram (stampa a terminale gli affari trovati):
```bash
python3 scraper.py --once --dry-run
```

### Monitoraggio Continuo (Daemon)
Esegue una scansione ogni 30 minuti (o quanto impostato in `CHECK_INTERVAL_MINUTES`):
```bash
python3 scraper.py
```
Puoi personalizzare l'intervallo direttamente da linea di comando:
```bash
python3 scraper.py --interval 15
```

### Reset storico annunci visti
Per forzare il riesame di tutti gli annunci attualmente online:
```bash
python3 scraper.py --once --reset-seen
```

---

## ⚙️ Personalizzazione Prezzi e Modelli

Nel file `config_modelli.json` puoi in qualsiasi momento:
- Modificare `prezzo_max_soglia_affare` per qualsiasi modello funzionante.
- Regolare la soglia per i MacBook Pro rotti modificando il valore per `"id": "mbp_broken_any"` (impostato a 300 €).
- Impostare `"attivo": false` su modelli che non ti interessano.
