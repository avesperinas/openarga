"use client";

import { zonedDates } from "@openarga/ui";
import * as React from "react";

const long = () => zonedDates({ weekday: "long", day: "numeric", month: "long" });

const CHECK_MS = 60_000;

export function TodayDate({ initial }: { initial: string }) {
  const [shown, setShown] = React.useState(initial);
  React.useEffect(() => {
    const check = () => setShown(long().format(new Date()));
    check();
    const timer = window.setInterval(check, CHECK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);
  return <p className="today-date">{shown}</p>;
}
