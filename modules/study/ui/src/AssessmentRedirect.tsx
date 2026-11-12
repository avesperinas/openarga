import { OfflineNotice, Screen } from "@openarga/ui";
import { useEffect } from "react";

import { api } from "./api";
import { useNavigate } from "./App";
import { Pending, Problem, useLoad } from "./Bits";
import { ScreenHeader } from "./Header";

export function AssessmentRedirect({ id }: { id: string }) {
  const navigate = useNavigate();
  const { data, found, problem } = useLoad(`assessment:${id}`, () => api.assessment(id));

  useEffect(() => {
    if (!data) return;
    if (data.subject_id) navigate({ tab: "subject", id: data.subject_id }, { replace: true });
    else navigate({ tab: "course", id: data.course_id, section: "assessments" }, { replace: true });
  }, [data, navigate]);

  return (
    <Screen>
      <ScreenHeader back={{ label: "Study", onClick: () => navigate({ tab: "home" }) }} />
      <OfflineNotice />
      <Problem text={problem} />
      <Pending found={found} />
    </Screen>
  );
}
