## Objetivo

Clonar a tela `/consulta` em uma nova rota `/consulta-demo` que simula visualmente o fluxo completo, sem gravar áudio nem chamar o backend. Útil para demonstrações.

## Fluxo simulado

1. **Estado inicial** — botão "Iniciar consulta" (azul-petróleo, igual ao real).
2. **Clique em "Iniciar consulta"** → muda para estado "gravando":
   - Botão vira "Finalizar consulta" (vermelho).
   - Indicador de gravação (ponto vermelho pulsante + cronômetro contando) aparece.
   - Nenhum acesso ao microfone é solicitado.
3. **Clique em "Finalizar consulta"** → muda para estado "transcrevendo":
   - Spinner + texto "Transcrevendo…" (~2s simulados).
   - Depois passa para "Estruturando anamnese…" (~2s simulados).
4. **Estado final** → exibe uma anamnese mock pré-pronta (texto fixo em PT-BR cobrindo as seções típicas: Queixa principal, HMA, Antecedentes, Exame físico, Hipótese diagnóstica, Conduta).
5. Botão "Nova consulta" reseta para o estado inicial.

## Arquivos

- **Novo:** `src/routes/consulta-demo.tsx` — define `createFileRoute("/consulta-demo")` com `head()` próprio (título "Consulta DEMO").
- **Novo:** `src/routes/-consulta-demo-page.tsx` — componente clonado de `-consulta-page.tsx`, com toda a lógica de `MediaRecorder`, `fetch` e server functions substituída por `setTimeout` e estado local. Mantém exatamente o mesmo visual (mesmos componentes, classes Tailwind, layout responsivo).
- Nenhuma alteração em `-consulta-page.tsx`, `consulta.tsx`, server functions ou backend.

## Detalhes técnicos

- Estados: `"idle" | "recording" | "transcribing" | "structuring" | "done"`.
- Cronômetro: `useEffect` com `setInterval(1000)` enquanto `recording`.
- Transições: `setTimeout(2000)` para transcrevendo→estruturando→done.
- Anamnese mock: constante de string no topo do arquivo.
- Sem `navigator.mediaDevices`, sem `MediaRecorder`, sem `fetch`.

## Navegação

Acessível diretamente por `/consulta-demo`. (Posso adicionar um link discreto na home ou na própria `/consulta` — me diga se quiser.)
