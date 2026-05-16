"""API pública do compilador Fortran 77 -> VM.

Este módulo agrega os principais pontos de extensão para uso externo:
lexer, parser, semântica, codegen e funções de compilação completa.
"""

from .lexer import FortranLexer, tokenize
from .parser import FortranParser, ParseError
from .semantics import SemanticAnalyzer, SemanticError
from .codegen_vm import VMCodeGenerator, CodegenError
from .compiler import compile_file_to_vm, compile_source_to_vm

__all__ = [
    "FortranLexer",
    "FortranParser",
    "ParseError",
    "SemanticAnalyzer",
    "SemanticError",
    "VMCodeGenerator",
    "CodegenError",
    "compile_source_to_vm",
    "compile_file_to_vm",
    "tokenize",
]
