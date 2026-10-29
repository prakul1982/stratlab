import { useEffect, useMemo, useRef, useState } from "react";
import { CUSTOM_UNITS, offeredRanges, rangeFrom, rangeLabel, saveRange, spanWords, startRange, toMs, type RangeOption } from "../../lib/range";
import { ChipBar } from "./ChipBar";

/** The one range control for a history chart (O4): 1W 1M 3M 6M YTD 1Y 3Y 5Y All and "+ Custom", only the chips the data reaches, the
 * choice remembered for this chart (`chart`, a stable name) on this device. `times` are the chart's points, oldest first (ISO dates
 * or milliseconds): the hook returns the index the range starts at, so a chart, its table and its figures all cut the same way. */
export function useRange(chart: string, times: (string | number)[]) {
  const options = useMemo(() => offeredRanges(times), [times]);
  const touched = useRef(false);
  const [value, setValue] = useState(() => startRange(chart, times, options));
  // the data arrives after the first paint: the remembered range applies once there are chips to hold it, unless the reader chose one
  useEffect(() => { if (!touched.current) setValue(startRange(chart, times, options)); }, [chart, times, options]);
  const pick = (v: string) => { touched.current = true; setValue(v); saveRange(chart, v); };
  const from = rangeFrom(times, value);
  const shown = from > 0 ? (value === "all" ? "all" : value) : "all";
  return { options, value: shown, pick, from };
}

export function RangeChips({ chart, times, options, value, onChange, label = "Range" }: {
  chart: string; times: (string | number)[]; options: RangeOption[]; value: string; onChange: (v: string) => void; label?: string;
}) {
  if (options.length < 2) return null;
  const first = toMs(times[0]), last = toMs(times[times.length - 1]);
  const have = spanWords((last - first) / 86_400_000);
  return (
    <ChipBar label={label} options={options} value={value} onChange={onChange}
      custom={{
        storageKey: `stratlab.range.custom.${chart}`, units: CUSTOM_UNITS, defaultUnit: "months",
        // a custom stretch that reaches back past the first point shows what "All" shows: refused in words, never added as a twin chip
        validate: (n, unit) => rangeFrom(times, `${n} ${unit}`) > 0 ? { value: `${n} ${unit}`, label: rangeLabel(`${n} ${unit}`) }
          : { error: `This chart has ${have} of data, so ${rangeLabel(`${n} ${unit}`)} is all of it. Pick All.` },
        keep: (v) => rangeFrom(times, v) > 0,
      }} />
  );
}
