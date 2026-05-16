"""Pipeline de compilação de alto nível.

Este módulo existe para concentrar o percurso completo do compilador
numa API simples reutilizável por CLI, testes e scripts.
"""

from __future__ import annotations

from pathlib import Path

from .codegen_vm import VMCodeGenerator
from .parser import FortranParser
from .semantics import SemanticAnalyzer


def compile_source_to_vm(source: str) -> list[str]:
    """Compila texto Fortran para instruções VM.

    Parâmetros:
    - `source`: conteúdo de um programa Fortran.

    Devolve:
    - lista de instruções já pronta para serialização.
    """
    ast = FortranParser().parse(source)
    checked_ast = SemanticAnalyzer().analyze(ast)
    return VMCodeGenerator().generate(checked_ast)


def compile_file_to_vm(input_path: Path, output_path: Path | None = None) -> list[str]:
    """Compila ficheiro Fortran e, opcionalmente, escreve ficheiro `.vm`.

    Esta função evita duplicação de código em scripts de validação.
    """
    source = input_path.read_text(encoding="utf-8")
    instructions = compile_source_to_vm(source)
    if output_path is not None:
        output_path.write_text("\n".join(instructions) + "\n", encoding="utf-8")
    return instructions
