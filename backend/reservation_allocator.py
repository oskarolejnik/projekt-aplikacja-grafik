"""Czysty, wspólny evaluator przydziału zasobów rezerwacji (R4).

Moduł celowo nie zna routerów ani ``main.py``. Wywołujący przekazuje opublikowany
snapshot stołów, jawne kombinacje i zajęte identyfikatory. Reguły czasu i
pojemności operacyjnej są oceniane przez kanoniczny evaluator R3, a ranking
zasobów pozostaje w czystym module :mod:`seating`.

To jest warstwa decyzji, nie zapisu: nie wykonuje commita ani nie tworzy claimów.
Mutacja musi ponownie wywołać evaluator pod ``begin_locked_write`` i dopiero wtedy
zapisać zwrócone ``allocation`` w tej samej transakcji co ``Termin``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Iterable, Literal, Mapping, Sequence

import reservation_rules
import seating


AllocationDecision = Literal["allow", "override_required", "deny"]
AllocationIntent = Literal[
    "quote", "create", "edit", "simulate", "assign", "reoptimize",
]


@dataclass(frozen=True)
class AllocationRequest:
    """Dane wspólne dla widgetu, recepcji, hosta i symulatora.

    ``preferred_room_id`` jest preferencją miękką. Pole ``sala_id`` pozostaje
    wygodnym aliasem dla klientów domenowych używających nazewnictwa R3.
    """

    data: date
    godz_od: time
    liczba_osob: int
    kanal: str = "wewnetrzna"
    godz_do: time | None = None
    intent: AllocationIntent = "quote"
    existing_termin_id: int | None = None
    preferred_room_id: int | None = None
    sala_id: int | None = None
    preferred_zone: str | None = None
    preferred_features: tuple[str, ...] = ()
    preserve_existing_room_access: bool = False
    preserve_explicit_interval: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.liczba_osob, bool) or int(self.liczba_osob) < 1:
            raise ValueError("liczba_osob musi być dodatnia")
        object.__setattr__(self, "liczba_osob", int(self.liczba_osob))
        object.__setattr__(
            self,
            "kanal",
            reservation_rules.normalise_channel(self.kanal),
        )
        if self.intent not in {
            "quote", "create", "edit", "simulate", "assign", "reoptimize",
        }:
            raise ValueError("nieobsługiwany intent alokacji")
        if (
            self.preferred_room_id is not None
            and self.sala_id is not None
            and self.preferred_room_id != self.sala_id
        ):
            raise ValueError("preferred_room_id i sala_id wskazują różne sale")
        room_id = (
            self.preferred_room_id
            if self.preferred_room_id is not None
            else self.sala_id
        )
        object.__setattr__(self, "preferred_room_id", room_id)
        object.__setattr__(self, "sala_id", room_id)
        object.__setattr__(
            self,
            "preferred_zone",
            str(self.preferred_zone or "").strip() or None,
        )
        features = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.preferred_features
                if str(value).strip()
            )
        )
        object.__setattr__(self, "preferred_features", features)

    @property
    def rule_intent(
        self,
    ) -> Literal["quote", "create", "edit", "simulate", "assign"]:
        if self.intent in {"assign", "reoptimize"}:
            return "assign"
        return self.intent


@dataclass(frozen=True)
class AllocationReason:
    """Stabilny kod dla UI wraz z komunikatem zrozumiałym dla operatora."""

    code: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {"code": self.code, "message": self.message}
        if self.metadata:
            out["metadata"] = dict(self.metadata)
        return out


@dataclass(frozen=True)
class AllocationCandidate:
    """Kandydat bez surowego kosztu i wewnętrznych wag rankingu."""

    table_ids: tuple[int, ...]
    table_names: tuple[str, ...]
    room_id: int | None
    room_name: str | None
    name: str | None
    capacity: int
    combination: bool
    plan_version_id: int | None
    plan_combination_id: int | None
    unused_seats: int
    decision: AllocationDecision
    reasons: tuple[AllocationReason, ...] = ()
    ranking_cost: float = field(default=0.0, repr=False, compare=False)

    @property
    def allocation(self) -> dict[str, Any]:
        """Dokładny payload potrzebny do ustawienia ``Termin`` i proweniencji."""
        return {
            "stolik_id": self.table_ids[0],
            "stoliki_dodatkowe": list(self.table_ids[1:]) or None,
            "stoliki": list(self.table_ids),
            "sala_id": self.room_id,
            "przydzial_wersja_planu_id": self.plan_version_id,
            "przydzial_kombinacja_planu_id": self.plan_combination_id,
            "auto_przydzielony": True,
        }

    def to_dict(self, *, expose_exact: bool = True) -> dict[str, Any]:
        if not expose_exact:
            return {"decision": self.decision}
        return {
            "kind": "combination" if self.combination else "single_table",
            "table_count": len(self.table_ids),
            "capacity": self.capacity,
            "unused_seats": self.unused_seats,
            "decision": self.decision,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "table_ids": list(self.table_ids),
            "table_names": list(self.table_names),
            "room_id": self.room_id,
            "room_name": self.room_name,
            "name": self.name,
            "plan_version_id": self.plan_version_id,
            "plan_combination_id": self.plan_combination_id,
        }

    def to_display_dict(
        self,
        *,
        visit_end: str | None,
        expose_exact: bool,
        state: str = "preview",
    ) -> dict[str, Any]:
        """Kontrakt prezentacyjny wspólny dla panelu i publicznego widgetu."""
        out: dict[str, Any] = {
            "state": state,
            "visibility": "exact" if expose_exact else "availability_only",
            "visit_end": visit_end,
        }
        if not expose_exact:
            return out
        out.update({
            "kind": "combination" if self.combination else "single_table",
            "room": (
                {"id": self.room_id, "name": self.room_name}
                if self.room_id is not None or self.room_name is not None else None
            ),
            "tables": [
                {"id": table_id, "name": table_name}
                for table_id, table_name in zip(self.table_ids, self.table_names)
            ],
            "capacity": self.capacity,
            "reasons": [reason.to_dict() for reason in self.reasons],
        })
        return out


@dataclass(frozen=True)
class AllocationResult:
    """Połączona decyzja R3 i rekomendacja zasobu R4."""

    request: AllocationRequest
    evaluation: reservation_rules.RuleEvaluation
    decision: AllocationDecision
    selected: AllocationCandidate | None = None
    candidates: tuple[AllocationCandidate, ...] = ()
    alternatives: tuple[AllocationCandidate, ...] = ()
    reasons: tuple[AllocationReason, ...] = ()
    code: str | None = None
    rule: str | None = None
    message: str | None = None

    @property
    def available(self) -> bool:
        return self.decision == "allow" and self.selected is not None

    @property
    def allocation(self) -> dict[str, Any] | None:
        return self.selected.allocation if self.selected is not None else None

    def to_dict(self, *, expose_exact: bool = True) -> dict[str, Any]:
        """Serializuje wynik; wariant publiczny nie ujawnia układu sali.

        Zachowujemy pola kontraktu R3. Dla odpowiedzi publicznej tablice techniczne
        pozostają obecne, lecz są bezpiecznie zredukowane tak jak w publicznym
        handlerze błędów rezerwacji.
        """
        out = self.evaluation.to_dict()
        visit_end = out.get("visit_end")
        out.update({
            "available": self.available,
            "decision": self.decision,
            "code": self.code,
            "rule": self.rule,
            "message": self.message,
            "can_override": self.decision == "override_required",
            "resource_allocation": (
                "recommended" if self.selected is not None else "unavailable"
            ),
            "selected": (
                self.selected.to_dict(expose_exact=expose_exact)
                if self.selected is not None else None
            ),
            "allocation": (
                self.selected.to_display_dict(
                    visit_end=visit_end,
                    expose_exact=expose_exact,
                ) if self.selected is not None else None
            ),
            "candidates": [
                candidate.to_dict(expose_exact=expose_exact)
                for candidate in self.candidates
            ] if expose_exact else [],
            "alternatives": [
                {
                    "kind": "resource",
                    "allocation": candidate.to_display_dict(
                        visit_end=visit_end,
                        expose_exact=expose_exact,
                    ),
                }
                for candidate in self.alternatives
            ] if expose_exact else [],
            "reasons": (
                [reason.to_dict() for reason in self.reasons]
                if expose_exact else []
            ),
        })
        if not expose_exact:
            out.pop("buffer_min", None)
            service = out.get("service")
            if isinstance(service, dict):
                out["service"] = {
                    key: service.get(key)
                    for key in ("name", "godz_od", "godz_do")
                }
            out["checks"] = []
            out["applied_rules"] = []
            out["violations"] = [
                {
                    "code": item.get("code"),
                    "rule": item.get("rule"),
                    "message": item.get("message"),
                    "overrideable_by_operator": item.get(
                        "overrideable_by_operator", False,
                    ),
                }
                for item in (out.get("violations") or [])
            ]
        return out


@dataclass(frozen=True)
class _EvaluatedCandidate:
    candidate: AllocationCandidate
    evaluation: reservation_rules.RuleEvaluation
    raw: Mapping[str, Any]
    rank: int


def _rule_request(
    request: AllocationRequest,
    *,
    room_id: int | None,
) -> reservation_rules.RuleRequest:
    return reservation_rules.RuleRequest(
        data=request.data,
        godz_od=request.godz_od,
        godz_do=request.godz_do,
        liczba_osob=request.liczba_osob,
        kanal=request.kanal,
        sala_id=room_id,
        existing_termin_id=request.existing_termin_id,
        intent=request.rule_intent,
        preserve_existing_room_access=request.preserve_existing_room_access,
        preserve_explicit_interval=request.preserve_explicit_interval,
    )


def _violation_reasons(
    evaluation: reservation_rules.RuleEvaluation,
) -> tuple[AllocationReason, ...]:
    return tuple(
        AllocationReason(
            code=item.code,
            message=item.message,
            metadata={"rule": item.rule},
        )
        for item in evaluation.violations
    )


def _candidate_reasons(
    raw: Mapping[str, Any],
    evaluation: reservation_rules.RuleEvaluation,
    request: AllocationRequest,
) -> tuple[AllocationReason, ...]:
    unused = max(0, int(raw.get("nadmiar_miejsc") or 0))
    reasons: list[AllocationReason] = []
    if unused == 0:
        reasons.append(AllocationReason(
            "EXACT_CAPACITY",
            "Pojemność zestawu dokładnie odpowiada liczbie gości.",
        ))
    else:
        reasons.append(AllocationReason(
            "CAPACITY_FIT",
            "Zestaw mieści grupę z niewielkim zapasem miejsc.",
            {"unused_seats": unused},
        ))
    table_count = len(raw.get("stoliki") or ())
    if table_count == 1:
        reasons.append(AllocationReason(
            "SINGLE_TABLE",
            "Grupa mieści się przy jednym stoliku.",
        ))
    else:
        reasons.append(AllocationReason(
            "TABLE_COMBINATION",
            "Grupa mieści się przy dozwolonym zestawie połączonych stolików.",
            {"table_count": table_count},
        ))
    if (
        request.preferred_room_id is not None
        and raw.get("sala_id") == request.preferred_room_id
    ):
        reasons.append(AllocationReason(
            "PREFERRED_ROOM",
            "Kandydat znajduje się w preferowanej sali.",
        ))
    if request.preferred_zone and all(
        row.get("strefa") == request.preferred_zone
        for row in raw.get("_stoly", ())
    ):
        reasons.append(AllocationReason(
            "PREFERRED_ZONE",
            "Kandydat znajduje się w preferowanej strefie gościa.",
        ))
    if raw.get("strategia_zapelniania") == "wypelniaj_kolejno":
        reasons.append(AllocationReason(
            "STRICT_ROOM_PRIORITY",
            "Kandydat respektuje kolejność zapełniania sal.",
        ))
    if evaluation.decision == "allow":
        reasons.append(AllocationReason(
            "RULES_ALLOW",
            "Kandydat spełnia reguły rezerwacji dla tej sali i kanału.",
        ))
    elif evaluation.decision == "override_required":
        reasons.append(AllocationReason(
            "RULE_OVERRIDE_REQUIRED",
            "Kandydat wymaga jawnego potwierdzenia wyjątku przez operatora.",
        ))
        reasons.extend(_violation_reasons(evaluation))
    return tuple(reasons)


def _room_name(table_rows: Sequence[Mapping[str, Any]]) -> str | None:
    names = {
        str(row.get("sala_nazwa") or row.get("strefa")).strip()
        for row in table_rows
        if (row.get("sala_nazwa") or row.get("strefa")) not in (None, "")
    }
    return next(iter(names)) if len(names) == 1 else None


def _candidate_is_within_one_room(
    raw: Mapping[str, Any],
    tables_by_id: Mapping[int, Mapping[str, Any]],
) -> bool:
    """Odrzuca uszkodzone legacy zestawy spinające zasoby z różnych sal."""
    try:
        rows = [tables_by_id[int(value)] for value in (raw.get("stoliki") or ())]
    except (KeyError, TypeError, ValueError):
        return False
    if not rows:
        return False

    explicit_room_ids = {row.get("sala_id") for row in rows}
    if any(room_id is not None for room_id in explicit_room_ids):
        return len(explicit_room_ids) == 1

    legacy_zones = {
        str(row.get("strefa") or "").strip().casefold()
        for row in rows
    }
    return len(legacy_zones) == 1


def _wrap_candidate(
    raw: Mapping[str, Any],
    *,
    tables_by_id: Mapping[int, Mapping[str, Any]],
    evaluation: reservation_rules.RuleEvaluation,
    request: AllocationRequest,
) -> AllocationCandidate:
    table_ids = tuple(int(value) for value in (raw.get("stoliki") or ()))
    table_rows = [tables_by_id[value] for value in table_ids]
    reason_input = {**raw, "_stoly": table_rows}
    return AllocationCandidate(
        table_ids=table_ids,
        table_names=tuple(str(row.get("nazwa") or value) for row, value in zip(
            table_rows, table_ids,
        )),
        room_id=raw.get("sala_id"),
        room_name=_room_name(table_rows),
        name=raw.get("nazwa"),
        capacity=max(0, int(raw.get("suma_pojemnosci") or 0)),
        combination=bool(raw.get("kombinacja")),
        plan_version_id=raw.get("wersja_planu_id"),
        plan_combination_id=raw.get("kombinacja_planu_id"),
        unused_seats=max(0, int(raw.get("nadmiar_miejsc") or 0)),
        decision=evaluation.decision,
        reasons=_candidate_reasons(reason_input, evaluation, request),
        ranking_cost=float(raw.get("koszt") or 0.0),
    )


def _ordered(
    rows: Sequence[_EvaluatedCandidate],
    *,
    preferred_room_id: int | None,
) -> list[_EvaluatedCandidate]:
    """Stosuje ścisłą kolejność sal przed miękkimi preferencjami."""
    rows = list(rows)
    strict = [
        row for row in rows
        if row.raw.get("strategia_zapelniania") == "wypelniaj_kolejno"
        and row.raw.get("sala_id") is not None
    ]
    if strict:
        first_room = min(
            (
                int(row.raw.get("priorytet_sali") or 0),
                int(row.raw.get("kolejnosc_sali") or 0),
                int(row.raw["sala_id"]),
            )
            for row in strict
        )
        return sorted(rows, key=lambda row: (
            0 if (
                row.raw.get("strategia_zapelniania") == "wypelniaj_kolejno"
                and (
                    int(row.raw.get("priorytet_sali") or 0),
                    int(row.raw.get("kolejnosc_sali") or 0),
                    int(row.raw["sala_id"]),
                ) == first_room
            ) else 1,
            0 if row.raw.get("strategia_zapelniania") == "wypelniaj_kolejno" else 1,
            int(row.raw.get("priorytet_sali") or 0),
            int(row.raw.get("kolejnosc_sali") or 0),
            row.rank,
        ))
    return sorted(rows, key=lambda row: (
        0 if (
            preferred_room_id is not None
            and row.raw.get("sala_id") == preferred_room_id
        ) else 1,
        row.rank,
    ))


def _no_resource_result(
    request: AllocationRequest,
    evaluation: reservation_rules.RuleEvaluation,
    *,
    potential: Sequence[Mapping[str, Any]],
    occupied: set[int],
) -> AllocationResult:
    blocked = [
        raw for raw in potential
        if set(int(value) for value in (raw.get("stoliki") or ())) & occupied
    ]
    if blocked:
        combination_blocked = any(len(raw.get("stoliki") or ()) > 1 for raw in blocked)
        reason = AllocationReason(
            "RESOURCE_COMPONENT_OCCUPIED" if combination_blocked else "RESOURCE_OCCUPIED",
            (
                "Co najmniej jeden składnik pasującego zestawu jest zajęty."
                if combination_blocked
                else "Pasujący stolik jest zajęty w tym czasie."
            ),
            {"blocked_candidates": len(blocked)},
        )
    else:
        reason = AllocationReason(
            "NO_CAPACITY_MATCH",
            "Brak aktywnego stolika lub dozwolonej kombinacji dla tej liczby gości.",
        )
    return AllocationResult(
        request=request,
        evaluation=evaluation,
        decision="deny",
        reasons=(reason,),
        code="NO_TABLE_CANDIDATE",
        rule="table",
        message="Brak wolnego stołu dla tej grupy w tym czasie.",
    )


def evaluate_allocation(
    db,
    request: AllocationRequest,
    *,
    tables: Sequence[Mapping[str, Any]],
    combinations: Sequence[Mapping[str, Any]],
    occupied_table_ids: Iterable[int],
    adjacency: Sequence[tuple[int, int]] = (),
    section_load: Mapping[str, int] | None = None,
    now: datetime | None = None,
    alternative_limit: int = 3,
) -> AllocationResult:
    """Ocenia reguły i wybiera najlepszy bezpieczny zasób bez zapisu do bazy."""
    if isinstance(alternative_limit, bool) or int(alternative_limit) < 0:
        raise ValueError("alternative_limit nie może być ujemny")
    alternative_limit = int(alternative_limit)
    table_rows = tuple(dict(row) for row in tables)
    combination_rows = tuple(dict(row) for row in combinations)
    occupied = {int(value) for value in occupied_table_ids}
    tables_by_id = {int(row["id"]): row for row in table_rows}

    base = reservation_rules.evaluate_reservation_rules(
        db,
        _rule_request(request, room_id=None),
        now=now,
    )
    if base.decision == "deny":
        reasons = _violation_reasons(base)
        first = base.violations[0] if base.violations else None
        return AllocationResult(
            request=request,
            evaluation=base,
            decision="deny",
            reasons=reasons,
            code=first.code if first else "RESERVATION_RULE_DENIED",
            rule=first.rule if first else "rules",
            message=first.message if first else "Reguły nie pozwalają na rezerwację.",
        )

    preferences = {}
    if request.preferred_zone:
        preferences["strefa"] = request.preferred_zone
    if request.preferred_features:
        preferences["cechy"] = list(request.preferred_features)
    preferences = preferences or None
    potential = seating.dopasuj(
        request.liczba_osob,
        table_rows,
        combination_rows,
        zajete=(),
        preferencje=preferences,
        limit=0,
        sasiedztwo=tuple(adjacency),
        obciazenie_sekcji=section_load,
        respect_room_fill=False,
    )
    potential = [
        raw for raw in potential
        if _candidate_is_within_one_room(raw, tables_by_id)
    ]
    free = seating.dopasuj(
        request.liczba_osob,
        table_rows,
        combination_rows,
        zajete=occupied,
        preferencje=preferences,
        limit=0,
        sasiedztwo=tuple(adjacency),
        obciazenie_sekcji=section_load,
        respect_room_fill=False,
    )
    free = [
        raw for raw in free
        if _candidate_is_within_one_room(raw, tables_by_id)
    ]
    if not free:
        return _no_resource_result(
            request,
            base,
            potential=potential,
            occupied=occupied,
        )

    evaluated: list[_EvaluatedCandidate] = []
    denied: list[_EvaluatedCandidate] = []
    for rank, raw in enumerate(free):
        room_id = raw.get("sala_id")
        evaluation = (
            base
            if room_id is None
            else reservation_rules.evaluate_reservation_rules(
                db,
                _rule_request(request, room_id=int(room_id)),
                now=now,
            )
        )
        candidate = _wrap_candidate(
            raw,
            tables_by_id=tables_by_id,
            evaluation=evaluation,
            request=request,
        )
        wrapped = _EvaluatedCandidate(candidate, evaluation, raw, rank)
        if evaluation.decision == "deny":
            denied.append(wrapped)
        else:
            evaluated.append(wrapped)

    allowed = _ordered(
        [row for row in evaluated if row.evaluation.decision == "allow"],
        preferred_room_id=request.preferred_room_id,
    )
    needs_override = _ordered(
        [
            row for row in evaluated
            if row.evaluation.decision == "override_required"
        ],
        preferred_room_id=request.preferred_room_id,
    )
    if allowed:
        ordered = [*allowed, *needs_override]
    elif needs_override:
        ordered = needs_override
    elif denied:
        chosen_denial = _ordered(
            denied,
            preferred_room_id=request.preferred_room_id,
        )[0]
        evaluation = chosen_denial.evaluation
        first = evaluation.violations[0] if evaluation.violations else None
        return AllocationResult(
            request=request,
            evaluation=evaluation,
            decision="deny",
            reasons=_violation_reasons(evaluation),
            code=first.code if first else "RESERVATION_RULE_DENIED",
            rule=first.rule if first else "rules",
            message=first.message if first else "Reguły sali blokują przydział.",
        )
    else:
        return _no_resource_result(
            request,
            base,
            potential=potential,
            occupied=occupied,
        )

    selected_row = ordered[0]
    alternatives = tuple(
        row.candidate for row in ordered[1:1 + alternative_limit]
    )
    candidates = (selected_row.candidate, *alternatives)
    evaluation = selected_row.evaluation
    first = evaluation.violations[0] if evaluation.violations else None
    return AllocationResult(
        request=request,
        evaluation=evaluation,
        decision=evaluation.decision,
        selected=selected_row.candidate,
        candidates=candidates,
        alternatives=alternatives,
        reasons=selected_row.candidate.reasons,
        code=first.code if first else None,
        rule=first.rule if first else None,
        message=first.message if first else None,
    )


__all__ = [
    "AllocationCandidate",
    "AllocationReason",
    "AllocationRequest",
    "AllocationResult",
    "evaluate_allocation",
]
