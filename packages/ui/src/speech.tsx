"use client";

import * as React from "react";

import { Icon } from "./icons";
import { locale, numbers } from "./regional";
import { say } from "./words";

const CHUNK = 220;
const RATES = [1, 1.15, 1.3, 1.5, 0.9];
const RATE_KEY = "arga.speech.rate";

export interface Chunk {
  text: string;
  part: number;
}

export function chunksOf(parts: string[], limit = CHUNK): Chunk[] {
  const out: Chunk[] = [];
  parts.forEach((raw, part) => {
    const text = raw.replace(/\s+/g, " ").trim();
    if (!text) return;
    const sentences = text.match(/[^.!?…;:]+[.!?…;:]*["»”)]?\s*/g) ?? [text];
    let current = "";
    for (const sentence of sentences) {
      if (current && (current + sentence).length > limit) {
        out.push({ text: current.trim(), part });
        current = "";
      }
      if (sentence.length > limit) {
        const words = sentence.split(" ");
        for (const word of words) {
          if (current && (current + " " + word).length > limit) {
            out.push({ text: current.trim(), part });
            current = "";
          }
          current += (current ? " " : "") + word;
        }
      } else {
        current += sentence;
      }
    }
    if (current.trim()) out.push({ text: current.trim(), part });
  });
  return out;
}

const PREFERRED = /premium|enhanced|mejorad|natural|neural|siri|mónica|monica|google/i;

export function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  const base = lang.toLowerCase().split("-")[0]!;
  const country = base === "es" ? "es-es" : base === "en" ? "en-gb" : base === "de" ? "de-de" : base === "fr" ? "fr-fr" : `${base}-${base}`;
  const mine = voices.filter((voice) => voice.lang.toLowerCase().replace("_", "-").startsWith(base));
  if (mine.length === 0) return null;
  const score = (voice: SpeechSynthesisVoice) =>
    (voice.lang.toLowerCase().replace("_", "-") === country ? 4 : 0) + (PREFERRED.test(voice.name) ? 2 : 0) + (voice.localService ? 1 : 0);
  return [...mine].sort((a, b) => score(b) - score(a))[0] ?? null;
}

export function listeningMinutes(chunks: Chunk[], rate = 1): number {
  const words = chunks.reduce((sum, chunk) => sum + chunk.text.split(/\s+/).filter(Boolean).length, 0);
  return Math.max(1, Math.round(words / (160 * rate)));
}

type SpeechState = "idle" | "playing" | "paused";

export interface Player {
  supported: boolean;
  state: SpeechState;
  part: number | null;
  progress: number;
  rate: number;
  minutes: number;
  play: () => void;
  pause: () => void;
  stop: () => void;
  skip: (step: number) => void;
  faster: () => void;
}

function storedRate(): number {
  try {
    const value = Number(window.localStorage.getItem(RATE_KEY));
    return RATES.includes(value) ? value : 1;
  } catch {
    return 1;
  }
}

function storeRate(rate: number) {
  try {
    window.localStorage.setItem(RATE_KEY, String(rate));
  } catch {
  }
}

const nextRate = (rate: number) => RATES[(RATES.indexOf(rate) + 1) % RATES.length]!;

function useSpeakingMark(state: SpeechState) {
  React.useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (state === "idle") root.removeAttribute("data-speaking");
    else root.dataset.speaking = state;
  }, [state]);
  React.useEffect(
    () => () => {
      if (typeof document !== "undefined") document.documentElement.removeAttribute("data-speaking");
    },
    [],
  );
}

interface Sentinel {
  release: () => Promise<void>;
}

