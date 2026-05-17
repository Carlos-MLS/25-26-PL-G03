"""Análise semântica para o subset de Fortran 77 do projeto.

O objetivo desta fase é validar coerência do programa depois do parsing:
declarações, tipos, regras de controlo de fluxo e chamadas de função.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast import (
    Assignment,
    BinaryOp,
    CallExpression,
    ContinueStatement,
    Declaration,
    DoStatement,
    Expression,
    FunctionDef,
    GotoStatement,
    IfStatement,
    IndexedRef,
    Literal,
    PrintStatement,
    Program,
    ReadStatement,
    ReturnStatement,
    Statement,
    UnaryOp,
    VariableRef,
)

NUMERIC_TYPES = {"INTEGER", "REAL"}
RELATIONAL_OPS = {".EQ.", ".NE.", ".LT.", ".LE.", ".GT.", ".GE."}
ARITHMETIC_OPS = {"+", "-", "*", "/", "**"}
LOGICAL_OPS = {".AND.", ".OR."}


@dataclass(slots=True)
class SemanticIssue:
    """Registo de um problema semântico com posição opcional."""

    message: str
    line: int | None
    column: int | None

    def format(self) -> str:
        if self.line is None:
            return self.message
        if self.column is None:
            return f"linha {self.line}: {self.message}"
        return f"linha {self.line}, coluna {self.column}: {self.message}"


@dataclass(slots=True)
class SemanticError(Exception):
    """Exceção agregadora usada para devolver vários erros de uma vez."""

    issues: list[SemanticIssue]

    def __str__(self) -> str:
        header = f"Foram encontrados {len(self.issues)} erro(s) semânticos:"
        details = "\n".join(f"- {issue.format()}" for issue in self.issues)
        return f"{header}\n{details}"


@dataclass(slots=True)
class SymbolInfo:
    """Entrada da tabela de símbolos de um escopo."""

    name: str
    type_name: str
    array_size: int | None
    line: int | None
    kind: str = "VAR"  # VAR | PARAM | RETURN
    declared_by_decl: bool = True


@dataclass(slots=True)
class FunctionSignature:
    """Assinatura estática de função (nome, retorno e parâmetros)."""

    name: str
    return_type: str
    param_names: list[str]
    param_types: list[str]


class SemanticAnalyzer:
    """Analisador semântico principal.

    Estratégia geral:
    1) recolher assinaturas de funções;
    2) validar programa principal;
    3) validar cada função no seu escopo próprio;
    4) acumular erros e reportar no fim.
    """

    def __init__(self) -> None:
        self.issues: list[SemanticIssue] = []
        self._issue_keys: set[tuple[str, int | None, int | None]] = set()
        self.function_signatures: dict[str, FunctionSignature] = {}
        self.symbols: dict[str, SymbolInfo] = {}

        self._symbols: dict[str, SymbolInfo] = {}
        self._defined_labels: set[int] = set()
        self._referenced_labels: list[tuple[int, int | None, int | None]] = []
        self._current_function: str | None = None

    def analyze(self, ast: Program) -> Program:
        """Valida semanticamente um programa completo.

        Retorna:
        - a AST original, se não houver problemas.

        Lança:
        - `SemanticError` quando existir pelo menos um erro semântico.
        """
        self.issues.clear()
        self._issue_keys.clear()
        self.function_signatures.clear()

        # Primeiro recolhemos assinaturas para permitir validação de
        # chamadas mesmo quando a definição aparece mais tarde.
        self._collect_function_signatures(ast)

        # Escopo do programa principal.
        self._analyze_scope(
            declarations=ast.declarations,
            statements=ast.statements,
            initial_symbols={},
            current_function=None,
        )
        self.symbols = dict(self._symbols)

        # Escopos de funções (cada uma com símbolos próprios).
        for function in ast.functions:
            function_symbols = self._build_function_initial_symbols(function)
            self._analyze_scope(
                declarations=function.declarations,
                statements=function.statements,
                initial_symbols=function_symbols,
                current_function=function.name,
            )
            if not any(isinstance(stmt, ReturnStatement) for stmt in function.statements):
                self._add_issue(
                    f"função '{function.name}' não tem RETURN",
                    function.line,
                    function.column,
                )

        if self.issues:
            raise SemanticError(self.issues)
        return ast

    def _collect_function_signatures(self, program: Program) -> None:
        """Extrai assinaturas de funções e valida tipagem de parâmetros."""
        for function in program.functions:
            name = function.name
            if name in self.function_signatures:
                self._add_issue(
                    f"função '{name}' declarada mais do que uma vez",
                    function.line,
                    function.column,
                )
                continue

            # Mapa auxiliar para cruzar parâmetros formais com declarações
            # de tipo existentes no corpo da função.
            param_type_by_name: dict[str, str] = {}
            for declaration in function.declarations:
                for var in declaration.variables:
                    if var.name in function.parameters and var.array_size is None:
                        if var.name in param_type_by_name:
                            self._add_issue(
                                f"parâmetro '{var.name}' da função '{name}' declarado mais do que uma vez",
                                var.line,
                                var.column,
                            )
                        else:
                            param_type_by_name[var.name] = declaration.type_name

            param_types: list[str] = []
            for param_name in function.parameters:
                ptype = param_type_by_name.get(param_name)
                if ptype is None:
                    self._add_issue(
                        f"parâmetro '{param_name}' da função '{name}' não foi declarado com tipo",
                        function.line,
                        function.column,
                    )
                    ptype = "INTEGER"
                param_types.append(ptype)

            self.function_signatures[name] = FunctionSignature(
                name=name,
                return_type=function.return_type,
                param_names=list(function.parameters),
                param_types=param_types,
            )

    def _build_function_initial_symbols(self, function: FunctionDef) -> dict[str, SymbolInfo]:
        """Cria tabela base do escopo de função (retorno + parâmetros)."""
        symbols: dict[str, SymbolInfo] = {
            function.name: SymbolInfo(
                name=function.name,
                type_name=function.return_type,
                array_size=None,
                line=function.line,
                kind="RETURN",
            )
        }

        signature = self.function_signatures.get(function.name)
        if signature is None:
            return symbols

        for pname, ptype in zip(signature.param_names, signature.param_types):
            symbols[pname] = SymbolInfo(
                name=pname,
                type_name=ptype,
                array_size=None,
                line=function.line,
                kind="PARAM",
                declared_by_decl=False,
            )
        return symbols

    def _analyze_scope(
        self,
        declarations: list[Declaration],
        statements: list[Statement],
        initial_symbols: dict[str, SymbolInfo],
        current_function: str | None,
    ) -> None:
        """Analisa um escopo isolado (programa principal ou função)."""
        self._symbols = dict(initial_symbols)
        self._defined_labels = set()
        self._referenced_labels = []
        self._current_function = current_function

        # As declarações entram primeiro para disponibilizar símbolos
        # antes da validação das instruções.
        for declaration in declarations:
            self._register_declaration(declaration)

        for statement in statements:
            self._visit_statement(statement)

        self._check_referenced_labels()

        for symbol in self._symbols.values():
            if symbol.kind == "PARAM" and not symbol.declared_by_decl:
                self._add_issue(
                    f"parâmetro '{symbol.name}' não foi declarado no bloco de declarações",
                    symbol.line,
                    None,
                )

    def _register_declaration(self, declaration: Declaration) -> None:
        """Regista declarações de variáveis e verifica conflitos locais."""
        decl_type = declaration.type_name
        for var in declaration.variables:
            existing = self._symbols.get(var.name)

            if existing is not None:
                if existing.kind == "PARAM":
                    if var.array_size is not None:
                        self._add_issue(
                            f"parâmetro '{var.name}' não pode ser declarado como array",
                            var.line,
                            var.column,
                        )
                    elif existing.type_name != decl_type:
                        self._add_issue(
                            f"tipo do parâmetro '{var.name}' incompatível com assinatura da função",
                            var.line,
                            var.column,
                        )
                    elif existing.declared_by_decl:
                        self._add_issue(
                            f"parâmetro '{var.name}' declarado mais do que uma vez",
                            var.line,
                            var.column,
                        )
                    else:
                        existing.declared_by_decl = True
                    continue

                self._add_issue(
                    f"variável '{var.name}' já declarada (declaração anterior na linha {existing.line})",
                    var.line,
                    var.column,
                )
                continue

            if var.array_size is not None and var.array_size <= 0:
                self._add_issue(
                    f"dimensão inválida para array '{var.name}': {var.array_size}",
                    var.line,
                    var.column,
                )

            self._symbols[var.name] = SymbolInfo(
                name=var.name,
                type_name=decl_type,
                array_size=var.array_size,
                line=var.line,
            )

    def _visit_statement(self, statement: Statement) -> None:
        """Despacha validação de statements por tipo concreto."""
        if statement.label is not None:
            self._defined_labels.add(statement.label)

        if isinstance(statement, Assignment):
            self._check_assignment(statement)
            return

        if isinstance(statement, IfStatement):
            self._check_if(statement)
            return

        if isinstance(statement, DoStatement):
            self._check_do(statement)
            return

        if isinstance(statement, GotoStatement):
            self._referenced_labels.append((statement.target_label, statement.line, statement.column))
            return

        if isinstance(statement, ContinueStatement):
            return

        if isinstance(statement, ReturnStatement):
            if self._current_function is None:
                self._add_issue("RETURN fora de uma função", statement.line, statement.column)
            return

        if isinstance(statement, ReadStatement):
            self._check_read(statement)
            return

        if isinstance(statement, PrintStatement):
            for expr in statement.items:
                self._infer_expr_type(expr)
            return

        self._add_issue("statement não suportado na análise semântica", statement.line, statement.column)

    def _check_assignment(self, statement: Assignment) -> None:
        """Valida atribuições (destino + expressão + compatibilidade)."""
        target_type = self._infer_target_type(statement.target, assignment_context=True)
        value_type = self._infer_expr_type(statement.value)

        if target_type is None or value_type is None:
            return

        if not self._is_assignment_compatible(target_type, value_type):
            self._add_issue(
                f"atribuição incompatível: não é possível atribuir {value_type} a {target_type}",
                statement.line,
                statement.column,
            )

    def _check_if(self, statement: IfStatement) -> None:
        """Valida condição do IF e visita ramos then/else."""
        cond_type = self._infer_expr_type(statement.condition)
        if cond_type is not None and cond_type != "LOGICAL":
            self._add_issue("condição de IF deve ser do tipo LOGICAL", statement.line, statement.column)

        for stmt in statement.then_body:
            self._visit_statement(stmt)
        for stmt in statement.else_body:
            self._visit_statement(stmt)

    def _check_do(self, statement: DoStatement) -> None:
        """Valida regras semânticas específicas de ciclos DO."""
        if statement.end_label <= 0:
            self._add_issue("label de fecho do DO deve ser positiva", statement.line, statement.column)

        if statement.continue_label is None:
            self._add_issue(
                "ciclo DO sem CONTINUE final com label; esperado '<label> CONTINUE'",
                statement.line,
                statement.column,
            )
        elif statement.continue_label != statement.end_label:
            self._add_issue(
                f"label do DO ({statement.end_label}) não coincide com label do CONTINUE ({statement.continue_label})",
                statement.line,
                statement.column,
            )

        # Iterador tem de existir, ser INTEGER e não ser array.
        sym = self._symbols.get(statement.iterator)
        if sym is None:
            self._add_issue(
                f"iterador do DO '{statement.iterator}' não foi declarado",
                statement.line,
                statement.column,
            )
        else:
            if sym.type_name != "INTEGER":
                self._add_issue(
                    f"iterador do DO '{statement.iterator}' deve ser INTEGER",
                    statement.line,
                    statement.column,
                )
            if sym.array_size is not None:
                self._add_issue(
                    f"iterador do DO '{statement.iterator}' não pode ser array",
                    statement.line,
                    statement.column,
                )

        # Os limites/passo precisam de ser numéricos para o codegen gerar
        # comparações e incrementos coerentes.
        self._expect_numeric(statement.start, "expressão inicial do DO", statement.line, statement.column)
        self._expect_numeric(statement.end, "expressão final do DO", statement.line, statement.column)
        if statement.step is not None:
            self._expect_numeric(statement.step, "passo do DO", statement.line, statement.column)

        for stmt in statement.body:
            self._visit_statement(stmt)

    def _check_read(self, statement: ReadStatement) -> None:
        """Valida lista de destinos da instrução READ."""
        if not statement.items:
            self._add_issue("READ sem variáveis de destino", statement.line, statement.column)
            return

        for item in statement.items:
            self._infer_target_type(item, assignment_context=True)

    def _infer_target_type(
        self, target: VariableRef | IndexedRef | None, assignment_context: bool = False
    ) -> str | None:
        """Infere tipo de um destino de escrita/leitura.

        `assignment_context=True` ativa restrições adicionais de escrita.
        """
        if target is None:
            return None

        if isinstance(target, VariableRef):
            sym = self._symbols.get(target.name)
            if sym is None:
                self._add_issue(f"variável '{target.name}' não declarada", target.line, target.column)
                return None
            if sym.array_size is not None:
                self._add_issue(
                    f"array '{target.name}' exige índice (use {target.name}(i))",
                    target.line,
                    target.column,
                )
                return None
            if assignment_context and sym.kind == "PARAM":
                self._add_issue(
                    f"não é permitido atribuir/ler para parâmetro '{target.name}'",
                    target.line,
                    target.column,
                )
                return None
            return sym.type_name

        if isinstance(target, IndexedRef):
            sym = self._symbols.get(target.name)
            if sym is None:
                self._add_issue(f"variável '{target.name}' não declarada", target.line, target.column)
                return None
            if sym.array_size is None:
                self._add_issue(
                    f"variável '{target.name}' não é array e não pode ser indexada",
                    target.line,
                    target.column,
                )
                return None
            if assignment_context and sym.kind == "PARAM":
                self._add_issue(
                    f"não é permitido atribuir/ler para parâmetro '{target.name}'",
                    target.line,
                    target.column,
                )
                return None

            idx_type = self._infer_expr_type(target.index)
            if idx_type is not None and idx_type != "INTEGER":
                self._add_issue(
                    f"índice de '{target.name}' deve ser INTEGER (recebido: {idx_type})",
                    target.line,
                    target.column,
                )
            return sym.type_name

        self._add_issue("alvo de atribuição/leitura inválido", target.line, target.column)
        return None

    def _infer_expr_type(self, expr: Expression | None) -> str | None:
        """Infere o tipo de uma expressão e anota-o no próprio nó.

        Esta é a única inferência de tipos do compilador. O resultado fica
        guardado em `expr.result_type`, para que as fases seguintes (em
        especial a geração de código) leiam esse campo em vez de repetir a
        inferência — evitando lógica duplicada e divergências entre fases.
        """
        result = self._compute_expr_type(expr)
        if expr is not None:
            expr.result_type = result
        return result

    def _compute_expr_type(self, expr: Expression | None) -> str | None:
        """Calcula o tipo estático de uma expressão e regista incompatibilidades."""
        if expr is None:
            return None

        if isinstance(expr, Literal):
            return expr.literal_type

        if isinstance(expr, VariableRef):
            sym = self._symbols.get(expr.name)
            if sym is None:
                self._add_issue(f"variável '{expr.name}' não declarada", expr.line, expr.column)
                return None
            if sym.array_size is not None:
                self._add_issue(
                    f"array '{expr.name}' exige índice (use {expr.name}(i))",
                    expr.line,
                    expr.column,
                )
                return None
            return sym.type_name

        if isinstance(expr, IndexedRef):
            sym = self._symbols.get(expr.name)
            if sym is None:
                self._add_issue(f"variável '{expr.name}' não declarada", expr.line, expr.column)
                return None
            if sym.array_size is None:
                self._add_issue(
                    f"variável '{expr.name}' não é array e não pode ser indexada",
                    expr.line,
                    expr.column,
                )
                return None

            idx_type = self._infer_expr_type(expr.index)
            if idx_type is not None and idx_type != "INTEGER":
                self._add_issue(
                    f"índice de '{expr.name}' deve ser INTEGER (recebido: {idx_type})",
                    expr.line,
                    expr.column,
                )
            return sym.type_name

        if isinstance(expr, CallExpression):
            return self._infer_call_type(expr)

        if isinstance(expr, UnaryOp):
            operand_type = self._infer_expr_type(expr.operand)
            if operand_type is None:
                return None

            if expr.op == "NEG":
                if operand_type not in NUMERIC_TYPES:
                    self._add_issue("negação numérica exige operando INTEGER ou REAL", expr.line, expr.column)
                    return None
                return operand_type

            if expr.op == ".NOT.":
                if operand_type != "LOGICAL":
                    self._add_issue("operador .NOT. exige operando LOGICAL", expr.line, expr.column)
                    return None
                return "LOGICAL"

            self._add_issue(f"operador unário desconhecido: {expr.op}", expr.line, expr.column)
            return None

        if isinstance(expr, BinaryOp):
            left_type = self._infer_expr_type(expr.left)
            right_type = self._infer_expr_type(expr.right)
            if left_type is None or right_type is None:
                return None

            op = expr.op
            # Operadores aritméticos: aceitam apenas tipos numéricos e
            # promovem para REAL quando necessário.
            if op in ARITHMETIC_OPS:
                if left_type not in NUMERIC_TYPES or right_type not in NUMERIC_TYPES:
                    self._add_issue(
                        f"operador '{op}' exige operandos numéricos (recebido: {left_type}, {right_type})",
                        expr.line,
                        expr.column,
                    )
                    return None
                if left_type == "REAL" or right_type == "REAL":
                    return "REAL"
                return "INTEGER"

            # Operadores lógicos: ambos os operandos devem ser LOGICAL.
            if op in LOGICAL_OPS:
                if left_type != "LOGICAL" or right_type != "LOGICAL":
                    self._add_issue(
                        f"operador '{op}' exige operandos LOGICAL (recebido: {left_type}, {right_type})",
                        expr.line,
                        expr.column,
                    )
                    return None
                return "LOGICAL"

            # Operadores relacionais: devolvem LOGICAL.
            if op in RELATIONAL_OPS:
                if op in {".LT.", ".LE.", ".GT.", ".GE."}:
                    if left_type not in NUMERIC_TYPES or right_type not in NUMERIC_TYPES:
                        self._add_issue(
                            f"operador '{op}' exige operandos numéricos",
                            expr.line,
                            expr.column,
                        )
                        return None
                else:
                    if left_type != right_type and not (
                        left_type in NUMERIC_TYPES and right_type in NUMERIC_TYPES
                    ):
                        self._add_issue(
                            f"comparação '{op}' incompatível entre {left_type} e {right_type}",
                            expr.line,
                            expr.column,
                        )
                        return None
                return "LOGICAL"

            self._add_issue(f"operador binário desconhecido: {op}", expr.line, expr.column)
            return None

        self._add_issue("expressão não suportada na análise semântica", expr.line, expr.column)
        return None

    def _infer_call_type(self, expr: CallExpression) -> str | None:
        """Valida chamada de função e devolve tipo de retorno esperado."""
        name = expr.name.upper()
        arg_types = [self._infer_expr_type(arg) for arg in expr.args]
        if any(t is None for t in arg_types):
            return None

        # `MOD` é tratado como builtin suportado diretamente.
        if name == "MOD":
            if len(expr.args) != 2:
                self._add_issue("MOD exige exatamente 2 argumentos", expr.line, expr.column)
                return None
            if any(t != "INTEGER" for t in arg_types):
                self._add_issue("MOD exige argumentos INTEGER", expr.line, expr.column)
                return None
            return "INTEGER"

        # Funções definidas pelo utilizador (assinatura recolhida antes).
        sig = self.function_signatures.get(name)
        if sig is not None:
            if self._current_function == name:
                self._add_issue(f"recursão não permitida para função '{name}'", expr.line, expr.column)
                return None
            if len(arg_types) != len(sig.param_types):
                self._add_issue(
                    f"função '{name}' espera {len(sig.param_types)} argumento(s), recebeu {len(arg_types)}",
                    expr.line,
                    expr.column,
                )
                return None
            for idx, (arg_t, param_t) in enumerate(zip(arg_types, sig.param_types), start=1):
                if arg_t != param_t:
                    self._add_issue(
                        f"argumento {idx} de '{name}' tem tipo {arg_t}, esperado {param_t}",
                        expr.line,
                        expr.column,
                    )
                    return None
            return sig.return_type

        # fallback: se o nome existir como símbolo local, pode tratar-se
        # de acesso indexado a array escrito como chamada.
        sym = self._symbols.get(name)
        if sym is not None:
            if sym.array_size is not None:
                if len(arg_types) != 1:
                    self._add_issue(
                        f"array '{name}' exige exatamente 1 índice",
                        expr.line,
                        expr.column,
                    )
                    return None
                if arg_types[0] != "INTEGER":
                    self._add_issue(
                        f"índice de '{name}' deve ser INTEGER (recebido: {arg_types[0]})",
                        expr.line,
                        expr.column,
                    )
                    return None
                return sym.type_name

            self._add_issue(
                f"'{name}' é escalar mas está a ser usado com argumentos",
                expr.line,
                expr.column,
            )
            return None

        self._add_issue(f"função '{name}' não declarada", expr.line, expr.column)
        return None

    @staticmethod
    def _is_assignment_compatible(target_type: str, value_type: str) -> bool:
        """Regra de compatibilidade de tipos em atribuição."""
        if target_type == value_type:
            return True
        if target_type == "REAL" and value_type == "INTEGER":
            return True
        return False

    def _expect_numeric(self, expr: Expression | None, ctx: str, line: int | None, column: int | None) -> None:
        """Ajuda para validar contexto que exige expressão numérica."""
        expr_type = self._infer_expr_type(expr)
        if expr_type is None:
            return
        if expr_type not in NUMERIC_TYPES:
            self._add_issue(f"{ctx} deve ser numérica (INTEGER/REAL)", line, column)

    def _check_referenced_labels(self) -> None:
        """Verifica se todas as labels referenciadas por GOTO existem."""
        for label, line, column in self._referenced_labels:
            if label not in self._defined_labels:
                self._add_issue(f"label {label} referenciada mas não definida", line, column)

    def _add_issue(self, message: str, line: int | None, column: int | None) -> None:
        """Adiciona erro semântico, evitando duplicação de mensagens."""
        key = (message, line, column)
        if key in self._issue_keys:
            return
        self._issue_keys.add(key)
        self.issues.append(SemanticIssue(message=message, line=line, column=column))
