"""Definições de AST (Abstract Syntax Tree) para o compilador.

Este módulo concentra as estruturas de dados partilhadas entre parser,
análise semântica e geração de código. A ideia é ter uma representação
intermédia clara do programa, independente dos detalhes do texto original.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Node:
    """Nó base com metadados de posição no código fonte.

    `line` e `column` permitem apresentar mensagens de erro mais úteis
    nas fases seguintes do compilador.
    """

    line: int | None = None
    column: int | None = None


@dataclass(slots=True)
class Statement(Node):
    """Nó base para instruções executáveis.

    `label` representa labels numéricos de Fortran (ex.: `10 CONTINUE`),
    usados sobretudo em `DO` e `GOTO`.
    """

    label: int | None = None


@dataclass(slots=True)
class Expression(Node):
    """Nó base para expressões avaliáveis.

    `result_type` é preenchido pela análise semântica com o tipo estático
    da expressão ("INTEGER", "REAL", "LOGICAL" ou "STRING"). As fases
    seguintes — em particular a geração de código — leem este campo em vez
    de reinferir tipos, mantendo uma única fonte de verdade.
    """

    result_type: str | None = None


@dataclass(slots=True)
class Program(Node):
    """Programa principal.

    `declarations` e `statements` guardam o corpo do `PROGRAM`.
    `functions` guarda definições de funções externas ao bloco principal.

    Nota sobre `default_factory=list`:
    cada instância precisa da sua própria lista. Usar `[]` diretamente
    criaria listas partilhadas entre instâncias, o que seria um erro.
    """

    name: str = ""
    declarations: list["Declaration"] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    functions: list["FunctionDef"] = field(default_factory=list)


@dataclass(slots=True)
class Declaration(Node):
    """Declaração de tipo Fortran com uma lista de variáveis."""

    type_name: str = ""
    variables: list["VariableDecl"] = field(default_factory=list)


@dataclass(slots=True)
class VariableDecl(Node):
    """Declaração de variável.

    `array_size` é `None` para escalar e inteiro positivo para array 1D.
    """

    name: str = ""
    array_size: int | None = None


@dataclass(slots=True)
class VariableRef(Expression):
    """Referência a variável escalar."""

    name: str = ""


@dataclass(slots=True)
class IndexedRef(Expression):
    """Referência indexada a array (`A(I)`)."""

    name: str = ""
    index: Expression | None = None


@dataclass(slots=True)
class Literal(Expression):
    """Literal constante (inteiro, real, lógico ou string)."""

    value: Any = None
    literal_type: str = ""


@dataclass(slots=True)
class UnaryOp(Expression):
    """Operação unária (negação numérica ou lógica)."""

    op: str = ""
    operand: Expression | None = None


@dataclass(slots=True)
class BinaryOp(Expression):
    """Operação binária aritmética, lógica ou relacional."""

    op: str = ""
    left: Expression | None = None
    right: Expression | None = None


@dataclass(slots=True)
class CallExpression(Expression):
    """Chamada de função em expressão."""

    name: str = ""
    args: list[Expression] = field(default_factory=list)


@dataclass(slots=True)
class Assignment(Statement):
    """Atribuição de expressão a variável/posição de array."""

    target: VariableRef | IndexedRef | None = None
    value: Expression | None = None


@dataclass(slots=True)
class IfStatement(Statement):
    """Estrutura condicional com ramo `then` e `else` opcional."""

    condition: Expression | None = None
    then_body: list[Statement] = field(default_factory=list)
    else_body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class DoStatement(Statement):
    """Representação de ciclo `DO` clássico com label de fecho."""

    end_label: int = 0
    iterator: str = ""
    start: Expression | None = None
    end: Expression | None = None
    step: Expression | None = None
    body: list[Statement] = field(default_factory=list)
    continue_label: int | None = None


@dataclass(slots=True)
class GotoStatement(Statement):
    """Salto incondicional para uma label."""

    target_label: int = 0


@dataclass(slots=True)
class ContinueStatement(Statement):
    """Instrução `CONTINUE` (frequentemente usada para fechar `DO`)."""

    pass


@dataclass(slots=True)
class ReturnStatement(Statement):
    """Instrução `RETURN` no contexto de função."""

    pass


@dataclass(slots=True)
class ReadStatement(Statement):
    """Leitura para uma ou mais variáveis/posições de array."""

    items: list[VariableRef | IndexedRef] = field(default_factory=list)


@dataclass(slots=True)
class PrintStatement(Statement):
    """Escrita de uma sequência de expressões."""

    items: list[Expression] = field(default_factory=list)


@dataclass(slots=True)
class FunctionDef(Node):
    """Definição de função com parâmetros, declarações e corpo."""

    name: str = ""
    return_type: str = ""
    parameters: list[str] = field(default_factory=list)
    declarations: list["Declaration"] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