export function useWakeLock(on: boolean) {
  const held = React.useRef<Sentinel | null>(null);
  React.useEffect(() => {
    if (typeof navigator === "undefined") return;
    const lock = (navigator as Navigator & { wakeLock?: { request: (type: "screen") => Promise<Sentinel> } }).wakeLock;
    if (!lock) return;
    let live = true;
    const take = () => {
      if (!on || held.current || document.visibilityState !== "visible") return;
      void lock
        .request("screen")
        .then((sentinel) => {
          if (live && on) held.current = sentinel;
          else void sentinel.release();
        })
        .catch(() => undefined);
    };
    const back = () => {
      held.current = null;
      take();
    };
    take();
    document.addEventListener("visibilitychange", back);
    return () => {
      live = false;
      document.removeEventListener("visibilitychange", back);
      void held.current?.release().catch(() => undefined);
      held.current = null;
    };
  }, [on]);
}

export function useSpeech(parts: string[], lang: string): Player {
  const synth = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
  const supported = Boolean(synth) && typeof SpeechSynthesisUtterance !== "undefined";
  const chunks = React.useMemo(() => chunksOf(parts), [parts]);
  const [state, setState] = React.useState<SpeechState>("idle");
  const [index, setIndex] = React.useState(0);
  const [rate, setRate] = React.useState(1);
  const [voices, setVoices] = React.useState<SpeechSynthesisVoice[]>([]);
  const token = React.useRef(0);
  const live = React.useRef({ index: 0, rate: 1 });

  React.useEffect(() => {
    setRate(storedRate());
  }, []);

  React.useEffect(() => {
    if (!synth) return;
    const load = () => setVoices(synth.getVoices());
    load();
    synth.addEventListener?.("voiceschanged", load);
    return () => synth.removeEventListener?.("voiceschanged", load);
  }, [synth]);

  React.useEffect(
    () => () => {
      token.current += 1;
      synth?.cancel();
    },
    [synth],
  );

  const speak = React.useCallback(
    (at: number, speed: number) => {
      if (!synth || at >= chunks.length) {
        setState("idle");
        setIndex(0);
        return;
      }
      const mine = ++token.current;
      synth.cancel();
      const utterance = new SpeechSynthesisUtterance(chunks[at]!.text);
      utterance.lang = lang;
      const voice = pickVoice(voices, lang);
      if (voice) utterance.voice = voice;
      utterance.rate = speed;
      utterance.onend = () => {
        if (token.current !== mine) return;
        const next = at + 1;
        live.current.index = next;
        setIndex(next);
        if (next < chunks.length) speak(next, live.current.rate);
        else {
          setState("idle");
          setIndex(0);
          live.current.index = 0;
        }
      };
      utterance.onerror = (event) => {
        if (token.current !== mine) return;
        if (event.error === "interrupted" || event.error === "canceled") return;
        setState("idle");
      };
      live.current = { index: at, rate: speed };
      setIndex(at);
      setState("playing");
      synth.speak(utterance);
    },
    [synth, chunks, lang, voices],
  );

  return {
    supported: supported && chunks.length > 0,
    state,
    part: state === "idle" ? null : (chunks[index]?.part ?? null),
    progress: chunks.length ? (index / chunks.length) * 100 : 0,
    rate,
    minutes: listeningMinutes(chunks, rate),
    play: () => speak(state === "idle" ? 0 : live.current.index, rate),
    pause: () => {
      token.current += 1;
      synth?.cancel();
      setState("paused");
    },
    stop: () => {
      token.current += 1;
      synth?.cancel();
      live.current.index = 0;
      setIndex(0);
      setState("idle");
    },
    skip: (step: number) => {
      const at = Math.min(Math.max(0, live.current.index + step), chunks.length - 1);
      if (state === "playing") speak(at, rate);
      else {
        live.current.index = at;
        setIndex(at);
      }
    },
    faster: () => {
      const next = nextRate(rate);
      setRate(next);
      storeRate(next);
      if (state === "playing") speak(live.current.index, next);
    },
  };
}

export interface SpokenAudio {
  src: string;
  duration: number;
  timeline: number[];
}

export function partAt(timeline: number[], seconds: number): number {
  let part = 0;
  for (let index = 0; index < timeline.length; index += 1) if (timeline[index]! <= seconds + 0.05) part = index;
  return part;
}

