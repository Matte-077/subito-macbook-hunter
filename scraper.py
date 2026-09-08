#!/usr/bin/env python3
"""MacBook Pro Hunter - Agente 3: Scraper & Telegram Bot Notificatore

Esegue il monitoraggio continuo o one-shot di Subito.it per annunci MacBook Pro 14" e 16"
Apple Silicon a prezzi vantaggiosi, inviando notifiche istantanee su Telegram.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

from nlp_matcher import NLPMatcher, MatchResult

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MacBookProHunter")


class SubitoHunter:
    def __init__(
        self,
        config_path: str = "config_modelli.json",
        patterns_path: str = "patterns_ricerca.json",
        seen_ads_path: str = "seen_ads.json",
        dry_run: bool = False,
    ) -> None:
        self.seen_ads_path = Path(seen_ads_path)
        self.dry_run = dry_run
        self.matcher = NLPMatcher(patterns_path=patterns_path, models_path=config_path)
        self.seen_ids = self._load_seen_ads()

        # Telegram Configuration
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not self.bot_token or not self.chat_id:
            logger.warning(
                "⚠️ Variabili TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID non configurate in .env. "
                "Le notifiche verranno stampate solo a terminale."
            )

    def _load_seen_ads(self) -> Set[str]:
        if not self.seen_ads_path.exists():
            return set()
        try:
            with open(self.seen_ads_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                elif isinstance(data, dict):
                    return set(data.get("seen_ids", []))
        except Exception as e:
            logger.error(f"Errore lettura {self.seen_ads_path}: {e}. Verrà reinizializzato.")
        return set()

    def _save_seen_ads(self) -> None:
        try:
            with open(self.seen_ads_path, "w", encoding="utf-8") as f:
                json.dump({"seen_ids": sorted(list(self.seen_ids))}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore salvataggio {self.seen_ads_path}: {e}")

    def fetch_subito_page(self, query: str) -> Optional[str]:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.subito.it/annunci-italia/vendita/usato/?q={encoded_query}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        # 1. Primary method: curl_cffi (impersonates Chrome TLS & HTTP/2 to bypass Cloudflare/Akamai bot detection on Linux)
        if cffi_requests is not None:
            try:
                resp = cffi_requests.get(url, impersonate="chrome120", headers=headers, timeout=15)
                if resp.status_code == 200 and resp.text and "<script id=\"__NEXT_DATA__\"" in resp.text:
                    return resp.text
                elif resp.status_code != 200:
                    logger.debug(f"curl_cffi HTTP {resp.status_code} per '{query}'")
            except Exception as e:
                logger.debug(f"curl_cffi fallback to curl: {e}")

        # 2. Fallback method: system curl with redirect and decompression flags
        try:
            cmd = [
                "curl",
                "-sL",
                "--compressed",
                url,
                "-H", f"User-Agent: {headers['User-Agent']}",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H", "Accept-Language: it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "-H", "Sec-Ch-Ua: \"Chromium\";v=\"124\", \"Google Chrome\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
                "-H", "Sec-Ch-Ua-Mobile: ?0",
                "-H", "Sec-Ch-Ua-Platform: \"macOS\"",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout and "<script id=\"__NEXT_DATA__\"" in res.stdout:
                return res.stdout
        except Exception as e:
            logger.debug(f"Curl fallback to requests: {e}")

        # 3. Last fallback: standard requests
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.text
            else:
                logger.warning(f"Richiesta standard fallita per '{query}': HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"Errore connessione Subito.it per '{query}': {e}")

        return None

    def extract_ads_from_html(self, html: str) -> List[Dict[str, Any]]:
        m = re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", html, re.DOTALL)
        if not m:
            logger.warning(f"⚠️ __NEXT_DATA__ non trovato nella risposta (lunghezza HTML: {len(html)} caratteri).")
            return []

        try:
            data = json.loads(m.group(1))
            items = data.get("props", {}).get("pageProps", {}).get("initialState", {}).get("items", {})
            raw_list = items.get("originalList", [])
        except Exception as e:
            logger.error(f"Errore parsing JSON __NEXT_DATA__: {e}")
            return []

        extracted = []
        for raw_item in raw_list:
            urn = raw_item.get("urn", "")
            # Extract clean ID from urn or URL
            item_id = urn.split(":")[-1] if urn else ""

            subject = raw_item.get("subject", "").strip()
            body = raw_item.get("body", "").strip()
            date = raw_item.get("date", "")

            # Extract price
            features = raw_item.get("features", {})
            price_data = features.get("/price", {})
            price_vals = price_data.get("values", [])
            price_val = None
            if price_vals:
                raw_price_str = price_vals[0].get("key", "").replace(".", "").replace(",", ".")
                try:
                    price_val = float(raw_price_str)
                except ValueError:
                    pass

            # Extract location
            geo = raw_item.get("geo", {})
            city = geo.get("city", {}).get("value", "")
            province = geo.get("city", {}).get("shortName", "")
            town = geo.get("town", {}).get("value", "")
            location_parts = []
            if town:
                location_parts.append(town)
            elif city:
                location_parts.append(city)
            if province and province not in location_parts:
                location_parts.append(f"({province})")
            location = " ".join(location_parts) if location_parts else "Italia"

            # URL
            urls = raw_item.get("urls", {})
            url = urls.get("default", "")

            if not item_id and url:
                # Extract numeric id from url (e.g. "...-123456789.htm")
                id_match = re.search(r"-(\d+)\.htm", url)
                if id_match:
                    item_id = id_match.group(1)

            if item_id and subject:
                extracted.append({
                    "id": item_id,
                    "title": subject,
                    "description": body,
                    "price": price_val,
                    "location": location,
                    "url": url,
                    "date": date,
                })

        return extracted

    def send_telegram_alert(self, ad: Dict[str, Any], match: MatchResult) -> bool:
        bargain_threshold = int(match.bargain_price or 0)
        market_price = int(match.market_price or 0)
        price = int(ad["price"]) if ad.get("price") is not None else 0

        if match.is_broken:
            message = (
                f"🔧 <b>MACBOOK PRO ROTTO / PER RICAMBI (&lt; 300€)!</b>\n\n"
                f"💻 <b>Titolo:</b> {ad['title']}\n"
                f"⚙️ <b>Chip stimato:</b> {match.extracted_chip}\n"
                f"💰 <b>Prezzo:</b> {price} € <i>(Soglia max: {bargain_threshold} €)</i>\n"
                f"📍 <b>Luogo:</b> {ad['location']}\n"
                f"🔗 <b>Link:</b> {ad['url']}\n"
                f"⚠️ <i>Segnalato come guasto / da riparare / per ricambi</i>\n"
            )
        else:
            model_name = (
                match.matched_model.get("nome_commerciale")
                if match.matched_model
                else f"MacBook Pro {match.extracted_screen}\" ({match.extracted_chip})"
            )
            message = (
                f"🚨 <b>NUOVO AFFARE MACBOOK PRO!</b>\n\n"
                f"💻 <b>Modello:</b> {model_name}\n"
                f"💰 <b>Prezzo:</b> {price} € <i>(Soglia max affare: {bargain_threshold} €, Medio mercato: {market_price} €)</i>\n"
                f"📍 <b>Luogo:</b> {ad['location']}\n"
                f"🔗 <b>Link:</b> {ad['url']}\n"
            )

        if self.dry_run or not self.bot_token or not self.chat_id:
            logger.info("📢 [TELEGRAM NOTIFICATION SIMULATED]:\n" + message)
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✅ Notifica Telegram inviata con successo per annuncio ID {ad['id']}")
                return True
            else:
                logger.error(f"❌ Errore invio Telegram HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"❌ Eccezione durante invio notifica Telegram: {e}")

        return False

    def scan_once(self) -> int:
        queries = self.matcher.patterns.get("search_queries", ["macbook pro 14", "macbook pro 16"])
        new_deals_count = 0
        total_seen_this_run = 0

        logger.info(f"🔍 Avvio scansione con {len(queries)} query di ricerca...")

        for query in queries:
            logger.info(f"🔎 Ricerca: '{query}'")
            html = self.fetch_subito_page(query)
            if not html:
                continue

            ads = self.extract_ads_from_html(html)
            logger.info(f"  Trovati {len(ads)} annunci.")

            for ad in ads:
                ad_id = ad["id"]
                if ad_id in self.seen_ids:
                    continue

                total_seen_this_run += 1
                match = self.matcher.evaluate_ad(
                    title=ad["title"],
                    price=ad["price"],
                    description=ad["description"],
                )

                if match.is_match:
                    logger.info(
                        f"🎯 AFFARE TROVATO! [{ad['id']}] {ad['title']} - {ad['price']}€ @ {ad['location']}"
                    )
                    self.send_telegram_alert(ad, match)
                    new_deals_count += 1
                else:
                    logger.debug(
                        f"Scartato [{ad_id}] '{ad['title'][:40]}...': {match.rejection_reason}"
                    )

                # Mark as seen so we don't evaluate or notify twice
                self.seen_ids.add(ad_id)

            # Polite pause between queries
            time.sleep(1.5)

        self._save_seen_ads()
        logger.info(
            f"✨ Scansione completata: {total_seen_this_run} nuovi annunci esaminati, {new_deals_count} affari segnalati."
        )
        return new_deals_count

    def run_loop(self, interval_minutes: int) -> None:
        logger.info(f"🚀 MacBook Pro Hunter avviato. Ciclo ogni {interval_minutes} minuti.")
        while True:
            try:
                self.scan_once()
            except KeyboardInterrupt:
                logger.info("Arresto manuale del bot.")
                break
            except Exception as e:
                logger.exception(f"Errore imprevisto durante la scansione: {e}")

            logger.info(f"💤 Prossimo controllo tra {interval_minutes} minuti ({datetime.now().strftime('%H:%M:%S')}).")
            time.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Subito.it MacBook Pro Hunter")
    parser.add_argument("--once", action="store_true", help="Esegui una singola scansione ed esci")
    parser.add_argument("--dry-run", action="store_true", help="Simula le notifiche senza inviare messaggi reali a Telegram")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Intervallo in minuti per il monitoraggio continuo (default da .env o 30 min)",
    )
    parser.add_argument("--reset-seen", action="store_true", help="Cancella la lista degli annunci visti")
    args = parser.parse_args()

    seen_file = Path("seen_ads.json")
    if args.reset_seen and seen_file.exists():
        seen_file.unlink()
        logger.info("🗑️ seen_ads.json rimosso.")

    interval = args.interval
    if interval is None:
        interval_env = os.getenv("CHECK_INTERVAL_MINUTES", "30")
        try:
            interval = int(interval_env)
        except ValueError:
            interval = 30

    hunter = SubitoHunter(dry_run=args.dry_run)

    if args.once:
        hunter.scan_once()
    else:
        hunter.run_loop(interval_minutes=interval)


if __name__ == "__main__":
    main()
