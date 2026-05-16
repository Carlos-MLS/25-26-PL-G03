"""Interface de linha de comandos do compilador.

Disponibiliza quatro modos:
- `lex`: inspecionar tokens;
- `parse`: inspecionar AST;
- `sem`: validar semântica;
- `vm`: gerar código da máquina virtual.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from pathlib import Path
from pprint import pprint

from .codegen_vm import CodegenError
from .compiler import compile_source_to_vm
from .lexer import LexicalError, tokenize
from .parser import FortranParser, ParseError
from .semantics import SemanticAnalyzer, SemanticError


def main() -> int:
    """Devolve código de saída POSIX:"""
    parser = argparse.ArgumentParser(description="Ferramentas do compilador Fortran 77 (subset).")
    parser.add_argument("input", type=Path, help="Ficheiro Fortran de entrada")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Ficheiro de saída (apenas para --mode vm).",
    )
    parser.add_argument(
        "--mode",
        choices=("lex", "parse", "sem", "vm"),
        default="lex",
        help="Modo: lex (tokens), parse (AST), sem (análise semântica), vm (código VM).",
    )
    args = parser.parse_args()

    source = args.input.read_text(encoding="utf-8")
    if args.mode == "lex":
        # Modo de diagnóstico rápido do lexer.
        try:
            tokens = tokenize(source)
        except LexicalError as err:
            print(err)
            return 1

        for tok in tokens:
            print(f"{tok.lineno:>4}:{tok.lexpos:<4} {tok.type:<16} {tok.value!r}")
        return 0

    try:
        ast = FortranParser().parse(source)
    except (LexicalError, ParseError) as err:
        print(err)
        return 1

    if args.mode == "parse":
        # Mostra AST serializada para facilitar debug da gramática.
        pprint(asdict(ast) if is_dataclass(ast) else ast, sort_dicts=False)
        return 0

    if args.mode == "sem":
        # Executa apenas até semântica (sem gerar VM).
        analyzer = SemanticAnalyzer()
        try:
            checked_ast = analyzer.analyze(ast)
        except SemanticError as err:
            print(err)
            return 1

        print("Análise semântica: OK")
        print(f"Símbolos: {', '.join(sorted(analyzer.symbols.keys()))}")
        return 0

    try:
        # Pipeline completo parse -> semântica -> codegen.
        instructions = compile_source_to_vm(source)
    except (LexicalError, ParseError, SemanticError, CodegenError) as err:
        print(err)
        return 1

    if args.output is not None:
        args.output.write_text("\n".join(instructions) + "\n", encoding="utf-8")

    for inst in instructions:
        print(inst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
