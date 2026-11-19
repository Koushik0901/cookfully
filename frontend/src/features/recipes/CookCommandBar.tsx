import { useMutation } from "@tanstack/react-query";
import { Mic } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { recipesApi } from "./api";
import type { CookCommand } from "./types";

type Intent = Exclude<CookCommand["intent"], "none">;

const ASK_DURATION = "For how long? Say, for example, “timer 10 minutes”.";

const LABELS: Record<Intent, string> = {
  next: "Next step",
  previous: "Previous step",
  repeat: "Read this step again",
  timer: "Start a timer",
  ingredient: "Check the ingredients",
};

// The Web Speech API is not in the TypeScript DOM lib; only what is used here is declared.
type Recognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
};
type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export type CookCommandActions = {
  next: () => string;
  previous: () => string;
  repeat: () => string;
  ingredient: () => string;
  timer: (minutes: number) => string;
};

/**
 * Type or say a command ("next", "set a timer for ten minutes"). A decision-model panel picks the
 * intent; when it is unsure the cook is asked which they meant, and when it cannot answer the manual
 * buttons around it are unchanged.
 */
export function CookCommandBar({ recipeId, step, actions }: { recipeId: string; step: number; actions: CookCommandActions }) {
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");
  const [options, setOptions] = useState<CookCommand["alternatives"]>([]);
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const Speech = recognitionConstructor();

  function perform(intent: Intent, minutes: number | null | undefined): string {
    if (intent === "timer") return minutes ? actions.timer(minutes) : ASK_DURATION;
    return actions[intent]();
  }

  const interpret = useMutation({
    mutationFn: (utterance: string) => recipesApi.cookCommand(recipeId, utterance, step),
    onMutate: () => {
      setMessage("");
      setOptions([]);
    },
    onSuccess: (result) => {
      if (result.intent === "none") {
        setMessage("I didn’t catch a command. Use the buttons, or try “next”, “repeat” or “timer 10 minutes”.");
        return;
      }
      if (result.act) {
        setMessage(perform(result.intent, result.minutes));
        setText("");
        return;
      }
      setOptions(result.alternatives);
      setMessage(result.intent === "timer" && !result.minutes ? ASK_DURATION : "Did you mean:");
    },
    onError: () => setMessage("Voice commands are unavailable right now. The buttons still work."),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const utterance = text.trim();
    if (utterance && !interpret.isPending) interpret.mutate(utterance);
  }

  function listen() {
    if (!Speech) return;
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const session = new Speech();
    session.lang = typeof navigator === "undefined" ? "en-US" : navigator.language || "en-US";
    session.interimResults = false;
    session.maxAlternatives = 1;
    session.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) {
        setText(transcript);
        interpret.mutate(transcript);
      }
    };
    session.onend = () => setListening(false);
    session.onerror = () => {
      setListening(false);
      setMessage("I couldn’t hear that. Type the command instead.");
    };
    recognition.current = session;
    setListening(true);
    session.start();
  }

  return (
    <form className="cook-command" onSubmit={submit} aria-label="Voice commands">
      <input
        type="text"
        value={text}
        maxLength={400}
        aria-label="Say or type a command"
        placeholder="Say or type a command"
        onChange={(event) => setText(event.target.value)}
      />
      {Speech ? (
        <button type="button" className="cook-command__mic" aria-pressed={listening} aria-label={listening ? "Stop listening" : "Speak a command"} onClick={listen}>
          <Mic aria-hidden="true" />
        </button>
      ) : null}
      <button type="submit" disabled={!text.trim() || interpret.isPending}>
        {interpret.isPending ? "Working…" : "Go"}
      </button>
      <div aria-live="polite" aria-atomic="true" className="cook-command__status">
        {message}
        {options.map((option) => (
          <button
            key={option.intent}
            type="button"
            onClick={() => {
              setOptions([]);
              setMessage(perform(option.intent, interpret.data?.minutes));
            }}
          >
            {LABELS[option.intent]}
          </button>
        ))}
      </div>
    </form>
  );
}
