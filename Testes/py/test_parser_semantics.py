"""Testes de parsing e análise semântica."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compilador.parser import FortranParser, ParseError
from compilador.semantics import SemanticAnalyzer, SemanticError


class ParserSemanticsTests(unittest.TestCase):
    """Garante que gramática e regras semânticas-base estão estáveis."""

    def test_parse_programa_minimo(self) -> None:
        source = "PROGRAM MIN\nEND\n"
        ast = FortranParser().parse(source)
        self.assertEqual(ast.name, "MIN")
        self.assertEqual(ast.declarations, [])
        self.assertEqual(ast.statements, [])

    def test_parse_error_programa_sem_end(self) -> None:
        source = "PROGRAM M\nINTEGER A\n"
        with self.assertRaises(ParseError):
            FortranParser().parse(source)

    def test_semantica_deteta_variavel_nao_declarada(self) -> None:
        source = "PROGRAM P\nA = 2\nEND\n"
        ast = FortranParser().parse(source)
        with self.assertRaises(SemanticError) as ctx:
            SemanticAnalyzer().analyze(ast)
        self.assertIn("não declarada", str(ctx.exception))

    def test_semantica_deteta_label_goto_nao_definida(self) -> None:
        source = "PROGRAM P\nGOTO 99\nEND\n"
        ast = FortranParser().parse(source)
        with self.assertRaises(SemanticError) as ctx:
            SemanticAnalyzer().analyze(ast)
        self.assertIn("label 99 referenciada mas não definida", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
