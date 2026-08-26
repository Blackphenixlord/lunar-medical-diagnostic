"""VITALS - spaceflight medical decision support.

Team TETHER, NASA HUNCH 2026-27, Software & Technology.
Joshua (lead / engine), Joaquin (medical research / rules), Cruz (interface / testing).

WHAT THIS IS
    A crewmember describes how they feel in plain English. VITALS returns a
    ranked differential: what it might be, why, what to do next, and a real
    citation for every rule it used.

    It is decision support. It is not a diagnosis, and it never pretends to be
    a flight surgeon.

HOW THE PIECES FIT TOGETHER
    Read the modules in this order and the whole system makes sense:

        models.py           the nouns - Condition, FindingDef, Evidence
        knowledge_base.py   loads and validates kb/ on disk
        patterns.py         the phrasebook: English -> finding ids
        extract.py          complaint text  -> observed findings
        retrieval.py        observed findings -> the KB pages worth reading
        ollama_client.py    the HTTP plumbing for the local model
        reason.py           the model reads those pages and answers   <- THE LLM
        scoring.py          the arithmetic behind the cross-check engine
        engine.py           the deterministic cross-check itself
        sensors.py          where hardware readings will plug in (nothing yet)
        render.py           everything that prints to a terminal
        cli.py              argument parsing and nothing else
        server.py           the same pipeline behind a browser

THE ONE RULE WE DO NOT BREAK
    Every answer must trace back to something a human can check. A flight
    surgeon will not act on a black box and a review panel will not pass one.
"""

__version__ = "0.4.0"          # renamed to VITALS; refactored for readability

from .knowledge_base import KnowledgeBase, KnowledgeBaseError, load_knowledge_base
from .engine import Result, ConditionScore, diagnose, next_best_questions
from .retrieval import retrieve
from . import sensors

__all__ = [
    "__version__",
    "KnowledgeBase",
    "KnowledgeBaseError",
    "load_knowledge_base",
    "Result",
    "ConditionScore",
    "diagnose",
    "next_best_questions",
    "retrieve",
    "sensors",
]
