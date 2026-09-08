"""NLP Matcher & Filter Engine for MacBook Pro Hunter.

Classifies Subito.it listing titles and descriptions according to hardware requirements
and matches them against target models defined in config_modelli.json, including
broken/for parts MacBook deals under 400€.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MatchResult:
    is_match: bool
    is_broken: bool = False
    rejection_reason: Optional[str] = None
    matched_model: Optional[Dict[str, Any]] = None
    extracted_chip: Optional[str] = None
    extracted_screen: Optional[int] = None
    extracted_ram: Optional[int] = None
    extracted_ssd: Optional[int] = None
    bargain_price: Optional[float] = None
    market_price: Optional[float] = None


class NLPMatcher:
    def __init__(
        self,
        patterns_path: str | Path = "patterns_ricerca.json",
        models_path: str | Path = "config_modelli.json",
    ) -> None:
        self.patterns_path = Path(patterns_path)
        self.models_path = Path(models_path)
        self.patterns = self._load_json(self.patterns_path)
        self.models = self._load_json(self.models_path)

        # Pre-compile negative regex patterns (accessories, covers, cables)
        self.negative_patterns = [
            re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
            for token in self.patterns.get("negative_tokens", [])
        ]

        # Pre-compile broken regex patterns (damaged, for parts, icloud locked)
        self.broken_patterns = [
            re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
            for token in self.patterns.get("broken_tokens", [])
        ]

    @staticmethod
    def _load_json(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text.lower()
        cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def check_negative_tokens(self, text: str) -> Optional[str]:
        norm_text = self.normalize_text(text)
        for pattern in self.negative_patterns:
            if pattern.search(norm_text):
                return f"Contains accessory/excluded token: '{pattern.pattern}'"
        return None

    def check_broken_tokens(self, text: str) -> Optional[str]:
        norm_text = self.normalize_text(text)
        for pattern in self.broken_patterns:
            if pattern.search(norm_text):
                return f"Broken/parts token detected: '{pattern.pattern}'"
        return None

    def extract_screen_size(self, text: str) -> Optional[int]:
        norm = self.normalize_text(text)
        screen_config = self.patterns.get("screen_sizes", {})

        for variant in screen_config.get("16", []):
            escaped = re.escape(variant)
            if re.search(rf"(?:^|[^\d]){escaped}(?:[^\d]|$)", norm):
                return 16

        for variant in screen_config.get("14", []):
            escaped = re.escape(variant)
            if re.search(rf"(?:^|[^\d]){escaped}(?:[^\d]|$)", norm):
                return 14

        return None

    def extract_chip(self, text: str) -> Optional[str]:
        norm = self.normalize_text(text)
        chips = self.patterns.get("chips", [])
        for chip_info in chips:
            pattern = chip_info["regex"]
            if re.search(pattern, norm, re.IGNORECASE):
                return chip_info["name"]
        return None

    def extract_ram(self, text: str) -> Optional[int]:
        norm = self.normalize_text(text)
        ram_pattern = re.compile(
            r"\b(16|18|24|32|36|48|64|96|128)\s*(?:gb|giga|ram)\b|\bram\s*(?:di|:)?\s*(16|18|24|32|36|48|64|96|128)\b",
            re.IGNORECASE,
        )
        match = ram_pattern.search(norm)
        if match:
            val = match.group(1) or match.group(2)
            if val:
                return int(val)
        return None

    def extract_ssd(self, text: str) -> Optional[int]:
        norm = self.normalize_text(text)
        tb_match = re.search(r"\b(1|2|4|8)\s*(?:tb|tera)\b|\bssd\s*(?:di|:)?\s*(1|2|4|8)\s*tb\b", norm, re.IGNORECASE)
        if tb_match:
            tb_val = int(tb_match.group(1) or tb_match.group(2))
            return tb_val * 1024

        gb_match = re.search(r"\b(512|1000|1024|2000|2048)\s*(?:gb|giga|ssd)\b", norm, re.IGNORECASE)
        if gb_match:
            return int(gb_match.group(1))

        return None

    def evaluate_ad(
        self,
        title: str,
        price: Optional[float],
        description: str = "",
        min_working_price: float = 450.0,
    ) -> MatchResult:
        norm_title = self.normalize_text(title)
        combined_text = f"{title} {description}"

        # 0. Title must actually refer to MacBook / MBP
        macbook_variants = self.patterns.get("macbook_variants", ["macbook", "mac book", "mbp"])
        has_macbook_in_title = any(v in norm_title for v in macbook_variants)
        if not has_macbook_in_title:
            return MatchResult(
                is_match=False,
                rejection_reason="Title does not contain MacBook / MBP keywords (likely an accessory)",
            )

        # 1. Pure accessory exclusion check (cables, covers, boxes, adapters)
        neg_reason = self.check_negative_tokens(combined_text)
        if neg_reason:
            return MatchResult(is_match=False, rejection_reason=neg_reason)

        # 2. Check if it's a BROKEN / FOR PARTS MacBook Pro (must be Pro and at least M1)
        broken_reason = self.check_broken_tokens(combined_text)
        if broken_reason:
            broken_model_cfg = next((m for m in self.models if m.get("id") == "mbp_broken_any"), None)
            if broken_model_cfg and broken_model_cfg.get("attivo", True):
                max_broken_threshold = float(broken_model_cfg.get("prezzo_max_soglia_affare", 300.0))
                market_broken_est = float(broken_model_cfg.get("prezzo_medio_stimato", 300.0))
                norm_combined = self.normalize_text(combined_text)

                # Must be MacBook Pro (exclude Air and non-Pro)
                if re.search(r"\b(macbook\s*air|mac\s*book\s*air)\b", norm_combined):
                    return MatchResult(is_match=False, rejection_reason="MacBook rotto ma è MacBook Air (richiesto MacBook Pro)")
                if not re.search(r"\b(pro|mbp)\b", norm_combined):
                    return MatchResult(is_match=False, rejection_reason="MacBook rotto ma non specificato Pro (richiesto MacBook Pro)")

                # Must be at least M1 (Apple Silicon M-series)
                if re.search(r"\b(intel|core\s*i[3579]|i5|i7|i9)\b", norm_combined):
                    return MatchResult(is_match=False, rejection_reason="MacBook Pro rotto ma è Intel (richiesto almeno chip M1)")

                chip = self.extract_chip(combined_text)
                if not chip:
                    return MatchResult(
                        is_match=False,
                        rejection_reason="MacBook Pro rotto ma nessun chip Apple Silicon (M1/M2/M3/M4) rilevato",
                    )

                if price is None or price <= 0:
                    return MatchResult(is_match=False, rejection_reason="Prezzo mancante per MacBook Pro rotto")

                if price < 15.0:
                    return MatchResult(
                        is_match=False,
                        rejection_reason=f"Prezzo {price}€ troppo basso (<15€, probabile accessorio/componente)",
                    )

                if price < max_broken_threshold:
                    # Valid broken MacBook Pro M-series deal!
                    screen = self.extract_screen_size(combined_text)
                    return MatchResult(
                        is_match=True,
                        is_broken=True,
                        matched_model=broken_model_cfg,
                        extracted_chip=chip,
                        extracted_screen=screen,
                        bargain_price=max_broken_threshold,
                        market_price=market_broken_est,
                    )
                else:
                    return MatchResult(
                        is_match=False,
                        rejection_reason=f"MacBook Pro {chip} rotto ma prezzo {price}€ >= soglia affare {max_broken_threshold}€",
                    )
            else:
                return MatchResult(
                    is_match=False,
                    rejection_reason="Modello rotto/ricambi ma categoria disattivata in config_modelli.json",
                )

        # 3. If NOT broken, evaluate as functional Apple Silicon MacBook Pro 14"/16"
        # Disqualify explicit non-compliant hardware for functional units
        norm_combined = self.normalize_text(combined_text)
        if re.search(r"\b8\s*(?:gb|giga|ram)\b", norm_combined):
            return MatchResult(is_match=False, rejection_reason="Contains disqualified RAM: 8GB")
        if re.search(r"\b(128|256)\s*(?:gb|giga|ssd)\b", norm_combined):
            return MatchResult(is_match=False, rejection_reason="Contains disqualified SSD: <512GB")
        if re.search(r"\b(13\"|13\s*pollici|13-inch|13,3|13\.3|15\"|15\s*pollici|macbook\s*air|intel|core\s*i[579])\b", norm_combined):
            return MatchResult(is_match=False, rejection_reason="Excluded model: 13/15 pollici, Air o Intel")

        chip = self.extract_chip(combined_text)
        if not chip:
            return MatchResult(
                is_match=False,
                rejection_reason="No supported Apple Silicon chip detected (M1 Pro/Max, M2 Pro/Max, M3 series, M4 series)",
            )

        screen_size = self.extract_screen_size(combined_text)
        if not screen_size:
            m = re.search(r"\b(14|16)\b", title)
            if m:
                screen_size = int(m.group(1))

        ram = self.extract_ram(combined_text)
        ssd = self.extract_ssd(combined_text)

        if chip == "M3" and (ram is None or ram < 16):
            return MatchResult(
                is_match=False,
                rejection_reason="Base M3 requires explicit confirmation of >=16GB RAM",
            )

        matched_candidates = []
        for model in self.models:
            if not model.get("attivo", True) or model.get("id") == "mbp_broken_any":
                continue
            if model.get("chip") != chip:
                continue
            if screen_size and model.get("display_pollici") != screen_size:
                continue
            if ram and ram < model.get("ram_min_gb", 16):
                continue
            if ssd and ssd < model.get("ssd_min_gb", 512):
                continue
            matched_candidates.append(model)

        if not matched_candidates:
            return MatchResult(
                is_match=False,
                rejection_reason=f"No active model matched for chip '{chip}' and screen '{screen_size}'",
                extracted_chip=chip,
                extracted_screen=screen_size,
                extracted_ram=ram,
                extracted_ssd=ssd,
            )

        best_model = matched_candidates[0]
        bargain_threshold = float(best_model.get("prezzo_max_soglia_affare", 0))
        market_price = float(best_model.get("prezzo_medio_stimato", 0))

        if price is None or price <= 0:
            return MatchResult(
                is_match=False,
                rejection_reason="Invalid or missing price",
                matched_model=best_model,
                extracted_chip=chip,
                extracted_screen=screen_size or best_model.get("display_pollici"),
                extracted_ram=ram,
                extracted_ssd=ssd,
                bargain_price=bargain_threshold,
                market_price=market_price,
            )

        if price < min_working_price:
            return MatchResult(
                is_match=False,
                rejection_reason=f"Price {price}€ below realistic minimum {min_working_price}€ for working unit (not marked as broken)",
                matched_model=best_model,
                extracted_chip=chip,
                extracted_screen=screen_size or best_model.get("display_pollici"),
                extracted_ram=ram,
                extracted_ssd=ssd,
                bargain_price=bargain_threshold,
                market_price=market_price,
            )

        if price > bargain_threshold:
            return MatchResult(
                is_match=False,
                rejection_reason=f"Price {price}€ exceeds bargain threshold {bargain_threshold}€ (market: {market_price}€)",
                matched_model=best_model,
                extracted_chip=chip,
                extracted_screen=screen_size or best_model.get("display_pollici"),
                extracted_ram=ram,
                extracted_ssd=ssd,
                bargain_price=bargain_threshold,
                market_price=market_price,
            )

        return MatchResult(
            is_match=True,
            is_broken=False,
            matched_model=best_model,
            extracted_chip=chip,
            extracted_screen=screen_size or best_model.get("display_pollici"),
            extracted_ram=ram or best_model.get("ram_min_gb"),
            extracted_ssd=ssd or best_model.get("ssd_min_gb"),
            bargain_price=bargain_threshold,
            market_price=market_price,
        )
