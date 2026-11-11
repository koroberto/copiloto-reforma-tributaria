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
uv run pytest
```

## Estrutura

```
copiloto/nfe.py         leitura do XML da NF-e (itens, NCM, CFOP, valores e tributos)
tests/                  testes com uma NF-e sintética
dados/                  XMLs e cadastros de exemplo (nunca dados reais de cliente sem anonimizar)
docs/                   proposta, plano, regras da transição
```
