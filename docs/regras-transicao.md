# Regras da transição (a conferir)

> **Nada aqui foi conferido na lei ainda.** É um resumo de memória do cronograma da EC 132/2023 e da LC 214/2025, para orientar a estrutura do código. Antes de usar qualquer valor no simulador, conferir o artigo correspondente no texto oficial (planalto.gov.br) e anotar o artigo na coluna "Fonte".

| Ano | CBS | IBS | PIS/Cofins | IPI | ICMS e ISS | Fonte conferida |
|---|---|---|---|---|---|---|
| 2026 | fase de teste (alíquota simbólica, compensável) | fase de teste (alíquota simbólica) | mantidos | mantido | mantidos | ⬜ |
| 2027 | integral | ainda simbólico | extintos | zerado, exceto Zona Franca | mantidos | ⬜ |
| 2028 | integral | ainda simbólico | — | idem | mantidos | ⬜ |
| 2029 a 2032 | integral | sobe aos poucos | — | idem | caem aos poucos | ⬜ |
| 2033 | integral | integral | — | idem | extintos | ⬜ |

## Parâmetros que o simulador precisa
- Alíquota de referência da CBS e do IBS (ainda dependem de definição oficial: trabalhar com cenários).
- Percentual de ICMS/ISS mantido em cada ano de 2029 a 2032.
- Reduções de alíquota por regime diferenciado (60%, 100%) e lista de NCMs de cada um (anexos da LC 214/2025).
- Regras de crédito (crédito amplo na CBS/IBS).

Cada parâmetro vai para um arquivo de configuração com o valor, o artigo da lei e a data em que foi conferido.
