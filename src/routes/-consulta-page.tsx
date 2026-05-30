import { useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { enviarConsulta } from "@/lib/consulta.functions";

const PACIENTE = {
  nome: "Pedro Henrique Alves",
  nascimento: "15/05/2002",
};

type Status =
  | "idle"
  | "recording"
  | "sending"
  | "success"
  | "error"
  | "permission-denied";

function formatTime(totalSeconds: number) {
  const m = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const s = (totalSeconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
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

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-10 shadow-sm">
        <header className="text-center">
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            {PACIENTE.nome}
          </h1>
          <p className="mt-3 text-lg text-muted-foreground">
            Nascimento: {PACIENTE.nascimento}
          </p>
        </header>

        <div className="mt-10 flex flex-col items-center gap-6">
          {isRecording && (
            <div className="flex items-center gap-3 text-destructive">
              <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-destructive" />
              <span className="font-mono text-xl tabular-nums">
                {formatTime(elapsed)}
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={isRecording ? handleFinalizar : handleIniciar}
            disabled={isSending}
            className={
              isRecording
                ? "w-full rounded-xl bg-destructive px-8 py-5 text-lg font-semibold text-destructive-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                : "w-full rounded-xl bg-primary px-8 py-5 text-lg font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            }
          >
            {isSending
              ? "Enviando..."
              : isRecording
              ? "Finalizar consulta"
              : "Iniciar consulta"}
          </button>

          {status === "success" && (
            <p className="text-center text-sm font-medium text-foreground">
              Consulta enviada com sucesso
            </p>
          )}
          {status === "error" && (
            <p className="text-center text-sm font-medium text-destructive">
              Não foi possível enviar a gravação, tente novamente
            </p>
          )}
          {status === "permission-denied" && (
            <p className="text-center text-sm font-medium text-destructive">
              Permissão de microfone negada. Habilite o microfone para gravar a
              consulta.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
