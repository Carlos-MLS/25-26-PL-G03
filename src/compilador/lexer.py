"""Analisador léxico para o subset de Fortran 77 (formato free-form).
transforma texto em tokens estruturados que o parser consegue consumir de forma determinística.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator

import ply.lex as lex


@dataclass(slots=True)
class LexicalError(Exception):
    """Erro léxico com posição exata no código fonte."""

    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"Erro léxico (linha {self.line}, coluna {self.column}): {self.message}"


class FortranLexer:
    """Mantém tabelas de keywords e operadores Fortran e expõe uma interface
    simples (`input` + iteração em `token`) usada pelo parser e pela CLI.
    """

    # Keywords suportadas no subset atual. Esta tabela existe para
    # converter identificadores reservados no token correto.
    reserved = {
        "PROGRAM": "PROGRAM",
        "END": "END",
        "INTEGER": "INTEGER",
        "REAL": "REAL",
        "LOGICAL": "LOGICAL",
        "IF": "IF",
        "THEN": "THEN",
        "ELSE": "ELSE",
        "ENDIF": "ENDIF",
        "DO": "DO",
        "CONTINUE": "CONTINUE",
        "GOTO": "GOTO",
        "READ": "READ",
        "PRINT": "PRINT",
        "FUNCTION": "FUNCTION",
        "SUBROUTINE": "SUBROUTINE",
        "RETURN": "RETURN",
        "CALL": "CALL",
    }

    # Operadores e literais lógicos escritos com notação .OP.
    dot_operators = {
        ".EQ.": "EQ",
        ".NE.": "NE",
        ".LT.": "LT",
        ".LE.": "LE",
        ".GT.": "GT",
        ".GE.": "GE",
        ".AND.": "AND",
        ".OR.": "OR",
        ".NOT.": "NOT",
        ".TRUE.": "BOOL_LITERAL",
        ".FALSE.": "BOOL_LITERAL",
    }

    # Lista final de tokens exposta ao parser.
    # Junta tokens "simples" com os tokens derivados das tabelas acima.
    tokens = [
        "IDENTIFIER",
        "INTEGER_LITERAL",
        "REAL_LITERAL",
        "STRING_LITERAL",
        "LABEL",
        "POWER",
        "PLUS",
        "MINUS",
        "TIMES",
        "DIVIDE",
        "ASSIGN",
        "COMMA",
        "LPAREN",
        "RPAREN",
        "COLON",
        "NEWLINE",
    ] + sorted(set(reserved.values()) | set(dot_operators.values()))

    t_PLUS = r"\+"
    t_MINUS = r"-"
    t_TIMES = r"\*"
    t_DIVIDE = r"/"
    t_ASSIGN = r"="
    t_COMMA = r","
    t_LPAREN = r"\("
    t_RPAREN = r"\)"
    t_COLON = r":"

    t_ignore = " \t\r"

    def __init__(self) -> None:
        """Constrói o autómato léxico.

        `re.MULTILINE` é necessário para que regras ancoradas com `^`
        (nomeadamente labels) funcionem no início de cada linha.
        """
        self.lexer = lex.lex(module=self, reflags=re.MULTILINE)
        self._source = ""

    def input(self, source: str) -> None:
        """Carrega um novo texto de entrada para tokenização."""
        self._source = source
        self.lexer.lineno = 1
        self.lexer.input(source)

    def token(self):
        """Obtém o próximo token (ou `None` no fim da entrada)."""
        return self.lexer.token()

    def __iter__(self) -> Iterator:
        """Permite percorrer tokens com `for tok in lexer`."""
        while True:
            tok = self.token()
            if tok is None:
                break
            yield tok

    @staticmethod
    def _find_column(source: str, lexpos: int) -> int:
        """Converte `lexpos` absoluto em coluna"""
        line_start = source.rfind("\n", 0, lexpos) + 1
        return (lexpos - line_start) + 1

    # Reconhece labels numéricos no início da linha.
    def t_LABEL(self, t):
        r"^[0-9]{1,5}(?=\s+[A-Za-z])"
        t.value = int(t.value)
        return t

    # Operador de potência `**`.
    def t_POWER(self, t):
        r"\*\*"
        return t

    # Literais reais, com ou sem expoente.
    def t_REAL_LITERAL(self, t):
        r"((\d+\.\d*|\.\d+)([Ee][+-]?\d+)?|\d+[Ee][+-]?\d+)"
        t.value = float(t.value)
        return t

    # Literais inteiros decimais.
    def t_INTEGER_LITERAL(self, t):
        r"\d+"
        t.value = int(t.value)
        return t

    # Strings delimitadas por aspas simples (com escape '' -> ').
    def t_STRING_LITERAL(self, t):
        r"'([^'\n]|'')*'"
        t.value = t.value[1:-1].replace("''", "'")
        return t

    # Resolve tokens da forma `.X.` para operadores/lógicos válidos.
    def t_DOT_TOKEN(self, t):
        r"\.[A-Za-z]+\."
        upper = t.value.upper()
        token_type = self.dot_operators.get(upper)
        if token_type is None:
            col = self._find_column(self._source, t.lexpos)
            raise LexicalError(f"operador lógico/relacional desconhecido: {t.value}", t.lineno, col)
        t.type = token_type
        if token_type == "BOOL_LITERAL":
            t.value = upper == ".TRUE."
        else:
            t.value = upper
        return t

    # Reconhece identificadores e promove keywords reservadas.
    def t_IDENTIFIER(self, t):
        r"[A-Za-z][A-Za-z0-9_]*"
        upper = t.value.upper()
        t.type = self.reserved.get(upper, "IDENTIFIER")
        # Fortran é case-insensitive; normalizamos para maiúsculas para
        # simplificar parser, semântica e comparação de símbolos.
        t.value = upper
        return t

    # Ignora comentários a partir de `!` até ao fim da linha.
    def t_COMMENT(self, t):
        r"![^\n]*"
        pass

    # Tokeniza quebras de linha e atualiza contador de linhas.
    def t_NEWLINE(self, t):
        r"\n+"
        t.lexer.lineno += len(t.value)
        return t

    def t_error(self, t):
        """Produz erro léxico com coluna calculada a partir do `lexpos`."""
        col = self._find_column(self._source, t.lexpos)
        raise LexicalError(f"carácter ilegal: {t.value[0]!r}", t.lineno, col)


def tokenize(source: str):
    """Função utilitária para tokenizar texto num único passo."""
    lexer = FortranLexer()
    lexer.input(source)
    return list(lexer)
