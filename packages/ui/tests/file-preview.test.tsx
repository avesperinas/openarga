import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { FilePreview, fileSize } from "../src/file-preview";
import es from "../src/i18n/es.json";
import { configureRegional } from "../src/regional";

afterEach(() => configureRegional({ locale: "es-ES" }));

const rows = [
  ["2030-01-03", "Groceries", "-42.10"],
  ["2030-01-04", "Salary", "1800.00"],
];

describe("FilePreview", () => {
  it("shows the file, its size, the header and the rows", () => {
    configureRegional({ locale: "en-US" });
    const html = renderToStaticMarkup(
      <FilePreview name="statement.csv" size={2048} columns={["Date", "Description", "Amount"]} rows={rows} />,
    );
    expect(html).toContain("statement.csv");
    expect(html).toContain("2.0 KB");
    expect(html).toContain('<th scope="col">Description</th>');
    expect(html).toContain("<td>Salary</td>");
    expect(html).not.toContain("more rows");
  });

  it("says how many rows are not shown, in the person's language", () => {
    configureRegional({ locale: "en-US" });
    expect(renderToStaticMarkup(<FilePreview name="a.csv" rows={rows} total={10} />)).toContain("8 more rows not shown");
    configureRegional({ locale: "es-ES" });
    const html = renderToStaticMarkup(<FilePreview name="a.csv" rows={rows} total={10} onRemove={() => undefined} />);
    expect(html).toContain(es["file_preview.more"].replace("{count}", "8"));
    expect(html).toContain(`aria-label="${es["file_preview.remove"]}"`);
  });

  it("offers no remove button without a handler and says when there is nothing to show", () => {
    configureRegional({ locale: "en-US" });
    const html = renderToStaticMarkup(<FilePreview name="empty.csv" rows={[]} />);
    expect(html).not.toContain("<button");
    expect(html).toContain("Nothing to show in this file.");
  });

  it("writes sizes in bytes, kilobytes and megabytes", () => {
    expect(fileSize(512)).toBe("512 B");
    expect(fileSize(1536)).toBe("1.5 KB");
    expect(fileSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});
