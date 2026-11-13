import { Button, Hint } from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { detector, isbnFrom } from "./scanner";
import { t } from "./lang";

export function Scanner({ onIsbn, onCancel }: { onIsbn: (isbn: string) => void; onCancel: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let stopped = false;
    let timer = 0;

    async function start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
      } catch {
        setProblem(t("scan.no_camera"));
        return;
      }
      const element = video.current;
      if (!element || stopped) return;
      element.srcObject = stream;
      await element.play().catch(() => undefined);
      const reader = await detector().catch(() => null);
      if (!reader) {
        setProblem(t("scan.unsupported"));
        return;
      }
      const look = async () => {
        if (stopped) return;
        try {
          for (const found of await reader.detect(element)) {
            const isbn = isbnFrom(found.rawValue);
            if (isbn) {
              stopped = true;
              onIsbn(isbn);
              return;
            }
          }
        } catch {
        }
        timer = window.setTimeout(() => void look(), 200);
      };
      void look();
    }

    void start();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [onIsbn]);

  return (
    <div className="library-scanner">
      {problem ? (
        <Hint tone="warning">
          {problem}
        </Hint>
      ) : (
        <>
          <video ref={video} className="library-scanner-video" muted playsInline aria-label={t("scan.camera")} />
          <Hint>{t("scan.hint")}</Hint>
        </>
      )}
      <Button variant="secondary" onClick={onCancel}>
        {t("action.cancel")}
      </Button>
    </div>
  );
}
