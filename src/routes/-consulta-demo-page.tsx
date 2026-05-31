import { useEffect, useRef, useState } from "react";
import {
  Clock,
  Play,
  Square,
  Lock,
  Printer,
  Share2,
  Plus,
  ChevronDown,
  Loader2,
} from "lucide-react";

const PACIENTE = {
  nome: "Pedro Henrique Alves",
  nascimento: "15/05/2002",
  idade: "23 anos",
  primeiraConsulta: "29/10/2017",
  convenio: "Unimed",
  atendimentos: 2,
  faltas: 0,
  iniciais: "PA",
};

const ANAMNESE_MOCK = `QUEIXA PRINCIPAL
Dor de cabeça intensa há 3 dias.

HISTÓRIA DA MOLÉSTIA ATUAL
Paciente refere cefaleia holocraniana, de caráter pulsátil, com início há 3 dias, de intensidade moderada a forte (7/10). Relata piora com luminosidade e ruídos. Nega febre, vômitos ou alterações visuais. Já fez uso de dipirona 1g, com alívio parcial.

ANTECEDENTES PESSOAIS
- Sem comorbidades conhecidas.
- Nega tabagismo e etilismo.
- Histórico familiar de enxaqueca (mãe).

EXAME FÍSICO
- BEG, LOTE, corado, hidratado, acianótico, anictérico.
- PA: 120x80 mmHg | FC: 76 bpm | FR: 16 irpm | Tax: 36,5°C
- ACV: BNRNF em 2T, sem sopros.
- AR: MV+ bilateralmente, sem RA.
- Abdome: plano, flácido, indolor à palpação.
- Neurológico: sem déficits focais. Pupilas isocóricas e fotorreagentes.

HIPÓTESE DIAGNÓSTICA
Enxaqueca sem aura (CID G43.0).

CONDUTA
1. Sumatriptano 50mg VO, se crise.
2. Orientações sobre higiene do sono e gatilhos alimentares.
3. Retorno em 30 dias para reavaliação.
4. Solicitado diário de cefaleia.`;

type Status =
  | "idle"
  | "recording"
  | "transcribing"
  | "structuring"
  | "done";

