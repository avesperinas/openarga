// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { ArticleReader, ReadAloud, chunksOf, listeningMinutes, pickVoice, spokenParts } from "../src/index";

class FakeUtterance {
  text: string;
  lang = "";
  rate = 1;
  voice: SpeechSynthesisVoice | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

class FakeSynth {
  spoken: FakeUtterance[] = [];
  cancelled = 0;
  voices: SpeechSynthesisVoice[] = [];
  speak(utterance: FakeUtterance) {
    this.spoken.push(utterance);
  }
  cancel() {
    this.cancelled += 1;
  }
  getVoices() {
    return this.voices;
  }
  addEventListener() {}
  removeEventListener() {}
  finish() {
    this.spoken.at(-1)?.onend?.();
  }
}

const voice = (name: string, lang: string, localService = true) => ({ name, lang, localService }) as SpeechSynthesisVoice;

let synth: FakeSynth;
let root: Root;
let host: HTMLElement;

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

beforeEach(() => {
  synth = new FakeSynth();
  Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  (globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = FakeUtterance;
  window.localStorage.clear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const button = (label: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find(
    (one) => one.textContent?.includes(label) || one.getAttribute("aria-label") === label,
  )!;

describe("splitting what is read", () => {
  it("in whole sentences of about 220 characters, remembering which part each piece comes from", () => {
    const long = "Una frase corta. ".repeat(30);
    const chunks = chunksOf(["Titular", long, ""]);
    expect(chunks[0]).toEqual({ text: "Titular", part: 0 });
    expect(chunks.slice(1).every((one) => one.part === 1 && one.text.length <= 220)).toBe(true);
    expect(chunks.slice(1).every((one) => one.text.endsWith("."))).toBe(true);
    expect(chunks.map((one) => one.text).join(" ")).toContain("Una frase corta.");
  });

  it("a sentence without full stops longer than a piece splits by words", () => {
    const chunks = chunksOf(["palabra ".repeat(80)]);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every((one) => one.text.length <= 220)).toBe(true);
  });

  it("minutes at 160 words per minute, and fewer at higher speed", () => {
    const chunks = chunksOf(["palabra ".repeat(320)]);
    expect(listeningMinutes(chunks)).toBe(2);
    expect(listeningMinutes(chunks, 2)).toBe(1);
  });

  it("what is heard of an article goes in reading order", () => {
    expect(
      spokenParts({
        headline: "Titular",
        lead: "Entradilla",
        sections: [{ title: "Ladillo", text: "Uno.\n\nDos." }],
        highlight: { label: "Para contar", text: "Dato." },
        coda: { label: "Para pensar:", text: "¿Y?" },
      }),
    ).toEqual(["Titular", "Entradilla", "Ladillo", "Uno.", "Dos.", "Para contar. Dato.", "Para pensar: ¿Y?"]);
  });
});

describe("the voice", () => {
  it("the locale's own country voice before another of the language, and a quality one before any", () => {
    const voices = [voice("Paulina", "es-MX"), voice("Jorge", "es-ES"), voice("Mónica (mejorada)", "es-ES"), voice("Anna", "de-DE")];
    expect(pickVoice(voices, "es-ES")?.name).toBe("Mónica (mejorada)");
    expect(pickVoice(voices, "de-DE")?.name).toBe("Anna");
    expect(pickVoice(voices, "fr-FR")).toBeNull();
  });
});

describe("escuchar", () => {
  it("without a voice in the browser, it does not show", () => {
    Object.defineProperty(window, "speechSynthesis", { value: undefined, configurable: true });
    delete (window as { speechSynthesis?: unknown }).speechSynthesis;
    expect(renderToStaticMarkup(<ReadAloud parts={["Hello"]} title="Something" />)).toBe("");
  });

  it("reads piece by piece, says where it is, pauses, resumes where it was and stops", () => {
    const parts: (number | null)[] = [];
    act(() => root.render(<ReadAloud parts={["First.", "Second.", "Third."]} title="A pill" onPart={(part) => parts.push(part)} />));
    expect(button("Listen").textContent).toContain("1 min");

    act(() => button("Listen").click());
    expect(synth.spoken.map((one) => one.text)).toEqual(["First."]);
    expect(synth.spoken[0]!.lang).toBe("en-GB");
    expect(document.documentElement.dataset.speaking).toBe("playing");
    expect(host.querySelector('[aria-label="Player"]')?.textContent).toContain("A pill");

    act(() => synth.finish());
    expect(synth.spoken.at(-1)!.text).toBe("Second.");

    act(() => button("Pause").click());
    expect(document.documentElement.dataset.speaking).toBe("paused");
    act(() => synth.finish());
    expect(synth.spoken.at(-1)!.text).toBe("Second.");

    act(() => button("Keep listening").click());
    expect(synth.spoken.at(-1)!.text).toBe("Second.");

    act(() => button("Stop").click());
    expect(document.documentElement.dataset.speaking).toBeUndefined();
    expect(host.querySelector('[aria-label="Player"]')).toBeNull();
    expect(parts).toContain(1);
    expect(parts.at(-1)).toBeNull();
  });

  it("the speed changes what plays and is remembered", () => {
    act(() => root.render(<ReadAloud parts={["First.", "Second."]} title="Something" />));
    act(() => button("Listen").click());
    act(() => button("Speed 1×").click());
    expect(synth.spoken.at(-1)!.rate).toBe(1.15);
    expect(window.localStorage.getItem("arga.speech.rate")).toBe("1.15");
  });

  it("when done, it goes back to the start", () => {
    act(() => root.render(<ReadAloud parts={["Only."]} title="Something" />));
    act(() => button("Listen").click());
    act(() => synth.finish());
    expect(document.documentElement.dataset.speaking).toBeUndefined();
    expect(button("Listen")).toBeTruthy();
  });

  it("the article highlights what is being read aloud", () => {
    act(() =>
      root.render(
        <ArticleReader headline="Titular" lead="Entradilla" sections={[{ title: "Ladillo", text: "Uno." }]} listen={{ lang: "de-DE" }} />,
      ),
    );
    act(() => button("Listen").click());
    expect(synth.spoken[0]!.lang).toBe("de-DE");
    expect(host.querySelector("h1")?.hasAttribute("data-speaking")).toBe(true);
    act(() => synth.finish());
    expect(host.querySelector(".article-reader-lead")?.hasAttribute("data-speaking")).toBe(true);
    expect(host.querySelector("h1")?.hasAttribute("data-speaking")).toBe(false);
  });
});

describe("so that it is not cut", () => {
  it("with the device voice, the screen stays on while it speaks", async () => {
    const taken: { released: boolean }[] = [];
    const wakeLock = {
      request: async () => {
        const sentinel = { released: false, release: async () => void (sentinel.released = true) };
        taken.push(sentinel);
        return sentinel;
      },
    };
    Object.defineProperty(navigator, "wakeLock", { value: wakeLock, configurable: true });
    act(() => root.render(<ReadAloud parts={["First.", "Second."]} title="Something" />));
    await act(async () => button("Listen").click());
    expect(taken).toHaveLength(1);
    expect(taken[0]!.released).toBe(false);
    await act(async () => button("Pause").click());
    expect(taken[0]!.released).toBe(true);
    delete (navigator as { wakeLock?: unknown }).wakeLock;
  });
});

describe("with real audio", () => {
  const audio = { src: "/insights/api/pills/p1/audio", duration: 90, timeline: [0, 4, 30] };
  let session: { metadata: unknown; playbackState: string; handlers: Map<string, unknown>; setActionHandler: (a: string, h: unknown) => void };

  beforeEach(() => {
    session = {
      metadata: null,
      playbackState: "none",
      handlers: new Map(),
      setActionHandler(action, handler) {
        if (handler) this.handlers.set(action, handler);
        else this.handlers.delete(action);
      },
    };
    Object.defineProperty(navigator, "mediaSession", { value: session, configurable: true });
    (globalThis as unknown as { MediaMetadata: unknown }).MediaMetadata = class {
      constructor(public init: { title: string; artist: string; album: string }) {}
    };
    HTMLMediaElement.prototype.play = function (this: HTMLMediaElement) {
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function (this: HTMLMediaElement) {
      this.dispatchEvent(new Event("pause"));
    };
  });

  afterEach(() => {
    delete (navigator as { mediaSession?: unknown }).mediaSession;
  });

  it("the audio plays and not the voice, and the lock screen knows", () => {
    act(() => root.render(<ReadAloud parts={["Headline", "Lead", "Body"]} title="La columna" audio={audio} />));
    expect(button("Listen").textContent).toContain("2 min");
    act(() => button("Listen").click());
    expect(synth.spoken).toHaveLength(0);
    expect(host.querySelector("audio")?.getAttribute("src")).toBe(audio.src);
    expect(document.documentElement.dataset.speaking).toBe("playing");
    expect((session.metadata as { init: { title: string; artist: string } }).init).toMatchObject({ title: "La columna", artist: "Insights" });
    expect(session.handlers.has("pause")).toBe(true);
    expect(session.handlers.has("nexttrack")).toBe(true);
  });

  it("highlights the part being read and forward skips to the next", () => {
    const parts: (number | null)[] = [];
    act(() => root.render(<ReadAloud parts={["Headline", "Lead", "Body"]} title="Something" audio={audio} onPart={(part) => parts.push(part)} />));
    act(() => button("Listen").click());
    const element = host.querySelector("audio")!;
    act(() => {
      element.currentTime = 10;
      element.dispatchEvent(new Event("timeupdate"));
    });
    expect(parts.at(-1)).toBe(1);
    act(() => button("Forward").click());
    expect(element.currentTime).toBe(30);
  });

  it("if the audio does not load, the device voice reads", () => {
    act(() => root.render(<ReadAloud parts={["First."]} title="Something" audio={audio} />));
    act(() => {
      host.querySelector("audio")!.dispatchEvent(new Event("error"));
    });
    expect(host.querySelector("audio")).toBeNull();
    act(() => button("Listen").click());
    expect(synth.spoken.map((one) => one.text)).toEqual(["First."]);
  });
});
