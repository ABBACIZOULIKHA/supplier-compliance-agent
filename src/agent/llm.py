"""The only module that talks to the LLM (Ollama). Swap the provider here and nothing else changes."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from .config import settings
from .prompts import EXTRACT_SYSTEM, SUMMARY_SYSTEM
from .schemas import ContractTerms, Issue

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: ollama.Client | None = None


class LLMError(RuntimeError):
    pass


def client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(host=settings.ollama_host)
    return _client


def chat(messages: list[Any], tools: list[dict] | None = None, schema: dict | None = None,
         temperature: float = 0.0):
    """One call to the model. `schema` forces JSON output matching a JSON schema."""
    kwargs: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "options": {"temperature": temperature},
    }
    if tools:
        kwargs["tools"] = tools
    if schema:
        kwargs["format"] = schema
    try:
        return client().chat(think=settings.ollama_think, **kwargs)
    except ollama.ResponseError as e:
        if "think" in str(e).lower():  # model without thinking support
            return client().chat(**kwargs)
        raise
    except ConnectionError as e:
        raise LLMError(f"Cannot reach Ollama at {settings.ollama_host}. Is `ollama serve` running?") from e


def _clean(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def structured(messages: list[dict], model_cls: type[T], retries: int = 3) -> T:
    """Ask for JSON matching `model_cls`; on invalid output, feed the error back and retry."""
    messages = list(messages)
    last_error = ""
    for attempt in range(1, retries + 1):
        resp = chat(messages, schema=model_cls.model_json_schema())
        content = _clean(resp.message.content)
        try:
            return model_cls.model_validate_json(content)
        except ValidationError as e:
            last_error = str(e)
            log.warning("Invalid LLM JSON (attempt %s/%s): %s", attempt, retries, last_error)
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That JSON was invalid: {last_error}\nReturn corrected JSON only."},
            ]
    raise LLMError(f"No valid {model_cls.__name__} after {retries} attempts: {last_error}")


def extract_contract_terms(contract_text: str) -> ContractTerms:
    return structured(
        [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": f"Contract text:\n\"\"\"\n{contract_text}\n\"\"\""},
        ],
        ContractTerms,
    )


# ------------------------------------------------------------------ summary
def deterministic_summary(supplier_name: str, period: str, issues: list[Issue], risk: str) -> str:
    """Template summary: used when the LLM is unavailable or invents numbers."""
    if not issues:
        return f"{supplier_name}, {period}: all payments comply with the contract. Risk level: {risk}."
    kinds: dict[str, int] = {}
    for i in issues:
        kinds[i.type] = kinds.get(i.type, 0) + 1
    listing = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(kinds.items()))
    top = " ".join(i.description for i in issues if i.severity != "low")[:600]
    return f"{supplier_name}, {period}: {len(issues)} issue(s) found ({listing}). {top} Risk level: {risk}."


def _numbers(text: str) -> set[float]:
    return {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text) if n.strip(",.")}


def write_summary(supplier_name: str, period: str, issues: list[Issue], risk: str) -> str:
    """LLM writes the prose from already-computed facts. Falls back to a template if the text
    contains any number that is not in the facts (hallucination guard)."""
    facts = json.dumps(
        {"supplier": supplier_name, "period": period, "risk_level": risk,
         "issues": [i.model_dump(exclude_none=True) for i in issues]}, indent=1)
    try:
        resp = chat(
            [{"role": "system", "content": SUMMARY_SYSTEM},
             {"role": "user", "content": f"Facts:\n{facts}\n\nWrite the summary."}],
            temperature=0.2,
        )
        text = _clean(resp.message.content)
    except Exception as e:  # noqa: BLE001
        log.warning("Summary LLM call failed (%s) -> template summary", e)
        return deterministic_summary(supplier_name, period, issues, risk)
    invented = _numbers(text) - _numbers(facts)
    if not text or invented:
        log.warning("Summary rejected (empty or unknown numbers %s) -> template summary", sorted(invented))
        return deterministic_summary(supplier_name, period, issues, risk)
    return text
