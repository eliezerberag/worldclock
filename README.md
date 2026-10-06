# Relógio Mundial

<img src="icone.png" width="64" align="right" alt="ícone">

Uns relógios de fusos diferentes direto na área de trabalho do Windows. Cada cidade vira um widget pequeno, que você arrasta pra onde quiser. Ele mostra a hora local, a diferença em relação ao seu fuso e se lá é dia (☀) ou noite (☾).

![Relógios na área de trabalho](docs/01-relogios.png)

É um único `.exe`. O Python já vai dentro. Não tem instalador.

## Baixar e abrir

Baixe o executável: [**Relógio Mundial.exe**](https://github.com/eliezerberag/worldclock/raw/main/dist/Rel%C3%B3gio%20Mundial.exe)

Coloque ele numa pasta só dele, por exemplo `Documentos\Relógio Mundial`. O `config.json` vai ser criado aí também. Na primeira vez pode demorar alguns segundos pra abrir.

Quando abre, já vêm quatro cidades: São Paulo, Nova York, Londres e Tóquio. Troque pelas que você usa.

> **Windows reclamando?** O `.exe` não tem assinatura digital. Se aparecer “O Windows protegeu o computador”, clique em **Mais informações → Executar assim mesmo**. Em computador de empresa, o antivírus pode bloquear. Aí só falando com a TI.

## Usando

**Pra mover:** clica e arrasta. Se segurar **Ctrl** enquanto arrasta, move todos juntos.

**Menu:** clique com o botão direito em qualquer relógio.

![Menu do botão direito](docs/02-menu.png)

O menu tem:

- **Configurar localidades…** — adiciona, edita, oculta ou remove cidades.
- **Converter horário…** — mostra que horas ficam em cada cidade num horário escolhido.
- **Ocultar “nome da cidade”** — esconde o relógio sem apagar.
- **Alinhar relógios** — organiza tudo em coluna ou linha.
- **Mover todos juntos** — todos se movem juntos quando você arrasta.
- **Sempre no topo** — deixa os relógios acima das outras janelas.
- **Sair** — fecha o programa.

### Adicionar cidade

1. Botão direito em um relógio → **Configurar localidades…**
2. Clique em **Nova localidade**.
3. Em **Buscar cidade**, digite o nome. A busca online usa o [Open-Meteo](https://open-meteo.com/). Sem internet, aparece só a lista de fusos que já vem no programa.
4. Escolha a cidade, mude o **Nome exibido** se quiser e clique em **Salvar**.

![Tela de localidades buscando Lisboa](docs/03-localidades.png)

Pra editar, seleciona a cidade na lista. Pra ocultar ou mostrar de novo, clique duas vezes nela.

### Converter horário

Na aba **Converter horário**, digite a hora (`14:30` ou `14h30`), a data (`25/12` ou `25/12/2026`) e o fuso de origem. Ele mostra o horário equivalente em todas as suas cidades. O botão **Agora** volta pro horário atual.

![Conversor de horário](docs/04-converter.png)

## Abrir junto com o Windows

Não coloquei isso automático de propósito. Antivírus costumam encher o saco com programa que se enfia na inicialização. Se quiser, faz na mão:

1. Aperta **Win + R**, digita `shell:startup` e dá Enter.
2. Nessa pasta, cria um atalho pro `Relógio Mundial.exe`. O jeito mais fácil é arrastar o arquivo pra lá segurando **Alt**.

Pra desativar, apaga o atalho.

## Configurações

Tudo fica no `config.json`, na mesma pasta do `.exe`: cidades, posições e opções. Pra levar suas configs pra outro computador, copie o `.exe` e o `config.json` juntos. Pra voltar ao padrão, apague o `config.json`.

## Se você for mexer no código

O fonte é o `Relógio Mundial.pyw` (Python 3 + tkinter, sem dependência além do `tzdata`). Pra rodar direto:

```
pip install tzdata
pythonw "Relógio Mundial.pyw"
```

Pra gerar o executável:

```
pip install pyinstaller tzdata
python -m PyInstaller --noconfirm --onefile --windowed --collect-data tzdata --icon icone.ico --add-data "icone.ico;." --name "Relógio Mundial" "Relógio Mundial.pyw"
```

O resultado sai em `dist\`.
