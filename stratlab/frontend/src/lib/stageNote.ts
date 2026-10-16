/* What "Stage 1 (basing)" and the other stages mean, in plain words, wherever a stage is named: facts about the 150-day
 * average and where the price sits against it, never a call. Matches the server's rule (engine/indicators.py: stage).
 * No imports, so the unit tests load it alone. */

export const STAGE_MEANING: Record<number, string> = {
  1: "Stage 1 (basing): the 150-day average has stopped falling, or the price has climbed above a falling average.",
  2: "Stage 2 (advancing): the price is above a rising 150-day average.",
  3: "Stage 3 (topping): the 150-day average has stopped rising, or the price is below a rising one.",
  4: "Stage 4 (declining): the price is below a falling 150-day average.",
};

/** One line saying what the four stages are: for a column header or a note under a list. */
export const STAGES_EXPLAINED = "A stage is a plain description of the price against its 150-day average and that average's slope over 20 days. "
  + [1, 2, 3, 4].map((n) => STAGE_MEANING[n]).join(" ");

/** The meaning of the stage a text names ("Stage 3 (topping)", "Stage 2 · advancing"), or null when it names none. */
export function stageMeaning(text: string | null | undefined): string | null {
  const m = /\bStage ([1-4])\b/.exec(String(text ?? ""));
  return m ? STAGE_MEANING[Number(m[1])] : null;
}
