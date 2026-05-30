import { useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import {
  Clock,
  Play,
  Square,
  Lock,
  Printer,
  Share2,
  Plus,
  ChevronDown,
} from "lucide-react";
import { enviarConsulta } from "@/lib/consulta.functions";

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

type Status =
  | "idle"
  | "recording"
  | "sending"
  | "success"
  | "error"
  | "permission-denied";

function formatTime(totalSeconds: number) {
  const h = Math.floor(totalSeconds / 3600)
    .toString()
    .padStart(2, "0");
  const m = Math.floor((totalSeconds % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const s = (totalSeconds % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] ?? "";
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export function ConsultaPage() {
  const enviar = useServerFn(enviarConsulta);
  const [status, setStatus] = useState<Status>("idle");
  const [elapsed, setElapsed] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTimer = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopTimer();
      stopStream();
    };
  }, []);

  const handleIniciar = async () => {
    setElapsed(0);
    chunksRef.current = [];

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.error("Permissão de microfone negada:", err);
      setStatus("permission-denied");
      return;
    }

    streamRef.current = stream;

    const recorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
    });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      stopTimer();
      stopStream();

      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      chunksRef.current = [];

      setStatus("sending");
      try {
        const audioBase64 = await blobToBase64(blob);
        const result = await enviar({ data: { audioBase64 } });
        if (result.success) {
          setStatus("success");
        } else {
          setStatus("error");
        }
      } catch (err) {
        console.error("Falha ao enviar consulta:", err);
        setStatus("error");
      }
    };

    recorder.start();
    setStatus("recording");

    intervalRef.current = setInterval(() => {
      setElapsed((s) => s + 1);
    }, 1000);
  };

  const handleFinalizar = () => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  };

  const isRecording = status === "recording";
  const isSending = status === "sending";

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
      mes: hoje
        .toLocaleString("pt-BR", { month: "short" })
        .replace(".", "")
        .toUpperCase(),
      ano: String(hoje.getFullYear()),
      horaAgora: hoje.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    });
  }, []);
  const { dia, mes, ano, horaAgora } = agora;

  const timelineMensagem = (() => {
    switch (status) {
      case "success":
        return {
          tone: "text-foreground",
          text: "Consulta enviada com sucesso ao prontuário.",
        };
      case "error":
        return {
          tone: "text-destructive",
          text: "Não foi possível enviar a gravação, tente novamente.",
        };
      case "permission-denied":
        return {
          tone: "text-destructive",
          text:
            "Permissão de microfone negada. Habilite o microfone para gravar a consulta.",
        };
      case "recording":
        return {
          tone: "text-muted-foreground italic",
          text: "Gravação em andamento…",
        };
      case "sending":
        return {
          tone: "text-muted-foreground italic",
          text: "Enviando gravação ao prontuário…",
        };
      default:
        return {
          tone: "text-muted-foreground italic",
          text: "Nenhum atendimento registrado nesta sessão.",
        };
    }
  })();

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ============ MOBILE LAYOUT ============ */}
      <div className="flex min-h-screen flex-col md:hidden">
        <header className="flex h-12 items-center justify-center bg-primary px-5 text-primary-foreground">
          <span className="text-base font-semibold tracking-tight">
            ◆ Prontuário
          </span>
        </header>

        <section className="flex flex-col items-center gap-3 border-b border-border bg-card px-5 py-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
            {PACIENTE.iniciais}
          </div>
          <h1 className="text-3xl font-bold leading-tight text-slate-800">
            {PACIENTE.nome}
          </h1>
          <p className="text-sm leading-relaxed text-slate-500">
            <span className="text-slate-500">Nascimento:</span>{" "}
            <span className="font-medium text-slate-800">
              {PACIENTE.nascimento}
            </span>
          </p>
        </section>

        <section className="px-5 pt-8 text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Duração da consulta
          </p>
          <p className="mt-1 font-mono text-5xl font-semibold tabular-nums text-foreground">
            {formatTime(elapsed)}
          </p>
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
            onClick={isRecording ? handleFinalizar : handleIniciar}
            disabled={isSending}
            className={
              "flex h-48 w-48 flex-col items-center justify-center gap-2 rounded-full text-base font-semibold shadow-lg transition-colors active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 " +
              (isRecording
                ? "bg-destructive text-destructive-foreground ring-8 ring-destructive/20"
                : "bg-primary text-primary-foreground ring-8 ring-primary/15 hover:bg-primary/90")
            }
          >
            {isSending ? (
              <span className="text-lg">Enviando...</span>
            ) : isRecording ? (
              <>
                <Square className="h-14 w-14 fill-current" />
                <span>Finalizar consulta</span>
              </>
            ) : (
              <>
                <Play className="h-14 w-14 fill-current" />
                <span>Iniciar consulta</span>
              </>
            )}
          </button>

          <div className="mt-6 min-h-[2.5rem] text-center text-sm">
            {status === "success" && (
              <p className="font-medium text-foreground">
                Consulta enviada com sucesso
              </p>
            )}
            {status === "error" && (
              <p className="font-medium text-destructive">
                Não foi possível enviar a gravação, tente novamente
              </p>
            )}
            {status === "permission-denied" && (
              <p className="font-medium text-destructive">
                Permissão de microfone negada. Habilite o microfone para gravar
                a consulta.
              </p>
            )}
            {status === "idle" && (
              <p className="text-muted-foreground">
                Toque para iniciar a gravação
              </p>
            )}
          </div>
        </section>
      </div>

      {/* ============ DESKTOP LAYOUT ============ */}
      <header className="hidden h-14 items-center justify-between bg-primary px-6 text-primary-foreground md:flex">
        <div className="flex items-center gap-8">
          <span className="text-lg font-semibold tracking-tight">
            ◆ Prontuário
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
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-foreground/20 text-xs font-semibold">
          DR
        </div>
      </header>

      <div className="hidden md:flex">
        {/* Sidebar */}
        <aside className="min-h-[calc(100vh-3.5rem)] w-72 border-r border-border bg-card">
          <div className="border-b border-border px-6 py-5">
            <h2 className="text-lg font-semibold text-foreground">
              Prontuários
            </h2>
          </div>

          <div className="space-y-5 px-6 py-6">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  Duração da consulta
                </span>
                <button className="text-xs text-primary hover:underline">
                  Ocultar
                </button>
              </div>
              <div className="flex items-center gap-3 rounded-xl border border-border bg-slate-50 px-4 py-3">
                <Clock className="h-5 w-5 text-primary" />
                <span className="font-mono text-2xl tabular-nums text-slate-800">
                  {formatTime(elapsed)}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={isRecording ? handleFinalizar : handleIniciar}
              disabled={isSending}
              className={
                "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 " +
                (isRecording
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : "bg-primary text-primary-foreground hover:bg-primary/90")
              }
            >
              {isSending ? (
                "Enviando..."
              ) : isRecording ? (
                <>
                  <Square className="h-4 w-4 fill-current" />
                  Finalizar consulta
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" />
                  Iniciar consulta
                </>
              )}
            </button>

            {isRecording && (
              <div className="flex items-center justify-center gap-2 text-xs font-medium text-destructive">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-destructive" />
                Gravando áudio…
              </div>
            )}

            {status === "permission-denied" && (
              <p className="text-xs text-destructive">
                Permissão de microfone negada. Habilite o microfone para gravar.
              </p>
            )}
          </div>

          <nav className="border-t border-border">
            <div className="border-l-2 border-primary bg-muted/30 px-6 py-3 text-sm font-medium text-primary">
              Resumo
            </div>
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
                <h2 className="text-3xl font-semibold leading-tight text-slate-800">
                  {PACIENTE.nome}
                </h2>
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
              <span className="w-full bg-primary/10 py-1 text-center text-2xl font-bold leading-none text-primary">
                {dia}
              </span>
              <span className="py-1 text-[10px] font-semibold tracking-widest text-slate-500">
                {mes}
              </span>
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
                <p className="text-base font-semibold text-slate-800">
                  Consulta por áudio
                </p>
                <p className={"text-sm " + timelineMensagem.tone}>
                  {timelineMensagem.text}
                </p>
                {status === "recording" && (
                  <p className="font-mono text-xs text-slate-500">
                    Tempo decorrido: {formatTime(elapsed)}
                  </p>
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
