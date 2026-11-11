# Proposta: Copiloto da Reforma Tributária para PMEs

Texto do Guilherme Monteiro (e-mail de 19/10/2026, 21:52), enviado ao grupo como "Proposta Inicial – Grupo 4" (PDF e Word).

## 1. Problema e contexto
A Reforma Tributária (EC 132/2023 e LC 214/2025) substitui PIS, Cofins, IPI, ICMS e ISS pela CBS (federal) e pelo IBS (estados e municípios), com transição gradual de 2026 a 2033. Durante esse período os dois sistemas convivem, as alíquotas mudam ano a ano e a lógica passa a ser de crédito amplo e cobrança no destino.

PMEs e escritórios contábeis não sabem responder perguntas práticas: "meu produto vai ficar mais caro ou mais barato de tributar?", "minha margem cai?", "preciso reajustar preço ou renegociar contrato de longo prazo?". Hoje essa análise é feita em planilhas manuais, produto a produto, o que é lento, caro e sujeito a erro. O risco é a empresa perder margem sem perceber ou ficar fora de preço frente à concorrência.

## 2. Usuário
- **Principal:** contadores e analistas fiscais de escritórios de contabilidade, que atendem dezenas ou centenas de clientes.
- **Secundário:** gestores financeiros, controllers e donos de indústrias e distribuidoras médias.
- **Quem paga:** os escritórios (assinatura por carteira de clientes) e as empresas médias.

## 3. Situação de uso
- Planejar a formação de preço para o próximo ano da transição (ex.: antes da virada de 2026 para 2027, quando a CBS passa a valer por inteiro e o PIS e a Cofins são extintos).
- Revisar ou assinar contratos de fornecimento de longo prazo (cláusula de reequilíbrio tributário).
- Reuniões de consultoria do escritório com o cliente, como ferramenta de diagnóstico e de venda de serviço consultivo.
- Quando saírem novas regulamentações ou alíquotas de referência.

## 4. Entrada
- XMLs de NF-e de entrada e saída de um período (ex.: 12 meses): NCM, CFOP, CST, valores, ICMS, PIS/Cofins, IPI, UF de origem e destino.
- Cadastro de produtos: código, descrição, NCM, custo, preço de venda.
- Dados da empresa: regime (Simples, Presumido, Real), CNAE, UF.
- Opcional: margem-alvo e cenário de alíquota.

## 5. Saída
- Simulador "antes × depois" por produto, em cada ano da transição.
- Impacto em margem (% e R$) por produto e no total.
- Alertas de preço priorizados, com preço sugerido para manter a margem.
- Sinalização de regimes diferenciados (reduções de 60% e 100%, cesta básica, regimes específicos) para validação do contador.
- Relatório exportável, para o escritório apresentar ao cliente.

## 6. Tarefa da IA
- **Classificação e enquadramento** do produto pela descrição e NCM, com nível de confiança.
- **Extração e normalização** de XMLs heterogêneos e cadastros inconsistentes.
- **Explicação em linguagem simples** do impacto.
- **Priorização dos alertas** (impacto em margem × volume de vendas).

O cálculo tributário é determinístico (regras e alíquotas parametrizadas). A IA atua na classificação, interpretação e comunicação, sempre com revisão humana do contador.

## 7. Função principal do MVP
Subir os XMLs e o cadastro e receber, em poucos minutos, um diagnóstico de impacto por produto: carga antes e depois, variação de margem e lista de preços a rever.

**Recorte sugerido:** um regime (Presumido ou Real), um setor (ex.: distribuição) e um ano-alvo, para reduzir a complexidade das regras e mostrar resultado rápido aos primeiros escritórios piloto.

## Pontos a fechar com o grupo (leitura do e-mail em 11/11/2026)
- **Um ano-alvo ou a série inteira:** a seção 5 pede a simulação em cada ano de 2026 a 2033, mas o recorte fala em um ano-alvo só. Sugestão: um ano no MVP (2027) e a série completa como evolução.
- **Simples Nacional:** a entrada cita os três regimes, mas o recorte deixa o Simples de fora, e a maioria das PMEs está nele. Se continuar fora, registrar como limitação no artigo.
