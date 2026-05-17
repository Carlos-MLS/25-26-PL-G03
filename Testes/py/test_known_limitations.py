"""Testes de limitações conhecidas.

Estes testes existem para documentar aspetos ainda não suportados.
"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compilador.compiler import compile_source_to_vm


class KnownLimitationsTests(unittest.TestCase):
    """Casos que ainda não passam no compilador atual."""

    @unittest.expectedFailure
    def test_operador_power_ainda_nao_suportado_em_codegen(self) -> None:
        source = "PROGRAM P\nINTEGER A\nA = 2 ** 3\nPRINT *, A\nEND\n"
        # Atualmente este caso falha no codegen porque a EWVM usada 
        # não tem mapeamento implementado para '**'.
        compile_source_to_vm(source)


if __name__ == "__main__":
    unittest.main()
