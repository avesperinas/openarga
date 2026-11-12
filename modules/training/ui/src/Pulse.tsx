import { Heading, WorkoutHeart } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type WorkoutPulse, readHeart } from "./api";

export function WorkoutPulseCard({ id, start }: { id: string; start: string }) {
  const [found, setFound] = useState<WorkoutPulse | null>(null);

  useEffect(() => {
    let live = true;
    readHeart(id)
      .then((pulse) => live && setFound(pulse))
      .catch(() => live && setFound(null));
    return () => {
      live = false;
    };
  }, [id]);

  if (!found?.found || (found.avg === null && found.beats.length === 0)) return null;
  return (
    <section className="surface training-pulse" aria-label="El vitals del entreno">
      <Heading>El vitals</Heading>
      <WorkoutHeart heart={found} start={start} />
    </section>
  );
}
