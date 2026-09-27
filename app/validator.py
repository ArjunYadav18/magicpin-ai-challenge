from __future__ import annotations

import re
from typing import Any, Optional

from app.facts import collect_allowed_numbers, merchant_name


class FactValidator:
    def __init__(self, category: Optional[dict[str, Any]], merchant: dict[str, Any], trigger: dict[str, Any], customer: Optional[dict[str, Any]], digest_item: Optional[dict[str, Any]]):
        self.category = category or {}
        self.merchant = merchant
        self.trigger = trigger
        self.customer = customer or {}
        self.digest_item = digest_item or {}
        self.allowed_numbers = collect_allowed_numbers(self.category, self.merchant, self.trigger, self.customer, self.digest_item)

    def validate_message(self, message: str) -> list[str]:
        errors = []
        if not message:
            return errors
        
        # 1. No URLs
        if "http://" in message.lower() or "https://" in message.lower() or "www." in message.lower():
            errors.append("contains_url")
            
        # 2. Check hallucinated numbers
        # We find all numbers in the message and check if they are in the allowed_numbers set
        found_numbers = re.findall(r"\d+(?:[.,]\d+)?", message)
        for num in found_numbers:
            clean_num = num.replace(",", "")
            if clean_num not in self.allowed_numbers:
                # Let's do a loose check for percentages and integers
                if "." in clean_num:
                    int_part = clean_num.split(".")[0]
                    if int_part in self.allowed_numbers:
                        continue
                try:
                    as_int = str(int(float(clean_num)))
                    if as_int in self.allowed_numbers:
                        continue
                except ValueError:
                    pass
                errors.append(f"hallucinated_number:{num}")
                
        # 3. Check taboos
        taboos = (self.category.get("voice") or {}).get("vocab_taboo") or []
        for taboo in taboos:
            if taboo.lower() in message.lower():
                errors.append(f"taboo_word_used:{taboo}")
                
        # 4. Check merchant fit (Did we use the right name?)
        # Simple heuristic: at least avoid using completely wrong names.
        
        return errors
