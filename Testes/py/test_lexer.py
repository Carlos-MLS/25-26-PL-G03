"""Testes da fase léxica do compilador."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fortran77_compiler.lexer import FortranLexer, LexicalError, tokenize


class LexerTests(unittest.TestCase):
    """Valida cenários típicos e erros esperados do lexer."""

    def test_tokeniza_keywords_e_identificadores_case_insensitive(self) -> None:
        source = "program hello\ninteger n\nend\n"
        tokens = tokenize(source)
        token_types = [tok.type for tok in tokens]
        self.assertEqual(
            token_types,
            ["PROGRAM", "IDENTIFIER", "NEWLINE", "INTEGER", "IDENTIFIER", "NEWLINE", "END", "NEWLINE"],
        )
        self.assertEqual(tokens[1].value, "HELLO")
        self.assertEqual(tokens[4].value, "N")

    def test_reconhece_operadores_dot_e_literal_logico(self) -> None:
        source = "IF (.TRUE. .AND. .FALSE.) THEN\nENDIF\n"
        tokens = tokenize(source)
        values = [(tok.type, tok.value) for tok in tokens if tok.type not in {"NEWLINE", "LPAREN", "RPAREN"}]
        self.assertIn(("BOOL_LITERAL", True), values)
        self.assertIn(("AND", ".AND."), values)
        self.assertIn(("BOOL_LITERAL", False), values)

    def test_erro_lexico_em_caracter_ilegal(self) -> None:
        source = "PROGRAM P\n@\nEND\n"
        with self.assertRaises(LexicalError) as ctx:
            lexer = FortranLexer()
            lexer.input(source)
            list(lexer)
        self.assertIn("carácter ilegal", str(ctx.exception))
        self.assertEqual(ctx.exception.line, 2)


if __name__ == "__main__":
    unittest.main()
