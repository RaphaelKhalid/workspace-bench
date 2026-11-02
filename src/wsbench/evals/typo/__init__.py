"""Typo: a single-token basic family on the shared bank judge. Superseded by ``typo_mt`` (Camila
2026-10-30: "drop this from the macro, we don't need it, just keep the hard version"): out of
the macro and out of every ``all`` default, still runnable by name."""

import dataclasses

from wsbench.basic.family import bank_family
from wsbench.registry import register

SPEC = register(dataclasses.replace(bank_family("typo", "Typo"), superseded_by="typo_mt"))
