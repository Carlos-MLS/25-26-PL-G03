"""Testes de compilação completa e validação dos exemplos fornecidos."""

from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compilador.compiler import compile_file_to_vm, compile_source_to_vm


class CodegenPipelineTests(unittest.TestCase):
    """Cobre execução ponta-a-ponta do compilador."""

    def test_hello_gera_vm_esperada(self) -> None:
        source = "PROGRAM HELLO\nPRINT *, 'Ola, Mundo!'\nEND\n"
        vm = compile_source_to_vm(source)
        self.assertEqual(
            vm,
            [
                "START",
                'PUSHS "Ola, Mundo!"',
                "WRITES",
                "WRITELN",
                "STOP",
            ],
        )

    def test_programas_exemplo_compilam(self) -> None:
        exemplos = sorted((ROOT / "Testes" / "text").glob("*.txt"))
        self.assertGreaterEqual(len(exemplos), 4, "Esperavam-se vários programas de exemplo em Testes/text/.")
        for ficheiro in exemplos:
            with self.subTest(ficheiro=ficheiro.name):
                vm = compile_source_to_vm(ficheiro.read_text(encoding="utf-8"))
                self.assertGreater(len(vm), 0)
                self.assertEqual(vm[0], "START")
                self.assertIn("STOP", vm)

    def test_compile_file_to_vm_escreve_saida(self) -> None:
        source = "PROGRAM P\nINTEGER A\nA = 3\nPRINT *, A\nEND\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "in.txt"
            out = Path(tmpdir) / "out.vm"
            inp.write_text(source, encoding="utf-8")

            vm = compile_file_to_vm(inp, out)
            self.assertTrue(out.exists())

            written = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(vm, written)


if __name__ == "__main__":
    unittest.main()
