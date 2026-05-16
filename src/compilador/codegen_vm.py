"""Geração de código para a sintaxe oficial da EWVM.

traduz a AST validada em instruções da máquina virtual.
O codegen assume que parsing e semântica já eliminaram casos inválidos,
mas mantém verificações defensivas para falhas de integração.
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


@dataclass(slots=True)
class CodegenError(Exception):
    """Erro de geração de código VM."""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class VarLayout:
    """Layout de uma variável em memória da VM.

    - `base`: offset relativo à área de armazenamento (global/frame).
    - `size`: número de slots ocupados.
    - `is_array`: distingue escalar de array.
    """

    type_name: str
    base: int
    size: int
    is_array: bool


@dataclass(slots=True)
class FunctionMeta:
    """Metainformação mínima de função usada em chamadas."""

    return_type: str
    param_types: list[str]


@dataclass(slots=True)
class FunctionScope:
    """Representa o frame de uma função durante codegen."""

    name: str
    vars: dict[str, VarLayout]
    local_slots: int


class VMCodeGenerator:
    """Gerador principal para EWVM.

    O fluxo é:
    1) construir layouts globais;
    2) recolher metadata de funções;
    3) emitir corpo principal;
    4) emitir corpos de funções.
    """

    def __init__(self) -> None:
        self.instructions: list[str] = []
        self._label_counter = 0

        self._global_layout: dict[str, VarLayout] = {}
        self._total_global_slots = 0

        self._function_meta: dict[str, FunctionMeta] = {}

        self._current_scope: FunctionScope | None = None

    def generate(self, ast: Program) -> list[str]:
        """Traduz AST completa e devolve lista de instruções VM."""
        self.instructions = []
        self._label_counter = 0
        self._global_layout = self._build_global_layout(ast.declarations)
        self._total_global_slots = sum(layout.size for layout in self._global_layout.values())
        self._build_function_metadata(ast.functions)

        # Reserva memória global numa só instrução para simplificar offsets.
        self._emit("START")
        if self._total_global_slots > 0:
            self._emit(f"PUSHN {self._total_global_slots}")

        # O corpo principal é emitido antes das funções.
        for statement in ast.statements:
            self._gen_statement(statement)

        self._emit("STOP")

        for function in ast.functions:
            self._gen_function(function)

        return self.instructions

    def _build_global_layout(self, declarations: list[Declaration]) -> dict[str, VarLayout]:
        """Calcula layout linear de variáveis globais."""
        layout: dict[str, VarLayout] = {}
        offset = 0
        for declaration in declarations:
            for var in declaration.variables:
                size = var.array_size if var.array_size is not None else 1
                layout[self._canon(var.name)] = VarLayout(
                    type_name=declaration.type_name,
                    base=offset,
                    size=size,
                    is_array=var.array_size is not None,
                )
                offset += size
        return layout

    def _build_function_metadata(self, functions: list[FunctionDef]) -> None:
        """Recolhe metadados de funções necessários para chamadas."""
        self._function_meta.clear()

        for function in functions:
            fname = self._canon(function.name)

            # Primeiro mapeamos nomes de parâmetros para tipos inferidos
            # a partir das declarações internas da função.
            param_type_map: dict[str, str] = {}
            for declaration in function.declarations:
                for var in declaration.variables:
                    vname = self._canon(var.name)
                    if vname in {self._canon(p) for p in function.parameters} and var.array_size is None:
                        if vname not in param_type_map:
                            param_type_map[vname] = declaration.type_name

            param_types: list[str] = []
            for pname in function.parameters:
                canon = self._canon(pname)
                param_types.append(param_type_map.get(canon, "INTEGER"))

            self._function_meta[fname] = FunctionMeta(
                return_type=function.return_type,
                param_types=param_types,
            )

    def _layout_function_scope(self, function: FunctionDef) -> FunctionScope:
        """Constrói o layout de frame local de uma função.

        Convenção adotada:
        - parâmetros em offsets negativos (relativos ao FP);
        - retorno/localidades em offsets não-negativos.
        """
        fname = self._canon(function.name)
        vars_layout: dict[str, VarLayout] = {}

        # Parâmetros posicionados na zona "abaixo" do frame pointer.
        num_params = len(function.parameters)
        for idx, param in enumerate(function.parameters):
            pname = self._canon(param)
            offset = -(num_params - idx)
            ptype = self._function_meta[fname].param_types[idx] if fname in self._function_meta else "INTEGER"
            vars_layout[pname] = VarLayout(
                type_name=ptype,
                base=offset,
                size=1,
                is_array=False,
            )

        # Reserva da célula que representa o valor de retorno da função.
        next_local = 0

        vars_layout[fname] = VarLayout(
            type_name=function.return_type,
            base=next_local,
            size=1,
            is_array=False,
        )
        next_local += 1

        # Depois alocamos variáveis locais declaradas na função.
        for declaration in function.declarations:
            for var in declaration.variables:
                vname = self._canon(var.name)
                if vname in vars_layout:
                    continue

                size = var.array_size if var.array_size is not None else 1
                vars_layout[vname] = VarLayout(
                    type_name=declaration.type_name,
                    base=next_local,
                    size=size,
                    is_array=var.array_size is not None,
                )
                next_local += size

        return FunctionScope(name=fname, vars=vars_layout, local_slots=next_local)

    def _gen_function(self, function: FunctionDef) -> None:
        """Emite o bloco de instruções de uma função."""
        scope = self._layout_function_scope(function)

        previous_scope = self._current_scope
        self._current_scope = scope

        self._emit_label(scope.name)
        if scope.local_slots > 0:
            self._emit(f"PUSHN {scope.local_slots}")

        for statement in function.statements:
            self._gen_statement(statement)

        self._current_scope = previous_scope

    def _gen_statement(self, statement: Statement) -> None:
        """Despacha geração conforme tipo de instrução."""
        if statement.label is not None:
            self._emit_label(f"U{statement.label}")

        if isinstance(statement, Assignment):
            self._gen_assignment(statement)
            return

        if isinstance(statement, IfStatement):
            self._gen_if(statement)
            return

        if isinstance(statement, DoStatement):
            self._gen_do(statement)
            return

        if isinstance(statement, GotoStatement):
            self._emit(f"JUMP U{statement.target_label}")
            return

        if isinstance(statement, ContinueStatement):
            self._emit("NOP")
            return

        if isinstance(statement, ReturnStatement):
            self._gen_return(statement)
            return

        if isinstance(statement, ReadStatement):
            self._gen_read(statement)
            return

        if isinstance(statement, PrintStatement):
            self._gen_print(statement)
            return

        raise CodegenError(f"statement não suportado no codegen: {type(statement).__name__}")

    def _gen_return(self, statement: ReturnStatement) -> None:
        """Emite retorno de função carregando variável de retorno."""
        if self._current_scope is None:
            raise CodegenError("RETURN fora de função")

        ret_layout = self._current_scope.vars.get(self._current_scope.name)
        if ret_layout is None:
            raise CodegenError(f"variável de retorno ausente para função '{self._current_scope.name}'")

        self._emit(f"PUSHL {ret_layout.base}")
        self._emit("RETURN")

    def _gen_assignment(self, statement: Assignment) -> None:
        """Emite atribuição a escalar ou posição de array."""
        if statement.target is None or statement.value is None:
            raise CodegenError("atribuição inválida (target/value ausente)")

        if isinstance(statement.target, VariableRef):
            layout, storage = self._resolve_var(statement.target.name)
            self._gen_expression(statement.value)
            self._emit_store(storage, layout.base)
            return

        if isinstance(statement.target, IndexedRef):
            layout, storage = self._resolve_var(statement.target.name)
            if not layout.is_array:
                raise CodegenError(f"variável '{statement.target.name}' não é array")
            self._emit_array_base_and_index(storage, layout, statement.target.index)
            self._gen_expression(statement.value)
            self._emit("STOREN")
            return

        raise CodegenError("alvo de atribuição não suportado")

    def _gen_if(self, statement: IfStatement) -> None:
        """Emite controlo de fluxo para IF/ELSE com labels temporárias."""
        else_lbl = self._fresh_label("L")
        end_lbl = self._fresh_label("L")

        self._gen_expression(statement.condition)
        self._emit(f"JZ {else_lbl}")

        for stmt in statement.then_body:
            self._gen_statement(stmt)

        self._emit(f"JUMP {end_lbl}")
        self._emit_label(else_lbl)

        for stmt in statement.else_body:
            self._gen_statement(stmt)

        self._emit_label(end_lbl)

    def _gen_do(self, statement: DoStatement) -> None:
        """Emite ciclo DO com suporte para passo positivo e negativo."""
        head_lbl = self._fresh_label("L")
        exit_lbl = self._fresh_label("L")
        neg_step_lbl = self._fresh_label("L")
        after_check_lbl = self._fresh_label("L")

        iter_layout, iter_storage = self._resolve_var(statement.iterator)

        self._gen_expression(statement.start)
        self._emit_store(iter_storage, iter_layout.base)

        self._emit_label(head_lbl)

        # Sem passo explícito assumimos +1 e condição crescente.
        if statement.step is None:
            self._emit_load(iter_storage, iter_layout.base)
            self._gen_expression(statement.end)
            self._emit("INFEQ")
            self._emit(f"JZ {exit_lbl}")
        else:
            # Com passo explícito, escolhemos comparação com base no sinal
            # do passo em tempo de execução (SUP vs SUPEQ/INFEQ).
            self._gen_expression(statement.step)
            self._emit("PUSHI 0")
            self._emit("SUP")
            self._emit(f"JZ {neg_step_lbl}")

            self._emit_load(iter_storage, iter_layout.base)
            self._gen_expression(statement.end)
            self._emit("INFEQ")
            self._emit(f"JZ {exit_lbl}")
            self._emit(f"JUMP {after_check_lbl}")

            self._emit_label(neg_step_lbl)
            self._emit_load(iter_storage, iter_layout.base)
            self._gen_expression(statement.end)
            self._emit("SUPEQ")
            self._emit(f"JZ {exit_lbl}")
            self._emit_label(after_check_lbl)

        for stmt in statement.body:
            self._gen_statement(stmt)

        self._emit_load(iter_storage, iter_layout.base)
        if statement.step is None:
            self._emit("PUSHI 1")
        else:
            self._gen_expression(statement.step)
        self._emit("ADD")
        self._emit_store(iter_storage, iter_layout.base)
        self._emit(f"JUMP {head_lbl}")
        self._emit_label(exit_lbl)

    def _gen_read(self, statement: ReadStatement) -> None:
        """Emite leitura para variáveis/arrays com conversão de tipo."""
        for item in statement.items:
            if isinstance(item, VariableRef):
                layout, storage = self._resolve_var(item.name)
                self._emit("READ")
                self._emit_read_conversion(layout.type_name)
                self._emit_store(storage, layout.base)
                continue

            if isinstance(item, IndexedRef):
                layout, storage = self._resolve_var(item.name)
                if not layout.is_array:
                    raise CodegenError(f"variável '{item.name}' não é array")
                self._emit_array_base_and_index(storage, layout, item.index)
                self._emit("READ")
                self._emit_read_conversion(layout.type_name)
                self._emit("STOREN")
                continue

            raise CodegenError("alvo de READ não suportado")

    def _emit_read_conversion(self, type_name: str) -> None:
        """Converte entrada textual para representação interna da VM."""
        if type_name == "REAL":
            self._emit("ATOF")
        else:
            self._emit("ATOI")

    def _gen_print(self, statement: PrintStatement) -> None:
        """Emite escrita tipada (`WRITEI`, `WRITEF`, `WRITES`)."""
        for expr in statement.items:
            expr_type = expr.result_type
            self._gen_expression(expr)
            if expr_type == "STRING":
                self._emit("WRITES")
            elif expr_type == "REAL":
                self._emit("WRITEF")
            else:
                self._emit("WRITEI")
        self._emit("WRITELN")

    def _gen_expression(self, expr: Expression | None) -> None:
        """Emite código para avaliar expressão e deixar resultado na stack."""
        if expr is None:
            raise CodegenError("expressão vazia no codegen")

        if isinstance(expr, Literal):
            if expr.literal_type == "INTEGER":
                self._emit(f"PUSHI {expr.value}")
            elif expr.literal_type == "REAL":
                self._emit(f"PUSHF {expr.value}")
            elif expr.literal_type == "LOGICAL":
                self._emit(f"PUSHI {1 if expr.value else 0}")
            elif expr.literal_type == "STRING":
                escaped = str(expr.value).replace('"', '\\"')
                self._emit(f'PUSHS "{escaped}"')
            else:
                raise CodegenError(f"literal desconhecido: {expr.literal_type}")
            return

        if isinstance(expr, VariableRef):
            layout, storage = self._resolve_var(expr.name)
            self._emit_load(storage, layout.base)
            return

        if isinstance(expr, IndexedRef):
            layout, storage = self._resolve_var(expr.name)
            if not layout.is_array:
                raise CodegenError(f"variável '{expr.name}' não é array")
            self._emit_array_base_and_index(storage, layout, expr.index)
            self._emit("LOADN")
            return

        if isinstance(expr, UnaryOp):
            # A EWVM não tem negação real direta, por isso multiplicamos
            # por -1.0 quando o operando for REAL.
            if expr.op == "NEG":
                if expr.operand is not None and expr.operand.result_type == "REAL":
                    self._emit("PUSHF -1.0")
                    self._gen_expression(expr.operand)
                    self._emit("FMUL")
                else:
                    self._emit("PUSHI -1")
                    self._gen_expression(expr.operand)
                    self._emit("MUL")
                return
            if expr.op == ".NOT.":
                self._gen_expression(expr.operand)
                self._emit("NOT")
                return
            raise CodegenError(f"operador unário não suportado: {expr.op}")

        if isinstance(expr, BinaryOp):
            self._gen_expression(expr.left)
            self._gen_expression(expr.right)
            # Para escolher entre opcode inteiro e real interessa o tipo dos
            # OPERANDOS, não o do resultado: uma comparação entre REAIS tem
            # resultado LOGICAL mas exige FINF/FSUP/etc.
            operand_type = self._operand_numeric_type(expr.left, expr.right)
            self._emit_binary_op(expr.op, operand_type)
            return

        if isinstance(expr, CallExpression):
            name = self._canon(expr.name)
            # `MOD` é tratado como builtin no codegen.
            if name == "MOD":
                if len(expr.args) != 2:
                    raise CodegenError("MOD exige exatamente 2 argumentos no codegen")
                self._gen_expression(expr.args[0])
                self._gen_expression(expr.args[1])
                self._emit("MOD")
                return

            # Funções do utilizador são chamadas por endereço (`PUSHA` + `CALL`).
            if name in self._function_meta:
                for arg in expr.args:
                    self._gen_expression(arg)
                self._emit(f"PUSHA {name}")
                self._emit("CALL")
                return

            # Se não for função, podemos ainda estar perante notação de
            # indexação de array que passou como CallExpression.
            try:
                layout, storage = self._resolve_var(name)
            except CodegenError:
                layout = None
                storage = ""

            if layout is not None:
                if layout.is_array:
                    if len(expr.args) != 1:
                        raise CodegenError(f"array '{name}' exige exatamente 1 índice")
                    self._emit_array_base_and_index(storage, layout, expr.args[0])
                    self._emit("LOADN")
                    return
                raise CodegenError(f"'{name}' é escalar mas está a ser usado com argumentos")

            raise CodegenError(f"chamada de função não suportada: {name}")

        raise CodegenError(f"expressão não suportada: {type(expr).__name__}")

    def _emit_binary_op(self, op: str, operand_type: str | None) -> None:
        """Mapeia operador abstrato para opcode EWVM concreto.

        `operand_type` é o tipo numérico dos operandos ("REAL"/"INTEGER"),
        não o tipo do resultado: é o que decide entre a variante inteira e
        a variante de vírgula flutuante, mesmo para comparações (que dão
        sempre LOGICAL mas comparam operandos REAIS com FINF/FSUP/etc.).
        """
        if op == "+":
            self._emit("FADD" if operand_type == "REAL" else "ADD")
        elif op == "-":
            self._emit("FSUB" if operand_type == "REAL" else "SUB")
        elif op == "*":
            self._emit("FMUL" if operand_type == "REAL" else "MUL")
        elif op == "/":
            self._emit("FDIV" if operand_type == "REAL" else "DIV")
        elif op == "**":
            raise CodegenError("operador '**' não suportado pela EWVM nesta fase")
        elif op == ".AND.":
            self._emit("AND")
        elif op == ".OR.":
            self._emit("OR")
        elif op == ".EQ.":
            self._emit("EQUAL")
        elif op == ".NE.":
            self._emit("EQUAL")
            self._emit("NOT")
        elif op == ".LT.":
            self._emit("FINF" if operand_type == "REAL" else "INF")
        elif op == ".LE.":
            self._emit("FINFEQ" if operand_type == "REAL" else "INFEQ")
        elif op == ".GT.":
            self._emit("FSUP" if operand_type == "REAL" else "SUP")
        elif op == ".GE.":
            self._emit("FSUPEQ" if operand_type == "REAL" else "SUPEQ")
        else:
            raise CodegenError(f"operador binário não suportado: {op}")

    def _emit_array_base_and_index(
        self,
        storage: str,
        layout: VarLayout,
        index: Expression | None,
    ) -> None:
        """Empilha endereço base + índice normalizado para arrays.

        O índice Fortran é 1-based nos exemplos do nossso projeto. A EWVM usa
        deslocamento zero-based, por isso subtraímos 1 antes de `LOADN/STOREN`.
        """
        if storage == "global":
            self._emit("PUSHGP")
            self._emit(f"PUSHI {layout.base}")
            self._emit("PADD")
        elif storage == "local":
            self._emit("PUSHFP")
            self._emit(f"PUSHI {layout.base}")
            self._emit("PADD")
        else:
            raise CodegenError("arrays em parâmetros não são suportados")

        self._gen_expression(index)
        self._emit("PUSHI 1")
        self._emit("SUB")

    @staticmethod
    def _operand_numeric_type(left: Expression | None, right: Expression | None) -> str:
        """Tipo numérico dominante de dois operandos.

        Devolve "REAL" se algum operando for REAL, caso contrário "INTEGER".
        Os tipos são lidos do campo `result_type` anotado pela análise
        semântica: o codegen já não reinfere tipos (uma única fonte de
        verdade), eliminando a lógica de inferência antes duplicada aqui.
        """
        left_type = left.result_type if left is not None else None
        right_type = right.result_type if right is not None else None
        if left_type == "REAL" or right_type == "REAL":
            return "REAL"
        return "INTEGER"

    def _resolve_var(self, name: str) -> tuple[VarLayout, str]:
        """Resolve símbolo para layout e classe de armazenamento."""
        canon = self._canon(name)

        if self._current_scope is not None:
            local = self._current_scope.vars.get(canon)
            if local is not None:
                if local.base >= 0:
                    return local, "local"
                return local, "param"

        global_var = self._global_layout.get(canon)
        if global_var is not None:
            return global_var, "global"

        raise CodegenError(f"variável não encontrada no layout: {name}")

    def _emit_load(self, storage: str, offset: int) -> None:
        """Emite instrução de leitura conforme origem (global/local/parâmetro)."""
        if storage == "global":
            self._emit(f"PUSHG {offset}")
            return
        if storage == "local":
            self._emit(f"PUSHL {offset}")
            return
        if storage == "param":
            self._emit("PUSHFP")
            self._emit(f"LOAD {offset}")
            return
        raise CodegenError(f"storage desconhecido para load: {storage}")

    def _emit_store(self, storage: str, offset: int) -> None:
        """Emite instrução de escrita conforme destino."""
        if storage == "global":
            self._emit(f"STOREG {offset}")
            return
        if storage == "local":
            self._emit(f"STOREL {offset}")
            return
        if storage == "param":
            raise CodegenError("atribuição a parâmetros não suportada")
        raise CodegenError(f"storage desconhecido para store: {storage}")

    @staticmethod
    def _canon(name: str) -> str:
        """Normaliza identificadores para maiúsculas (case-insensitive)."""
        return name.upper()

    def _fresh_label(self, prefix: str) -> str:
        """Gera labels internas únicas do codegen."""
        label = f"{prefix}{self._label_counter}"
        self._label_counter += 1
        return label

    def _emit_label(self, label: str) -> None:
        """Emite definição de label no formato esperado pela EWVM."""
        self.instructions.append(f"{label}:")

    def _emit(self, instruction: str) -> None:
        """Acrescenta uma instrução VM linear ao programa final."""
        self.instructions.append(instruction)
