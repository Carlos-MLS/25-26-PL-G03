# 25-26-PL-G03

## Grupo 03

- Aluno1: Carlos Miguel Lopes Silva
- Aluno2: Francisco Luís Veloso Soares
- Aluno3: Nuno Francisco Rocha Soares

Compilador de um *subset* de Fortran 77 para a EWVM, desenvolvido em Python com PLY.

## Como compilar e testar na VM (passo a passo)

### 1) Instalar dependências (uma vez)

A única dependência é o `ply`:

```
python3 -m pip install --user ply
```

### 2) Gerar código VM de um ficheiro `.txt`

A partir da raiz do projeto:

```
PYTHONPATH=src python3 -m compilador --mode vm Testes/text/hello.txt     -o output/hello.vm
PYTHONPATH=src python3 -m compilador --mode vm Testes/text/fatorial.txt  -o output/fatorial.vm
PYTHONPATH=src python3 -m compilador --mode vm Testes/text/primo.txt     -o output/primo.vm
PYTHONPATH=src python3 -m compilador --mode vm Testes/text/somaarr.txt   -o output/somaarr.vm
PYTHONPATH=src python3 -m compilador --mode vm Testes/text/conversao.txt -o output/conversao.vm
```

O `--mode` aceita ainda `lex` (tokens), `parse` (AST) e `sem` (análise semântica),
úteis para inspecionar cada fase isoladamente.

### 3) Testar na VM online

1. Abrir: https://ewvm.epl.di.uminho.pt/
2. Copiar o conteúdo de um ficheiro `.vm` da pasta `output/`.
3. Colar no editor da VM.
4. Executar (`Run`).
5. Introduzir números inteiros quando pedido (caso de `primo.vm` e `conversao.vm`).

### 4) Correr os testes automáticos

A partir da raiz do projeto:

```
python3 -m unittest discover -s Testes/py -v
```
