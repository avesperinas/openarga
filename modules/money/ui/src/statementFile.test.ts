import { describe, expect, it } from "vitest";

import { formatOf, previewOf, splitRow } from "./statementFile";

const OFX = `OFXHEADER:100
<OFX>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20300103120000<TRNAMT>-42.10<FITID>1<NAME>Groceries<MEMO>Card
</STMTTRN>
<STMTTRN><DTPOSTED>20300104<TRNAMT>1800.00<FITID>2<NAME>Salary
</STMTTRN>
</BANKTRANLIST>
</OFX>`;

describe("reading a bank file before it is imported", () => {
  it("tells OFX from CSV by name or by content", () => {
    expect(formatOf("march.ofx", "")).toBe("ofx");
    expect(formatOf("march.QFX", "")).toBe("ofx");
    expect(formatOf("export.txt", OFX)).toBe("ofx");
    expect(formatOf("march.csv", "Date;Amount\n")).toBe("csv");
  });

  it("splits a row with quotes and the delimiter inside them", () => {
    expect(splitRow('2030-01-03;"Shop; ""big"""; -4,50', ";")).toEqual(["2030-01-03", 'Shop; "big"', "-4,50"]);
  });

  it("previews a CSV with its header, the first rows and how many there are", () => {
    const text = "﻿Date;Description;Amount\n2030-01-03;Groceries;-42,10\n\n2030-01-04;Salary;1800,00\n2030-01-05;Rent;-650,00\n";
    expect(previewOf(text, "csv", 2)).toEqual({
      header: ["Date", "Description", "Amount"],
      rows: [
        ["2030-01-03", "Groceries", "-42,10"],
        ["2030-01-04", "Salary", "1800,00"],
      ],
      total: 3,
    });
  });

  it("picks the commonest delimiter of the header", () => {
    expect(previewOf("a,b,c\n1,2,3", "csv").header).toEqual(["a", "b", "c"]);
    expect(previewOf("a\tb\tc\n1\t2\t3", "csv").rows).toEqual([["1", "2", "3"]]);
  });

  it("previews an empty file as nothing", () => {
    expect(previewOf("  \n\n", "csv")).toEqual({ header: null, rows: [], total: 0 });
  });

  it("previews an OFX as date, amount and description", () => {
    expect(previewOf(OFX, "ofx")).toEqual({
      header: null,
      rows: [
        ["2030-01-03", "-42.10", "Groceries Card"],
        ["2030-01-04", "1800.00", "Salary"],
      ],
      total: 2,
    });
  });
});
