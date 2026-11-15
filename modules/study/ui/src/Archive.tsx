import { List, ListRow, OfflineNotice, Screen } from "@openarga/ui";

import { api } from "./api";
import { useNavigate } from "./App";
import { Empty, Pending, Problem, useLoad } from "./Bits";
import { ScreenHeader } from "./Header";
import { KINDS, dateLong, grade, labelOf } from "./words";
import { t } from "./lang";

export function ArchiveScreen() {
  const navigate = useNavigate();
  const { data, found, problem } = useLoad("courses:archive", () => api.courses("archive"));

  return (
    <Screen>
      <ScreenHeader back={{ label: t("app.name"), onClick: () => navigate({ tab: "home" }) }} title={t("archive.title")} />
      <OfflineNotice />
      <Problem text={problem} />
      {data === null && <Pending found={found} />}
      {data && data.length === 0 && (
        <Empty title={t("archive.empty")}>
          <p>{t("archive.empty_detail")}</p>
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
                  course.closed_on
                    ? t(finished ? "archive.finished_on" : "archive.abandoned_on", { date: dateLong(course.closed_on) })
                    : t(finished ? "archive.finished" : "archive.abandoned"),
                  course.institution ?? labelOf(KINDS, course.kind),
                  course.progress?.label,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                detail={course.has_certificate ? t("archive.with_certificate") : undefined}
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
