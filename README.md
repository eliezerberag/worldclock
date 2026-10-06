# Relógio Mundial

<img src="icone.png" width="64" align="right" alt="ícone">

Relógios de vários fusos horários direto na área de trabalho do Windows. Cada cidade aparece como um pequeno widget, que você pode arrastar para onde quiser. Ele mostra a hora local, a diferença de horas em relação ao seu fuso e se é dia (☀) ou noite (☾) naquele lugar.

Não precisa instalar nada: é um único arquivo `.exe`, e o Python já vai embutido.

## Download e primeira execução

1. Baixe o executável: [**Relógio Mundial.exe**](https://github.com/eliezerberag/worldclock/raw/main/dist/Rel%C3%B3gio%20Mundial.exe)
2. Coloque o arquivo numa pasta só dele, por exemplo `Documentos\Relógio Mundial`. As suas configurações são salvas nessa mesma pasta.
3. Dê dois cliques para abrir. A primeira abertura pode levar alguns segundos.

Na primeira vez aparecem quatro relógios de exemplo: São Paulo, Nova York, Londres e Tóquio. Troque-os pelas cidades que você usa (veja abaixo).

> **Aviso do Windows:** o executável não tem assinatura digital, então o Windows pode mostrar a tela "O Windows protegeu o computador". Clique em **Mais informações → Executar assim mesmo**. Em computadores de empresa, o antivírus também pode bloquear. Nesse caso, fale com a TI.

## Como usar

**Mover:** clique e arraste um relógio. Para arrastar todos de uma vez, segure **Ctrl** enquanto arrasta.

**Menu:** clique com o **botão direito** em qualquer relógio para ver as opções:

| Opção | O que faz |
|---|---|
| Configurar localidades… | Adiciona, edita, oculta ou remove cidades |
| Converter horário… | Mostra que horas serão em cada cidade num horário escolhido |
| Ocultar “nome da cidade” | Esconde o relógio sem apagá-lo |
| Alinhar relógios | Organiza todos em coluna ou em linha |
| Mover todos juntos | Faz todos os relógios se moverem juntos ao arrastar |
| Sempre no topo | Mantém os relógios acima das outras janelas |
| Sair | Fecha o programa |

### Adicionar uma cidade

1. Botão direito num relógio → **Configurar localidades…**
2. Clique em **Nova localidade**.
3. Em **Buscar cidade**, digite o nome de qualquer cidade do mundo. A busca online usa o [Open-Meteo](https://open-meteo.com/). Sem internet, aparece só a lista de fusos do próprio programa.
4. Escolha a cidade, ajuste o **Nome exibido** se quiser e clique em **Salvar**.

Para editar uma cidade, selecione-a na lista. Para ocultá-la ou mostrá-la de novo, clique duas vezes nela.

### Converter um horário

Na aba **Converter horário**, digite a hora (`14:30` ou `14h30`), a data (`25/12` ou `25/12/2026`) e o fuso de origem. O programa mostra o horário correspondente em todas as suas cidades. O botão **Agora** volta para o horário atual.

## Abrir junto com o Windows

O programa não faz isso sozinho, de propósito: antivírus costumam desconfiar de programas que se colocam na inicialização. Se quiser, faça manualmente:

1. Aperte **Win + R**, digite `shell:startup` e dê Enter.
2. Nessa pasta, crie um atalho para o `Relógio Mundial.exe`: arraste o arquivo para lá segurando **Alt**.

Para desativar, apague o atalho dessa pasta.

## Configurações

Tudo fica no arquivo `config.json`, na mesma pasta do `.exe`: cidades, posições e opções. Para levar suas configurações para outro computador, copie o `.exe` e o `config.json` juntos. Para voltar ao padrão, apague o `config.json`.

## Para desenvolvedores

O código-fonte é o `Relógio Mundial.pyw` (Python 3 + tkinter, sem dependências além do `tzdata`). Para rodar direto:

```
pip install tzdata
pythonw "Relógio Mundial.pyw"
```

Para gerar o executável:

```
pip install pyinstaller tzdata
python -m PyInstaller --noconfirm --onefile --windowed --collect-data tzdata --icon icone.ico --add-data "icone.ico;." --name "Relógio Mundial" "Relógio Mundial.pyw"
```

O resultado fica em `dist\`.
