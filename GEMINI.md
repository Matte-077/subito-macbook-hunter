 ARCHITETTURA MULTI-AGENTE: SUBITO.IT MACBOOK PRO HUNTER

## OBIETTIVO DEL PROGETTO
Automatizzare il monitoraggio e la notifica di annunci vantaggiosi di MacBook Pro usati su subito.it.

Requisiti:
1. **MacBook Pro Funzionanti (Apple Silicon 14" e 16")**:
   - Modelli: Apple Silicon dal 2021 in poi (M1 Pro/Max, M2 Pro/Max, M3 Pro/Max/Base 14", M4 Pro/Max)
   - Display: 14 pollici o 16 pollici
   - Memoria RAM: >= 16 GB
   - Archiviazione SSD: >= 512 GB
   - Condizione di prezzo: Inferiore alla media di mercato ("prezzo affare" / target price in `config_modelli.json`)

2. **MacBook Pro Rotti / Per Ricambi (almeno chip M1 Apple Silicon)**:
   - Modelli: Solo MacBook Pro con chip Apple Silicon (M1, M1 Pro, M1 Max, M2, M2 Pro, M2 Max, M3, M4 series), qualsiasi display (13", 14", 16"), con indicazione di guasto/da riparare/per parti di ricambio/bloccato. Esclusi MacBook Air e modelli Intel.
   - Condizione di prezzo: Prezzo < 300 € (soglia configurabile in `config_modelli.json`, id: `mbp_broken_any`).

---

## AGENTE 1: MARKET RESEARCHER & PRICING ANALYST
### Responsabilità:
1. Raccogliere le specifiche tecniche ufficiali dei MacBook Pro da fine 2021 a oggi (14" e 16"):
   - MacBook Pro 14"/16" 2021 (M1 Pro / M1 Max)
   - MacBook Pro 14"/16" 2023 (M2 Pro / M2 Max)
   - MacBook Pro 14"/16" fine 2023 (M3 / M3 Pro / M3 Max)
   - MacBook Pro 14"/16" successivi disponibili sul mercato dell'usato
2. Stimare per ciascun modello base/configurazione standard:
   - Prezzo medio dell'usato in Italia (€)
   - Prezzo minimo realistico d'acquisto / Soglia "Affare" (€)
3. Includere la voce speciale `mbp_broken_any` per modelli MacBook Pro rotti/ricambi almeno M1 (< 300€).
4. Generare e salvare il file `config_modelli.json` nella root del progetto.

### Formato file output (`config_modelli.json`):
```json
[
  {
    "id": "mbp_14_m1_pro",
    "attivo": true,
    "anno": 2021,
    "display_pollici": 14,
    "chip": "M1 Pro",
    "ram_min_gb": 16,
    "ssd_min_gb": 512,
    "prezzo_medio_stimato": 1150,
    "prezzo_max_soglia_affare": 700
  },
  {
    "id": "mbp_broken_any",
    "attivo": true,
    "nome_commerciale": "MacBook Pro Rotto / Per Ricambi (almeno M1)",
    "anno": ">=2020",
    "display_pollici": "qualsiasi",
    "chip": "M1 o superiore",
    "ram_min_gb": 0,
    "ssd_min_gb": 0,
    "prezzo_medio_stimato": 300,
    "prezzo_max_soglia_affare": 300
  }
]
```

---

## AGENTE 2: NLP & QUERY PATTERN SPECIALIST
### Responsabilità:
1. Gestire la variabilità ortografica degli annunci privati su Subito.it.
2. Definire:
   - Query di ricerca URL da passare al motore di scraping (inclusi target per MacBook Pro rotti/ricambi).
   - Espressioni regolari (Regex) e liste di token per validare titolo e descrizione.
3. Creare il file `patterns_ricerca.json` contenente:
   - Varianti MacBook Pro: `macbook pro`, `mac book pro`, `mbp`, `mcbook pro`, `macbok pro`
   - Varianti Pollici: `14"`, `14 pollici`, `14p`, `14-inch`, `16"`, `16 pollici`, `16-inch`, `16p`
   - Varianti RAM (>= 16GB): `16gb`, `16 gb`, `16 giga`, `32gb`, `32 gb`, `64gb`, `64 gb`, `18gb`, `36gb`
   - Varianti SSD (>= 512GB): `512gb`, `512 gb`, `512giga`, `1tb`, `1 tb`, `1tera`, `2tb`, `2 tb`
   - Token per modelli rotti (`broken_tokens`): `rotto`, `rotta`, `ricambi`, `per parti di ricambio`, `non funzionante`, `non si accende`, `schermo rotto`, `crepato`, `guasto`, `da riparare`, `blocco icloud`, `bloccato`
   - Token di esclusione assoluta (`negative_tokens`): accessori (cavi, cover, custodie, caricatori, caricabatterie, batterie sfuse, scatole vuote, adattatori, pellicole)
4. Fornire una funzione di parsing logico (`nlp_matcher.py`) per:
   - Se presente un token di rottura/ricambi: validare che sia un MacBook Pro con almeno chip M1 (esclusi Air e Intel) e prezzo < 300€.
   - Altrimenti: validare i requisiti minimi di un MacBook Pro Apple Silicon funzionante (14"/16", RAM >= 16GB, SSD >= 512GB).

---

## AGENTE 3: SCRAPER & BOT NOTIFICATORE
### Responsabilità:
1. Creare uno script Python autonomo (`scraper.py`) eseguibile a intervalli (default: 30 minuti) o one-shot (`--once`).
2. Canale di notifica scelto: **Telegram Bot**.
3. Meccanismo operativo:
   - Interrogare Subito.it per le query configurate.
   - Estrarre per ogni annuncio: Titolo, Prezzo, Località, Link URL, Descrizione completa, Data.
   - Mantenere un database locale (`seen_ads.json`) per memorizzare gli ID annunci già notificati ed evitare duplicati.
   - Validare ogni nuovo annuncio tramite `nlp_matcher.py`.
   - Se l'annuncio rispetta i criteri, inviare alert immediato su Telegram:
     * Per MacBook Pro funzionanti:
       ```text
       🚨 NUOVO AFFARE MACBOOK PRO!
       💻 Modello stimato: MacBook Pro 14" (M1 Pro)
       💰 Prezzo: 650 € (Soglia max: 700 €)
       📍 Luogo: Milano (MI)
       🔗 Link: https://www.subito.it/...
       ```
     * Per MacBook Pro rotti / ricambi (< 300€):
       ```text
       🔧 MACBOOK PRO ROTTO / PER RICAMBI (< 300€)!
       💻 Titolo: MacBook Pro 13 M1 rotto per ricambi
       ⚙️ Chip stimato: M1
       💰 Prezzo: 150 € (Soglia max: 300 €)
       📍 Luogo: Roma (RM)
       🔗 Link: https://www.subito.it/...
       ⚠️ Segnalato come guasto / da riparare / per ricambi
       ```
4. Creare `requirements.txt` e un file `.env` per configurare:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `CHECK_INTERVAL_MINUTES=30`

---

## PROTOCOLLO DI COLLABORAZIONE TRA AGENTI
1. Agente 1 genera e gestisce `config_modelli.json`.
2. Agente 2 genera `patterns_ricerca.json` e la logica di filtering/regex in `nlp_matcher.py`.
3. Agente 3 legge le configurazioni, implementa lo scraper e il modulo Telegram in `scraper.py`, gestisce `seen_ads.json` e il loop temporizzato.