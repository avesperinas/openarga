import { renderToString } from "react-dom/server";

import { ConfirmStartSheet, rotationDetail } from "./ConfirmStart";
import { english, inLocale } from "./i18n/testing";

describe("confirming before starting", () => {
  it("asks about the day, says where it falls and offers cancel before start", () => {
    const html = renderToString(
      inLocale(
        <ConfirmStartSheet
          name="Pull"
          detail={rotationDetail(english, 3, 2, 3)}
          onCancel={() => undefined}
          onStart={async () => undefined}
        />,
      ),
    );

    expect(html).toContain("Start Pull?");
    expect(html).toContain("Rotation 3, day 2 of 3.");
    expect(html).toMatch(/Cancel.*Start Pull/);
  });

  it("lets you start another day of the plan, with the done ones marked and the due one chosen (T-B05)", () => {
    const html = renderToString(
      inLocale(
        <ConfirmStartSheet
          name="Pull"
          detail={rotationDetail(english, 3, 2, 3)}
          days={[
            { id: "d1", name: "Push", done: true },
            { id: "d2", name: "Pull", done: false },
            { id: "d3", name: "Leg", done: false },
          ]}
          chosen="d2"
          onChoose={() => undefined}
          onCancel={() => undefined}
          onStart={async () => undefined}
        />,
      ),
    );

    expect(html).toContain('aria-label="Another day"');
    expect(html).toContain("Push ✓");
    expect(html).toMatch(/aria-checked="true"[^>]*>Pull</);
  });
});