export function useAudioPlayer(
  audio: SpokenAudio | null,
  element: React.RefObject<HTMLAudioElement | null>,
  meta: { title: string; artist: string; artwork?: string },
): Player {
  const [state, setState] = React.useState<SpeechState>("idle");
  const [seconds, setSeconds] = React.useState(0);
  const [rate, setRate] = React.useState(1);

  React.useEffect(() => {
    setRate(storedRate());
  }, []);

  React.useEffect(() => {
    const el = element.current;
    if (!el || !audio) return;
    const onPlay = () => setState("playing");
    const onPause = () => setState((now) => (now === "idle" ? "idle" : el.ended ? "idle" : "paused"));
    const onTime = () => {
      setSeconds(el.currentTime);
      const session = typeof navigator !== "undefined" ? navigator.mediaSession : undefined;
      if (session?.setPositionState && Number.isFinite(el.duration) && el.duration > 0) {
        try {
          session.setPositionState({ duration: el.duration, position: Math.min(el.currentTime, el.duration), playbackRate: el.playbackRate });
        } catch {
        }
      }
    };
    const onEnd = () => {
      setState("idle");
      setSeconds(0);
    };
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("ended", onEnd);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("ended", onEnd);
    };
  }, [audio, element]);

  React.useEffect(() => {
    if (element.current) element.current.playbackRate = rate;
  }, [rate, element]);

  const seek = React.useCallback(
    (to: number) => {
      const el = element.current;
      if (!el || !audio) return;
      el.currentTime = Math.min(Math.max(0, to), Math.max(0, audio.duration - 0.5));
      setSeconds(el.currentTime);
    },
    [audio, element],
  );

  const toPart = React.useCallback(
    (step: number) => {
      if (!audio) return;
      const el = element.current;
      const now = el ? el.currentTime : seconds;
      const current = partAt(audio.timeline, now);
      const target = step < 0 && now - (audio.timeline[current] ?? 0) > 3 ? current : current + step;
      const index = Math.min(Math.max(0, target), audio.timeline.length - 1);
      seek(audio.timeline[index] ?? 0);
    },
    [audio, element, seconds, seek],
  );

  const play = React.useCallback(() => {
    const el = element.current;
    if (!el) return;
    el.playbackRate = rate;
    setState("playing");
    void el.play().catch(() => setState("idle"));
  }, [element, rate]);
  const pause = React.useCallback(() => element.current?.pause(), [element]);
  const stop = React.useCallback(() => {
    const el = element.current;
    setState("idle");
    if (!el) return;
    el.pause();
    el.currentTime = 0;
    setSeconds(0);
  }, [element]);

  React.useEffect(() => {
    const session = typeof navigator !== "undefined" ? navigator.mediaSession : undefined;
    if (!session || !audio || state === "idle") return;
    try {
      session.metadata = new MediaMetadata({
        title: meta.title,
        artist: meta.artist,
        album: say("speech.album"),
        artwork: meta.artwork ? [{ src: meta.artwork, sizes: "512x512", type: "image/png" }] : [],
      });
    } catch {
    }
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => play()],
      ["pause", () => pause()],
      ["stop", () => stop()],
      ["previoustrack", () => toPart(-1)],
      ["nexttrack", () => toPart(1)],
      ["seekbackward", (details) => seek((element.current?.currentTime ?? 0) - (details.seekOffset ?? 15))],
      ["seekforward", (details) => seek((element.current?.currentTime ?? 0) + (details.seekOffset ?? 15))],
      ["seekto", (details) => details.seekTime !== undefined && seek(details.seekTime)],
    ];
    for (const [action, handler] of handlers) {
      try {
        session.setActionHandler(action, handler);
      } catch {
      }
    }
    session.playbackState = state === "playing" ? "playing" : "paused";
    return () => {
      for (const [action] of handlers) {
        try {
          session.setActionHandler(action, null);
        } catch {
        }
      }
    };
  }, [audio, state, meta.title, meta.artist, meta.artwork, play, pause, stop, toPart, seek, element]);

  return {
    supported: Boolean(audio),
    state,
    part: state === "idle" || !audio ? null : partAt(audio.timeline, seconds),
    progress: audio && audio.duration > 0 ? (seconds / audio.duration) * 100 : 0,
    rate,
    minutes: audio ? Math.max(1, Math.round(audio.duration / 60 / rate)) : 1,
    play,
    pause,
    stop,
    skip: toPart,
    faster: () => {
      const next = nextRate(rate);
      setRate(next);
      storeRate(next);
    },
  };
}

