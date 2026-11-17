/**
 * The `<Widget>` API, checked by the compiler.
 *
 * This file **does not run**: `tsc` checks it, as part of `pnpm lint`. Each `@ts-expect-error`
 * is an inverted assertion: if that line ever stopped being an error, `tsc` fails and so does
 * the PR. It is how "a module cannot do this" is written without relying on someone remembering.
 *
 * What it defends, the T-025 criterion: **a module cannot draw its own header.** If it could,
 * twenty widgets written at twenty different moments would stop looking like one system
 * (ADR-0004).
 */
import * as React from "react";

import { Widget, WidgetDetail, WidgetValue } from "../src/index";

const valid = (
  <Widget title="Events" hue={1} size="2x2" shape="number" state="ready">
    <WidgetValue>1.284</WidgetValue>
    <WidgetDetail>12 today</WidgetDetail>
  </Widget>
);

// @ts-expect-error · there is no header prop: the header belongs to the system, not the module
const withHeader = <Widget title="Events" hue={1} size="2x2" shape="number" state="ready" header={<h2>Mine</h2>} />;

// @ts-expect-error · nor in parts: no icon of its own
const withIcon = <Widget title="Events" hue={1} size="2x2" shape="number" state="ready" icon="📊" />;

// @ts-expect-error · no actions of its own in the header
const withActions = <Widget title="Events" hue={1} size="2x2" shape="number" state="ready" actions={[]} />;

// @ts-expect-error · no loose classes to sneak in
const withClass = <Widget title="Events" hue={1} size="2x2" shape="number" state="ready" className="mine" />;

// @ts-expect-error · no inline style, the back door to principle 5
const withStyle = <Widget title="Events" hue={1} size="2x2" shape="number" state="ready" style={{ padding: 0 }} />;

// @ts-expect-error · the title is not optional: it comes from the manifest and renders before the data
const untitled = <Widget hue={1} size="2x2" shape="number" state="ready" />;

// @ts-expect-error · sizes are the catalogue's and no others
const madeUpSize = <Widget title="Events" hue={1} size="3x1" shape="number" state="ready" />;

// @ts-expect-error · the tone comes from the fixed palette, it is not invented in the component
const madeUpTone = <Widget title="Events" hue={99} size="2x2" shape="number" state="ready" />;

// @ts-expect-error · `uncertain` is not a state: it is a modifier of `ready` (ADR-0016)
const doubtAsState = <Widget title="Events" hue={1} size="2x2" shape="number" state="uncertain" />;

export { valid, withHeader, withIcon, withActions, withClass, withStyle, untitled, madeUpSize, madeUpTone, doubtAsState };
