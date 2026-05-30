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
    <div className="min-h-screen bg-muted/40">
      {/* ============ MOBILE LAYOUT ============ */}
      <div className="flex min-h-screen flex-col md:hidden">
        <header className="flex h-12 items-center justify-center bg-primary px-5 text-primary-foreground">
          <span className="text-base font-semibold tracking-tight">
            ◆ Prontuário
          </span>
        </header>

        <section className="flex flex-col items-center gap-2 border-b border-border bg-card px-5 py-6 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary">
            {PACIENTE.iniciais}
          </div>
          <h1 className="text-3xl font-bold leading-tight text-primary">
            {PACIENTE.nome}
          </h1>
          <p className="text-sm text-muted-foreground">
            Nascimento: {PACIENTE.nascimento}
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
              "flex h-48 w-48 flex-col items-center justify-center gap-2 rounded-full text-base font-semibold shadow-lg transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 " +
              (isRecording
                ? "bg-destructive text-destructive-foreground ring-8 ring-destructive/20"
                : "bg-primary text-primary-foreground ring-8 ring-primary/15")
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
            <span className="opacity-90 hover:opacity-100">Painel</span>
            <span className="opacity-90 hover:opacity-100">Agenda</span>
            <span className="opacity-90 hover:opacity-100">Pacientes</span>
            <span className="flex items-center gap-1 opacity-90 hover:opacity-100">
              Gestão <ChevronDown className="h-3 w-3" />
            </span>
            <span className="opacity-90 hover:opacity-100">Marketing</span>
            <span className="flex items-center gap-1 opacity-90 hover:opacity-100">
              Outros <ChevronDown className="h-3 w-3" />
            </span>
          </nav>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-foreground/20 text-xs font-semibold">
          DR
        </div>
      </header>

      <div className="flex">
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
              <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-4 py-3">
                <Clock className="h-5 w-5 text-muted-foreground" />
                <span className="font-mono text-2xl tabular-nums text-foreground">
                  {formatTime(elapsed)}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={isRecording ? handleFinalizar : handleIniciar}
              disabled={isSending}
              className={
                "flex w-full items-center justify-center gap-2 rounded-md px-4 py-3 text-sm font-semibold transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 " +
                (isRecording
                  ? "bg-destructive text-destructive-foreground"
                  : "bg-primary text-primary-foreground")
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
        <section className="flex-1 space-y-6 p-8">
          <h1 className="text-2xl font-semibold text-foreground">Resumo</h1>

          {/* Patient card */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="flex flex-wrap items-start gap-6">
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xl font-semibold text-primary">
                {PACIENTE.iniciais}
              </div>

              <div className="flex-1 space-y-1">
                <h2 className="text-2xl font-semibold text-primary">
                  {PACIENTE.nome}
                </h2>
                <p className="text-sm text-muted-foreground">
                  Idade: {PACIENTE.idade}
                </p>
                <p className="text-sm text-muted-foreground">
                  Primeira consulta em: {PACIENTE.primeiraConsulta}
                </p>
                <p className="text-sm text-muted-foreground">
                  Convênio: {PACIENTE.convenio}
                </p>
                <p className="text-sm text-muted-foreground">
                  Nascimento: {PACIENTE.nascimento}
                </p>
              </div>

              <div className="space-y-1 text-sm text-muted-foreground">
                <p>Atendimentos: {PACIENTE.atendimentos}</p>
                <p>Faltas: {PACIENTE.faltas}</p>
              </div>

              <button className="rounded-md bg-primary px-4 py-2 text-xs font-semibold uppercase tracking-wide text-primary-foreground transition-opacity hover:opacity-90">
                Visualizar cadastro
              </button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Filtrar:</span>
              <button className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-foreground">
                Todos <ChevronDown className="h-3 w-3" />
              </button>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <button className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-muted-foreground hover:text-foreground">
                <Share2 className="h-4 w-4" /> Compartilhar
              </button>
              <button className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-muted-foreground hover:text-foreground">
                <Printer className="h-4 w-4" /> Imprimir
              </button>
            </div>
          </div>

          {/* Timeline */}
          <div className="flex gap-4">
            <div className="flex w-16 shrink-0 flex-col items-center overflow-hidden rounded-md border border-primary/30 bg-primary/10 text-primary">
              <span className="w-full bg-primary/20 py-1 text-center text-2xl font-bold leading-none">
                {dia}
              </span>
              <span className="py-1 text-[10px] font-semibold tracking-widest">
                {mes}
              </span>
              <span className="pb-2 text-xs">{ano}</span>
            </div>

            <div className="flex-1 rounded-lg border border-border bg-card shadow-sm">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div className="flex items-center gap-2 text-sm text-foreground">
                  <span>Por: Dr. José Rodrigues</span>
                  <Lock className="h-3 w-3 text-muted-foreground" />
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {horaAgora}
                </div>
              </div>

              <div className="space-y-3 px-5 py-4">
                <p className="text-sm font-medium text-primary">
                  Consulta por áudio
                </p>
                <p className={"text-sm " + timelineMensagem.tone}>
                  {timelineMensagem.text}
                </p>
                {status === "recording" && (
                  <p className="font-mono text-xs text-muted-foreground">
                    Tempo decorrido: {formatTime(elapsed)}
                  </p>
                )}
              </div>

              <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
                <button className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                  <Plus className="h-3 w-3" /> Inserir informações
                </button>
                <button className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-muted-foreground hover:text-foreground">
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