const speedLabel = (rate: number) => `${numbers({ maximumFractionDigits: 2 }).format(rate)}×`;

export function ReadAloud({
  parts,
  lang = locale(),
  title,
  onPart,
  audio = null,
  artist = "Insights",
  artwork,
}: {
  parts: string[];
  lang?: string;
  title: string;
  onPart?: (part: number | null) => void;
  audio?: SpokenAudio | null;
  artist?: string;
  artwork?: string;
}) {
  const element = React.useRef<HTMLAudioElement>(null);
  const [broken, setBroken] = React.useState(false);
  React.useEffect(() => setBroken(false), [audio?.src]);
  const usable = broken ? null : audio;
  const voice = useSpeech(parts, lang);
  const recorded = useAudioPlayer(usable, element, { title, artist, artwork });
  const speech = usable ? recorded : voice;
  useSpeakingMark(speech.state);
  useWakeLock(!usable && speech.state === "playing");
  const report = React.useRef(onPart);
  report.current = onPart;
  React.useEffect(() => {
    report.current?.(speech.part);
  }, [speech.part]);

  if (!speech.supported) return null;
  const active = speech.state !== "idle";
  return (
    <>
      {usable && <audio ref={element} src={usable.src} preload="none" onError={() => setBroken(true)} />}
      <button
        type="button"
        className="read-aloud"
        aria-pressed={speech.state === "playing"}
        onClick={speech.state === "playing" ? speech.pause : speech.play}
      >
        <Icon name={speech.state === "playing" ? "pause" : "headphones"} />
        {speech.state === "playing" ? say("speech.pause") : speech.state === "paused" ? say("speech.resume") : say("speech.listen")}
        <span className="read-aloud-time">{speech.minutes} min</span>
      </button>
      {active && (
        <div className="read-aloud-dock glass" role="region" aria-label={say("speech.player")}>
          <span className="read-aloud-progress" aria-hidden="true">
            <span style={{ "--done": `${speech.progress}%` } as React.CSSProperties} />
          </span>
          <span className="read-aloud-title">{title}</span>
          <span className="read-aloud-controls">
            <button type="button" className="read-aloud-button" aria-label={say("speech.back")} onClick={() => speech.skip(-1)}>
              <Icon name="undo" />
            </button>
            <button
              type="button"
              className="read-aloud-button"
              data-main=""
              aria-label={speech.state === "playing" ? say("speech.pause") : say("speech.continue")}
              onClick={speech.state === "playing" ? speech.pause : speech.play}
            >
              <Icon name={speech.state === "playing" ? "pause" : "play"} />
            </button>
            <button type="button" className="read-aloud-button" aria-label={say("speech.forward")} onClick={() => speech.skip(1)}>
              <Icon name="skip" />
            </button>
            <button type="button" className="read-aloud-speed" aria-label={say("speech.speed", { speed: speedLabel(speech.rate) })} onClick={speech.faster}>
              {speedLabel(speech.rate)}
            </button>
            <button type="button" className="read-aloud-button" aria-label={say("speech.stop")} onClick={speech.stop}>
              <Icon name="close" />
            </button>
          </span>
        </div>
      )}
    </>
  );
}
