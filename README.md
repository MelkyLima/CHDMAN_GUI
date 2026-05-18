# CHD Batch Converter

Aplicativo desktop para Windows que localiza jogos em formato BIN/CUE e converte para CHD usando `chdman.exe`.

Janela: **CHD Batch Converter - BIN/CUE para CHD**

## Recursos

- Interface moderna em tema escuro com PySide6
- Varredura recursiva de arquivos `.cue`
- Criacao automatica de `.cue` basico quando houver `.bin` sem CUE
- Validacao de arquivos `.bin` referenciados pelo CUE
- Tabela com selecao, nome, caminho, tamanho, status, progresso e botao individual
- Conversao individual, selecionada ou em lote
- Conversao paralela limitada com sistema de fila
- Barra de progresso geral e progresso individual
- Logs em tempo real
- Busca por nome ou caminho
- Configuracao automatica ou manual do `chdman.exe`
- Pasta destino configuravel para os arquivos `.chd`, com padrao `Games_CHDs`
- Log CSV de metricas por conversao salvo junto dos CHDs

## Requisitos

- Windows 10/11
- Python 3.10+
- `chdman.exe` (MAME CHD tools)

## Como executar em desenvolvimento

1. Instale dependencias:

```powershell
pip install -r requirements.txt
```

2. Coloque `chdman.exe` na pasta raiz do projeto ou selecione manualmente no app.
3. Execute:

```powershell
python app/main.py
```

## Como usar

1. Clique em **Selecionar Pasta**.
2. O app varre a pasta e subpastas automaticamente.
3. Confira os jogos encontrados na tabela.
4. Se quiser, escolha a pasta **Destino**. Por padrao, os CHDs vao para `Games_CHDs`.
5. Use **Converter**, **Converter Selecionados** ou **Converter Todos**.

## Metricas de conversao

Cada conversao adiciona uma linha em:

```text
Games_CHDs/conversion_metrics.csv
```

Campos principais: nome do jogo, caminhos de entrada/saida, sucesso, retorno do processo, tamanho original, tamanho CHD, economia, percentual de compressao, tempo e throughput.

## Build EXE com PyInstaller

```powershell
pip install pyinstaller
.\build.ps1
```

O executavel sera gerado em `dist`.

## Qualidade e testes

```powershell
pip install pytest ruff black
pytest
ruff check .
black --check .
```

## Estrutura

```text
app/
  main.py       Entrada da aplicacao
  gui.py        Interface PySide6
  worker.py     Varredura e fila em threads
  converter.py  Execucao do chdman.exe
  utils.py      Utilidades, validacao e configuracoes
  styles.py     Tema escuro
tests/
pyproject.toml
requirements.txt
build.ps1
```

## Contribuicao

1. Crie branch para sua alteracao.
2. Rode testes e validacoes locais.
3. Abra PR com descricao objetiva, impacto e passos de validacao.

## Roadmap

- Melhorar suporte a imagens multi-disco com heuristicas adicionais
- Adicionar internacionalizacao da interface
- Publicar pipeline CI para lint/test/build

## Licenca

Este projeto usa a licenca MIT. Consulte o arquivo `LICENSE`.
