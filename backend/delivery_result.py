"""Wspolny, bezpieczny kontrakt wyniku dostarczenia wiadomosci."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


DeliveryOutcome = Literal["sent", "retry", "failed", "uncertain"]
_DELIVERY_OUTCOMES = frozenset({"sent", "retry", "failed", "uncertain"})


@dataclass(frozen=True)
class DeliveryResult:
    """Niemutowalny wynik adaptera bez tresci odpowiedzi providera ani PII."""

    outcome: DeliveryOutcome
    code: str
    provider_message_id: Optional[str] = None
    status_code: Optional[int] = None

    def __post_init__(self) -> None:
        if self.outcome not in _DELIVERY_OUTCOMES:
            raise ValueError("Nieznany wynik dostarczenia.")
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("Kod wyniku dostarczenia jest wymagany.")
