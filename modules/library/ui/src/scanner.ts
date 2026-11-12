interface Detected {
  rawValue: string;
}

interface Detector {
  detect(source: HTMLVideoElement): Promise<Detected[]>;
}

const FORMATS: ("ean_13" | "ean_8")[] = ["ean_13", "ean_8"];

let made: Promise<Detector> | null = null;

export function detector(): Promise<Detector> {
  made ??= (async () => {
    const native = (globalThis as { BarcodeDetector?: new (options: { formats: string[] }) => Detector })
      .BarcodeDetector;
    if (native) return new native({ formats: FORMATS });
    const [{ BarcodeDetector, prepareZXingModule }, { default: wasm }] = await Promise.all([
      import("barcode-detector/ponyfill"),
      import("zxing-wasm/reader/zxing_reader.wasm?url"),
    ]);
    prepareZXingModule({
      overrides: { locateFile: (path: string, prefix: string) => (path.endsWith(".wasm") ? wasm : prefix + path) },
    });
    return new BarcodeDetector({ formats: FORMATS });
  })();
  return made;
}

export function isbnFrom(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  return /^97[89]\d{10}$/.test(digits) ? digits : null;
}