function formatTime(totalSeconds: number) {
  const h = Math.floor(totalSeconds / 3600).toString().padStart(2, "0");
  const m = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, "0");
  const s = (totalSeconds % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

export function ConsultaDemoPage() {
  const [status, setStatus] = useState<Status>("idle");
  const [elapsed, setElapsed] = useState(0);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const stopTimer = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const clearTimeouts = () => {
    timeoutsRef.current.forEach((t) => clearTimeout(t));
    timeoutsRef.current = [];
  };

  useEffect(() => {
    return () => {
      stopTimer();
      clearTimeouts();
    };
  }, []);

  const handleIniciar = () => {
    setElapsed(0);
    setStatus("recording");
    intervalRef.current = setInterval(() => {
      setElapsed((s) => s + 1);
    }, 1000);
  };

  const handleFinalizar = () => {
    stopTimer();
    setStatus("transcribing");
    const t1 = setTimeout(() => setStatus("structuring"), 2000);
    const t2 = setTimeout(() => setStatus("done"), 4000);
    timeoutsRef.current.push(t1, t2);
  };

  const handleNova = () => {
    clearTimeouts();
    stopTimer();
    setElapsed(0);
    setStatus("idle");
  };

  const isRecording = status === "recording";
  const isProcessing = status === "transcribing" || status === "structuring";
  const isDone = status === "done";

  const [agora, setAgora] = useState<{
    dia: string;
    mes: string;
    ano: string;
    horaAgora: string;
  }>({ dia: "", mes: "", ano: "", horaAgora: "" });

  useEffect(() => {
    const hoje = new Date();
    setAgora({
      dia: hoje.getDate().toString().padStart(2, "0"),
      mes: hoje.toLocaleString("pt-BR", { month: "short" }).replace(".", "").toUpperCase(),
      ano: String(hoje.getFullYear()),
      horaAgora: hoje.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
    });
  }, []);
  const { dia, mes, ano, horaAgora } = agora;

  const timelineMensagem = (() => {
    switch (status) {
      case "recording":
        return { tone: "text-muted-foreground italic", text: "Gravação em andamento…" };
      case "transcribing":
        return { tone: "text-muted-foreground italic", text: "Transcrevendo áudio…" };
      case "structuring":
        return { tone: "text-muted-foreground italic", text: "Estruturando anamnese…" };
      case "done":
        return { tone: "text-foreground", text: "Anamnese gerada com sucesso." };
      default:
        return { tone: "text-muted-foreground italic", text: "Nenhum atendimento registrado nesta sessão." };
    }
  })();

  const buttonLabel = isRecording
    ? "Finalizar consulta"
    : isProcessing
      ? status === "transcribing"
        ? "Transcrevendo…"
        : "Estruturando…"
      : isDone
        ? "Nova consulta"
        : "Iniciar consulta";

  const handleClick = isRecording
    ? handleFinalizar
    : isDone
      ? handleNova
      : isProcessing
        ? undefined
        : handleIniciar;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ============ MOBILE LAYOUT ============ */}
      <div className="flex min-h-screen flex-col md:hidden">
        <header className="flex h-12 items-center justify-center bg-primary px-5 text-primary-foreground">
          <span className="text-base font-semibold tracking-tight">
            ◆ Prontuário <span className="ml-2 rounded bg-primary-foreground/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">Demo</span>
          </span>
        </header>

        <section className="flex flex-col items-center gap-3 border-b border-border bg-card px-5 py-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
            {PACIENTE.iniciais}
          </div>
          <h1 className="text-3xl font-bold leading-tight text-slate-800">{PACIENTE.nome}</h1>
          <p className="text-sm leading-relaxed text-slate-500">
            <span className="text-slate-500">Nascimento:</span>{" "}
            <span className="font-medium text-slate-800">{PACIENTE.nascimento}</span>
          </p>
        </section>

        <section className="px-5 pt-8 text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Duração da consulta</p>
          <p className="mt-1 font-mono text-5xl font-semibold tabular-nums text-foreground">{formatTime(elapsed)}</p>
          {isRecording && (
            <div className="mt-2 flex items-center justify-center gap-2 text-xs font-medium text-destructive">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-destructive" />
              Gravando áudio…
            </div>
          )}
        </section>

        <section className="flex flex-col items-center px-5 pt-8">
          <button
            type="button"
            onClick={handleClick}
            disabled={isProcessing}
            className={
              "flex h-48 w-48 flex-col items-center justify-center gap-2 rounded-full text-base font-semibold shadow-lg transition-colors active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 " +
              (isRecording
                ? "bg-destructive text-destructive-foreground ring-8 ring-destructive/20"
                : "bg-primary text-primary-foreground ring-8 ring-primary/15 hover:bg-primary/90")
            }
          >
            {isProcessing ? (
              <>
                <Loader2 className="h-14 w-14 animate-spin" />
                <span className="text-sm">{status === "transcribing" ? "Transcrevendo…" : "Estruturando…"}</span>
              </>
            ) : isRecording ? (
              <>
                <Square className="h-14 w-14 fill-current" />
                <span>Finalizar consulta</span>
              </>
            ) : isDone ? (
              <>
                <Play className="h-14 w-14 fill-current" />
                <span>Nova consulta</span>
              </>
            ) : (
              <>
                <Play className="h-14 w-14 fill-current" />
                <span>Iniciar consulta</span>
              </>
            )}
          </button>

          <div className="mt-6 min-h-[2.5rem] text-center text-sm">
            {status === "idle" && <p className="text-muted-foreground">Toque para iniciar a gravação</p>}
            {isProcessing && <p className="text-muted-foreground">{status === "transcribing" ? "Transcrevendo áudio…" : "Estruturando anamnese…"}</p>}
            {isDone && <p className="font-medium text-foreground">Anamnese pronta</p>}
          </div>
        </section>

        {isDone && (
          <section className="mt-6 px-5 pb-10">
            <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">Anamnese</h3>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-700">{ANAMNESE_MOCK}</pre>
            </div>
          </section>
        )}
      </div>

      {/* ============ DESKTOP LAYOUT ============ */}
      <header className="hidden h-14 items-center justify-between bg-primary px-6 text-primary-foreground md:flex">
        <div className="flex items-center gap-8">
          <span className="text-lg font-semibold tracking-tight">
            ◆ Prontuário <span className="ml-2 rounded bg-primary-foreground/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">Demo</span>
          </span>
          <nav className="hidden items-center gap-6 text-sm md:flex">
            <span className="cursor-pointer opacity-90 transition-opacity hover:opacity-100">Painel</span>
            <span className="cursor-pointer opacity-90 transition-opacity hover:opacity-100">Agenda</span>
            <span className="cursor-pointer opacity-90 transition-opacity hover:opacity-100">Pacientes</span>
            <span className="flex cursor-pointer items-center gap-1 opacity-90 transition-opacity hover:opacity-100">
              Gestão <ChevronDown className="h-3 w-3" />
            </span>
            <span className="cursor-pointer opacity-90 transition-opacity hover:opacity-100">Marketing</span>
            <span className="flex cursor-pointer items-center gap-1 opacity-90 transition-opacity hover:opacity-100">
              Outros <ChevronDown className="h-3 w-3" />
            </span>
          </nav>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-foreground/20 text-xs font-semibold">DR</div>
      </header>

      <div className="hidden md:flex">
        {/* Sidebar */}
        <aside className="min-h-[calc(100vh-3.5rem)] w-72 border-r border-border bg-card">
          <div className="border-b border-border px-6 py-5">
            <h2 className="text-lg font-semibold text-foreground">Prontuários</h2>
          </div>

          <div className="space-y-5 px-6 py-6">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Duração da consulta</span>
                <button className="text-xs text-primary hover:underline">Ocultar</button>
              </div>
              <div className="flex items-center gap-3 rounded-xl border border-border bg-slate-50 px-4 py-3">
                <Clock className="h-5 w-5 text-primary" />
                <span className="font-mono text-2xl tabular-nums text-slate-800">{formatTime(elapsed)}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleClick}
              disabled={isProcessing}
              className={
                "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 " +
                (isRecording
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : "bg-primary text-primary-foreground hover:bg-primary/90")
              }
            >
              {isProcessing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {status === "transcribing" ? "Transcrevendo…" : "Estruturando…"}
                </>
              ) : isRecording ? (
                <>
                  <Square className="h-4 w-4 fill-current" />
                  Finalizar consulta
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" />
                  {isDone ? "Nova consulta" : "Iniciar consulta"}
                </>
              )}
            </button>

            {isRecording && (
              <div className="flex items-center justify-center gap-2 text-xs font-medium text-destructive">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-destructive" />
                Gravando áudio…
              </div>
            )}

            {isProcessing && (
              <div className="flex items-center justify-center gap-2 text-xs font-medium text-primary">
                <Loader2 className="h-3 w-3 animate-spin" />
                {status === "transcribing" ? "Transcrevendo áudio…" : "Estruturando anamnese…"}
              </div>
            )}
          </div>

          <nav className="border-t border-border">
            <div className="border-l-2 border-primary bg-muted/30 px-6 py-3 text-sm font-medium text-primary">Resumo</div>
          </nav>
        </aside>

        {/* Main */}
        <section className="flex-1 space-y-8 p-8">
          <h1 className="text-2xl font-semibold text-slate-800">Resumo</h1>

          {/* Patient card */}
          <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
            <div className="flex flex-wrap items-start gap-6">
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-primary text-xl font-semibold text-primary-foreground">
                {PACIENTE.iniciais}
              </div>

              <div className="flex-1 space-y-2">
                <h2 className="text-3xl font-semibold leading-tight text-slate-800">{PACIENTE.nome}</h2>
                <p className="text-sm leading-relaxed">
                  <span className="text-slate-500">Idade:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.idade}</span>
                </p>
                <p className="text-sm leading-relaxed">
                  <span className="text-slate-500">Primeira consulta em:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.primeiraConsulta}</span>
                </p>
                <p className="text-sm leading-relaxed">
                  <span className="text-slate-500">Convênio:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.convenio}</span>
                </p>
                <p className="text-sm leading-relaxed">
                  <span className="text-slate-500">Nascimento:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.nascimento}</span>
                </p>
              </div>

              <div className="space-y-2 text-sm leading-relaxed">
                <p>
                  <span className="text-slate-500">Atendimentos:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.atendimentos}</span>
                </p>
                <p>
                  <span className="text-slate-500">Faltas:</span>{" "}
                  <span className="font-medium text-slate-800">{PACIENTE.faltas}</span>
                </p>
              </div>

              <button className="rounded-lg border border-border bg-card px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-700 transition-colors hover:bg-slate-100">
                Visualizar cadastro
              </button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-500">Filtrar:</span>
              <button className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-slate-700 transition-colors hover:bg-slate-100">
                Todos <ChevronDown className="h-3 w-3" />
              </button>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <button className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
                <Share2 className="h-4 w-4" /> Compartilhar
              </button>
              <button className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
                <Printer className="h-4 w-4" /> Imprimir
              </button>
            </div>
          </div>

          {/* Timeline */}
          <div className="flex gap-4">
            <div className="flex w-16 shrink-0 flex-col items-center overflow-hidden rounded-xl border border-border bg-card text-slate-600 shadow-sm">
              <span className="w-full bg-primary/10 py-1 text-center text-2xl font-bold leading-none text-primary">{dia}</span>
              <span className="py-1 text-[10px] font-semibold tracking-widest text-slate-500">{mes}</span>
              <span className="pb-2 text-xs text-slate-500">{ano}</span>
            </div>

            <div className="flex-1 rounded-xl border border-border bg-card shadow-sm">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div className="flex items-center gap-2 text-sm text-slate-800">
                  <span>Por: Dr. José Rodrigues</span>
                  <Lock className="h-3 w-3 text-slate-400" />
                </div>
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  <Clock className="h-3 w-3" />
                  {horaAgora}
                </div>
              </div>

              <div className="space-y-3 px-5 py-4">
                <p className="text-base font-semibold text-slate-800">Consulta por áudio</p>
                <p className={"text-sm " + timelineMensagem.tone}>{timelineMensagem.text}</p>
                {isRecording && (
                  <p className="font-mono text-xs text-slate-500">Tempo decorrido: {formatTime(elapsed)}</p>
                )}
                {isDone && (
                  <div className="mt-4 rounded-lg border border-border bg-slate-50 p-4">
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary">Anamnese</h4>
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-700">{ANAMNESE_MOCK}</pre>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
                <button className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
                  <Plus className="h-3 w-3" /> Inserir informações
                </button>
                <button className="flex items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
                  <Printer className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
