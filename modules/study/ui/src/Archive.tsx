import { List, ListRow, OfflineNotice, Screen } from "@openarga/ui";

import { api } from "./api";
import { useNavigate } from "./App";
import { Empty, Pending, Problem, useLoad } from "./Bits";
import { ScreenHeader } from "./Header";
import { KINDS, dateLong, grade, labelOf } from "./words";

export function ArchiveScreen() {
  const navigate = useNavigate();
  const { data, found, problem } = useLoad("courses:archive", () => api.courses("archive"));

  return (
    <Screen>
      <ScreenHeader back={{ label: "Study", onClick: () => navigate({ tab: "home" }) }} title="Archivo" />
      <OfflineNotice />
      <Problem text={problem} />
      {data === null && <Pending found={found} />}
      {data && data.length === 0 && (
        <Empty title="Nada archivado">
          <p>Al terminar o abandonar un estudio, pasa aquí con su nota y su certificado.</p>
        </Empty>
      )}
      {data && data.length > 0 && (
        <List>
          {data.map((course) => {
            const finished = course.status === "finished";
            const average = course.average.average ?? course.grade?.final ?? null;
            return (
              <ListRow
                key={course.id}
                title={course.name}
                subtitle={[
                  `${finished ? "Terminado" : "Abandonado"}${course.closed_on ? ` el ${dateLong(course.closed_on)}` : ""}`,
                  course.institution ?? labelOf(KINDS, course.kind),
                  course.progress?.label,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                detail={course.has_certificate ? "Con título" : undefined}
                value={finished ? grade(average, course.scale_max) : undefined}
                tone={finished ? "positive" : undefined}
                accessory="chevron-right"
                onClick={() => navigate({ tab: "course", id: course.id })}
              />
            );
          })}
        </List>
      )}
    </Screen>
  );
}
