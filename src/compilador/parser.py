"""Parser PLY para o subset de Fortran 77 definido no projeto.

Este módulo converte a sequência de tokens (produzida pelo lexer) numa AST.
As regras seguem um estilo bottom-up típico do `yacc`, com ações semânticas
que instanciam nós da AST em cada redução.
"""

from __future__ import annotations

from dataclasses import dataclass

import ply.yacc as yacc

from .ast import (
    Assignment,
    BinaryOp,
    CallExpression,
    ContinueStatement,
    Declaration,
    DoStatement,
    FunctionDef,
    GotoStatement,
    IfStatement,
    IndexedRef,
    Literal,
    PrintStatement,
    Program,
    ReadStatement,
    ReturnStatement,
    UnaryOp,
    VariableDecl,
    VariableRef,
)
from .lexer import FortranLexer


@dataclass(slots=True)
class ParseError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class FortranParser:
    """Parser principal do compilador.

    A classe encapsula:
    - tabela de precedências para resolver ambiguidades em expressões;
    - gramática do subset Fortran;
    - construção de AST usada pelas fases seguintes.
    """

    tokens = FortranLexer.tokens

    # Define precedência e associatividade dos operadores de expressão.
    precedence = (
        ("left", "OR"),
        ("left", "AND"),
        ("right", "NOT"),
        ("nonassoc", "EQ", "NE", "LT", "LE", "GT", "GE"),
        ("left", "PLUS", "MINUS"),
        ("left", "TIMES", "DIVIDE"),
        ("right", "POWER"),
        ("right", "UMINUS"),
    )

    def __init__(self) -> None:
        """Inicializa lexer + parser PLY.

        `start="compilation_unit"` permite reconhecer programa principal
        e, opcionalmente, definições de funções após o bloco principal.
        """
        self.lexer = FortranLexer()
        self._source = ""
        self.parser = yacc.yacc(
            module=self,
            start="compilation_unit",
            debug=False,
            write_tables=False,
            errorlog=yacc.NullLogger(),
        )

    def parse(self, source: str) -> Program:
        """Executa parsing completo e devolve a AST do programa.

        Parâmetros:
        - `source`: texto Fortran a analisar.

        Devolve:
        - instância `Program` (raiz da AST).
        """
        self._source = source
        return self.parser.parse(source, lexer=self.lexer)

    def p_compilation_unit(self, p):
        """compilation_unit : leading_newlines program function_defs opt_newlines"""
        program = p[2]
        program.functions = p[3]
        p[0] = program

    def p_program(self, p):
        """program : PROGRAM IDENTIFIER NEWLINE program_items END opt_newlines"""
        decls, stmts = p[4]
        p[0] = Program(name=p[2], declarations=decls, statements=stmts, line=p.lineno(1))

    def p_function_defs_many(self, p):
        """function_defs : function_defs function_def"""
        p[0] = p[1] + [p[2]]

    def p_function_defs_empty(self, p):
        """function_defs : empty"""
        p[0] = []

    def p_function_def(self, p):
        """function_def : type_spec FUNCTION IDENTIFIER LPAREN param_list_opt RPAREN NEWLINE program_items END opt_newlines"""
        return_type, _ = p[1]
        decls, stmts = p[8]
        p[0] = FunctionDef(
            name=p[3],
            return_type=return_type,
            parameters=p[5],
            declarations=decls,
            statements=stmts,
            line=p.lineno(2),
        )

    def p_param_list_opt_empty(self, p):
        """param_list_opt : empty"""
        p[0] = []

    def p_param_list_opt_single(self, p):
        """param_list_opt : IDENTIFIER"""
        p[0] = [p[1]]

    def p_param_list_opt_many(self, p):
        """param_list_opt : param_list_opt COMMA IDENTIFIER"""
        p[0] = p[1] + [p[3]]

    def p_leading_newlines(self, p):
        """leading_newlines : empty
        | leading_newlines NEWLINE
        """

    def p_opt_newlines(self, p):
        """opt_newlines : empty
        | opt_newlines NEWLINE
        """

    def p_program_items_empty(self, p):
        """program_items : empty"""
        p[0] = ([], [])

    def p_program_items_append(self, p):
        """program_items : program_items program_item"""
        declarations, statements = p[1]
        item = p[2]

        # Ignora entradas vazias no bloco.
        if item is None:
            p[0] = (declarations, statements)
            return

        kind, node = item
        # Acumula declarações e instruções em listas separadas.
        if kind == "decl":
            declarations = declarations + [node]
        else:
            statements = statements + [node]
        p[0] = (declarations, statements)

    def p_program_item_decl(self, p):
        """program_item : declaration NEWLINE"""
        p[0] = ("decl", p[1])

    def p_program_item_stmt(self, p):
        """program_item : statement"""
        p[0] = ("stmt", p[1])

    def p_program_item_blank(self, p):
        """program_item : NEWLINE"""
        p[0] = None

    def p_statement(self, p):
        """statement : label_opt simple_statement NEWLINE
        | label_opt if_statement
        | label_opt do_statement
        """
        stmt = p[2]
        # Anexa label opcional ao statement reconhecido.
        if p[1] is not None:
            stmt.label = p[1]
        p[0] = stmt

    def p_label_opt(self, p):
        """label_opt : empty
        | LABEL
        """
        p[0] = p[1]

    def p_simple_statement(self, p):
        """simple_statement : assignment
        | goto_statement
        | continue_statement
        | return_statement
        | read_statement
        | print_statement
        """
        p[0] = p[1]

    def p_simple_statement_no_continue(self, p):
        """simple_statement_no_continue : assignment
        | goto_statement
        | read_statement
        | print_statement
        """
        p[0] = p[1]

    def p_declaration(self, p):
        """declaration : type_spec decl_list"""
        type_name, type_line = p[1]
        p[0] = Declaration(type_name=type_name, variables=p[2], line=type_line)

    def p_type_spec(self, p):
        """type_spec : INTEGER
        | REAL
        | LOGICAL
        """
        p[0] = (p[1], p.lineno(1))

    def p_decl_list_single(self, p):
        """decl_list : decl_item"""
        p[0] = [p[1]]

    def p_decl_list_many(self, p):
        """decl_list : decl_list COMMA decl_item"""
        p[0] = p[1] + [p[3]]

    def p_decl_item_scalar(self, p):
        """decl_item : IDENTIFIER"""
        p[0] = VariableDecl(name=p[1], line=p.lineno(1))

    def p_decl_item_array(self, p):
        """decl_item : IDENTIFIER LPAREN INTEGER_LITERAL RPAREN"""
        p[0] = VariableDecl(name=p[1], array_size=p[3], line=p.lineno(1))

    def p_assignment(self, p):
        """assignment : designator ASSIGN expression"""
        p[0] = Assignment(target=p[1], value=p[3], line=p.lineno(2))

    def p_designator_name(self, p):
        """designator : IDENTIFIER"""
        p[0] = VariableRef(name=p[1], line=p.lineno(1))

    def p_designator_indexed(self, p):
        """designator : IDENTIFIER LPAREN expression RPAREN"""
        p[0] = IndexedRef(name=p[1], index=p[3], line=p.lineno(1))

    def p_goto_statement(self, p):
        """goto_statement : GOTO INTEGER_LITERAL"""
        p[0] = GotoStatement(target_label=p[2], line=p.lineno(1))

    def p_continue_statement(self, p):
        """continue_statement : CONTINUE"""
        p[0] = ContinueStatement(line=p.lineno(1))

    def p_return_statement(self, p):
        """return_statement : RETURN"""
        p[0] = ReturnStatement(line=p.lineno(1))

    def p_read_statement(self, p):
        """read_statement : READ TIMES COMMA read_list"""
        p[0] = ReadStatement(items=p[4], line=p.lineno(1))

    def p_read_list_single(self, p):
        """read_list : designator"""
        p[0] = [p[1]]

    def p_read_list_many(self, p):
        """read_list : read_list COMMA designator"""
        p[0] = p[1] + [p[3]]

    def p_print_statement(self, p):
        """print_statement : PRINT TIMES COMMA expr_list"""
        p[0] = PrintStatement(items=p[4], line=p.lineno(1))

    def p_if_statement(self, p):
        """if_statement : IF LPAREN expression RPAREN THEN NEWLINE statement_block endif_tail"""
        else_body = p[8]
        p[0] = IfStatement(condition=p[3], then_body=p[7], else_body=else_body, line=p.lineno(1))

    def p_endif_tail_plain(self, p):
        """endif_tail : ENDIF NEWLINE"""
        p[0] = []

    def p_endif_tail_else(self, p):
        """endif_tail : ELSE NEWLINE statement_block ENDIF NEWLINE"""
        p[0] = p[3]

    def p_do_statement(self, p):
        """do_statement : DO INTEGER_LITERAL IDENTIFIER ASSIGN expression COMMA expression do_step_opt NEWLINE do_block do_end"""
        # Acrescenta o CONTINUE final ao corpo do ciclo.
        continue_label, continue_line = p[11]
        end_stmt = ContinueStatement(label=continue_label, line=continue_line)
        body = p[10] + [end_stmt]

        p[0] = DoStatement(
            end_label=p[2],
            iterator=p[3],
            start=p[5],
            end=p[7],
            step=p[8],
            body=body,
            continue_label=continue_label,
            line=p.lineno(1),
        )

    def p_do_step_opt(self, p):
        """do_step_opt : empty
        | COMMA expression
        """
        p[0] = None if len(p) == 2 else p[2]

    def p_statement_block_empty(self, p):
        """statement_block : empty"""
        p[0] = []

    def p_statement_block_stmt(self, p):
        """statement_block : statement_block statement"""
        p[0] = p[1] + [p[2]]

    def p_statement_block_blank(self, p):
        """statement_block : statement_block NEWLINE"""
        p[0] = p[1]

    def p_do_end(self, p):
        """do_end : LABEL CONTINUE NEWLINE"""
        p[0] = (p[1], p.lineno(1))

    def p_do_block_empty(self, p):
        """do_block : empty"""
        p[0] = []

    def p_do_block_stmt(self, p):
        """do_block : do_block do_block_item"""
        p[0] = p[1] + [p[2]]

    def p_do_block_blank(self, p):
        """do_block : do_block NEWLINE"""
        p[0] = p[1]

    def p_do_block_item_simple(self, p):
        """do_block_item : label_opt simple_statement_no_continue NEWLINE"""
        stmt = p[2]
        # Reconhece statements simples dentro do corpo do DO.
        if p[1] is not None:
            stmt.label = p[1]
        p[0] = stmt

    def p_do_block_item_if(self, p):
        """do_block_item : label_opt if_statement"""
        stmt = p[2]
        if p[1] is not None:
            stmt.label = p[1]
        p[0] = stmt

    def p_do_block_item_do(self, p):
        """do_block_item : label_opt do_statement"""
        stmt = p[2]
        if p[1] is not None:
            stmt.label = p[1]
        p[0] = stmt

    def p_expr_list_single(self, p):
        """expr_list : expression"""
        p[0] = [p[1]]

    def p_expr_list_many(self, p):
        """expr_list : expr_list COMMA expression"""
        p[0] = p[1] + [p[3]]

    def p_call_arg_list_opt_empty(self, p):
        """call_arg_list_opt : empty"""
        p[0] = []

    def p_call_arg_list_opt_single(self, p):
        """call_arg_list_opt : expression"""
        p[0] = [p[1]]

    def p_call_arg_list_opt_many(self, p):
        """call_arg_list_opt : call_arg_list_opt COMMA expression"""
        p[0] = p[1] + [p[3]]

    def p_expression_binary(self, p):
        """expression : expression OR expression
        | expression AND expression
        | expression EQ expression
        | expression NE expression
        | expression LT expression
        | expression LE expression
        | expression GT expression
        | expression GE expression
        | expression PLUS expression
        | expression MINUS expression
        | expression TIMES expression
        | expression DIVIDE expression
        | expression POWER expression
        """
        p[0] = BinaryOp(op=p[2], left=p[1], right=p[3], line=p.lineno(2))

    def p_expression_not(self, p):
        """expression : NOT expression"""
        p[0] = UnaryOp(op=p[1], operand=p[2], line=p.lineno(1))

    def p_expression_uminus(self, p):
        """expression : MINUS expression %prec UMINUS"""
        p[0] = UnaryOp(op="NEG", operand=p[2], line=p.lineno(1))

    def p_expression_group(self, p):
        """expression : LPAREN expression RPAREN"""
        p[0] = p[2]

    def p_expression_call(self, p):
        """expression : IDENTIFIER LPAREN call_arg_list_opt RPAREN"""
        # Constrói nó de expressão com identificador e argumentos.
        p[0] = CallExpression(name=p[1], args=p[3], line=p.lineno(1))

    def p_expression_identifier(self, p):
        """expression : IDENTIFIER"""
        p[0] = VariableRef(name=p[1], line=p.lineno(1))

    def p_expression_integer_literal(self, p):
        """expression : INTEGER_LITERAL"""
        p[0] = Literal(value=p[1], literal_type="INTEGER", line=p.lineno(1))

    def p_expression_real_literal(self, p):
        """expression : REAL_LITERAL"""
        p[0] = Literal(value=p[1], literal_type="REAL", line=p.lineno(1))

    def p_expression_string_literal(self, p):
        """expression : STRING_LITERAL"""
        p[0] = Literal(value=p[1], literal_type="STRING", line=p.lineno(1))

    def p_expression_bool_literal(self, p):
        """expression : BOOL_LITERAL"""
        p[0] = Literal(value=p[1], literal_type="LOGICAL", line=p.lineno(1))

    def p_empty(self, p):
        """empty :"""
        p[0] = None

    def p_error(self, p):
        """Converte erros do `yacc` em mensagens consistentes do projeto."""
        if p is None:
            raise ParseError("Erro sintático: fim de ficheiro inesperado.")

        column = FortranLexer._find_column(self._source, p.lexpos)
        raise ParseError(f"Erro sintático perto de '{p.value}' (linha {p.lineno}, coluna {column}).")
