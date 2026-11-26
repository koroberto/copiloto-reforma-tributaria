# Copiloto da Reforma Tributária para PMEs

Projeto Desafio do **Grupo 4** (Caio Roberto, Danilo Almeida e Guilherme Monteiro) em Sistemas Inteligentes II (Pós em IA do Senac, Prof. Marcelo R. Batalha).

Em uma frase: transformar os dados fiscais que a empresa já tem (XMLs de NF-e e cadastro de produtos) em uma decisão clara de preço para a transição da Reforma Tributária (CBS e IBS no lugar de PIS, Cofins, IPI, ICMS e ISS, de 2026 a 2033).

- Proposta completa: [docs/proposta.md](docs/proposta.md)
- Plano até a entrega (aulas 7 e 8): [docs/plano.md](docs/plano.md)
- Regras da transição (a conferir na lei): [docs/regras-transicao.md](docs/regras-transicao.md)

## Divisão de responsabilidade entre código e IA

| Parte | Quem faz | Por quê |
|---|---|---|
| Ler os XMLs da NF-e | Código | Formato fixo (layout da SEFAZ) |
| Cálculo da carga antes e depois | **Código, com alíquotas parametrizadas** | O imposto não pode ser "inventado" pela IA |
| Enquadramento do produto (alíquota padrão, reduzida, isenta, regime específico) | IA, com nível de confiança | Lê descrição e NCM; o contador revisa |
| Achar inconsistências no cadastro (NCM errado, descrição vaga) | IA | Texto livre e dados sujos |
| Explicar o impacto em linguagem simples | IA | "Este produto perde 3,2 pontos de margem porque..." |
| Priorizar os alertas | Código (impacto × volume), IA explica | Ordem reproduzível |

Toda sugestão de enquadramento passa por **revisão humana do contador**.

A sugestão da IA é conferida com a **tabela oficial da Receita** (NCM por anexo da LC 214/2025), tirada da calculadora de código aberto que a Receita publicou no GitHub em novembro de 2026 (licença MIT, sem efeito normativo). Redução de alíquota sem respaldo na tabela vai para revisão; padrão com NCM que aparece em algum anexo gera alerta. Para atualizar a tabela: `python scripts/tabela_receita.py <clone-da-calculadora>`.

## Uso no dia a dia: o cadastro inteiro (lote)

A aba "Cadastro do cliente (lote)" é o fluxo principal. O contador envia o cadastro de produtos exportado do ERP (CSV ou Excel) ou os XMLs das notas. Para cada produto:

1. a entrada é verificada antes da IA;
2. a IA sugere o enquadramento, com todos os itens num prompt só;
3. a sugestão é conferida com a tabela oficial da Receita.

Quando a tabela e a IA concordam, com confiança alta e um único cClassTrib possível, o item é aprovado sozinho e marcado como "automático". O resto vai para uma fila de revisão, com o motivo escrito. A planilha com o cClassTrib de cada produto só é liberada quando a fila zera.

Para testar sem chave de API, use o modo Simulada com o cadastro de exemplo (`exemplos/cadastro-distribuidora-ficticia.csv`, 34 produtos). Ele usa a resposta real do Gemini gravada em `exemplos/resposta-gemini-cadastro-exemplo.txt`: 27 itens são aprovados automaticamente e 7 vão para a fila. Requisitos em EARS e a tabela requisito → teste: [docs/requisitos-ears.md](docs/requisitos-ears.md).

## Recorte do MVP

Um regime (Lucro Presumido ou Real, a decidir), um setor (ex.: distribuição) e um ano-alvo da simulação. Fluxo:

```
XMLs NF-e + cadastro de produtos
        │
        ▼
 leitura das notas (copiloto/nfe.py) ── NCM, CFOP, valores e tributos por item
        │
        ▼
 enquadramento pela IA ── sugestão + confiança → revisão do contador
        │
        ▼
 cálculo determinístico ── carga atual × carga CBS/IBS no ano-alvo
        │
        ▼
 relatório ── variação de margem por produto, preço sugerido, alertas priorizados
```

## Rodar

```bash
uv venv && uv pip install -r requirements.txt
uv run pytest                 # testes
uv run mutmut run && uv run mutmut results   # teste de mutação (força dos testes)
uv run streamlit run app.py   # MVP em http://localhost:8501
```

Integração automática com o Gemini (opcional): `export GEMINI_API_KEY=...` antes de abrir o app. Sem chave, use os modos Simulada ou Manual.

## Estrutura

```
app.py                  interface Streamlit: aba do lote e aba de um produto passo a passo
copiloto/enquadramento.py  verificação da entrada, prompt V3, conferência da resposta, IA simulada/manual/integrada
copiloto/tabela_oficial.py confere a sugestão da IA com a tabela oficial da Receita (NCM por anexo da LC 214)
copiloto/lote.py        cadastro inteiro: leitura de CSV/XLSX/XML, prompt em lote, aprovação automática, fila e planilha de saída
exemplos/               cadastro fictício de distribuidora e a resposta real do Gemini a ele (modo Simulada)
scripts/tabela_receita.py  extrai essa tabela da calculadora oficial (github.com/ReceitaFederal/calculadora-rtc-regime-regular)
dados/receita/          tabela extraída (CSV) e origem.json com o commit da Receita usado
copiloto/nfe.py         leitura do XML da NF-e (itens, NCM, CFOP, valores e tributos)
tests/                  testes com uma NF-e sintética
dados/                  XMLs e cadastros de exemplo (nunca dados reais de cliente sem anonimizar)
docs/                   proposta, plano, regras da transição
```
