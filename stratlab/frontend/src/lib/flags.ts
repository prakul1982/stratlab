/* Switches the site's /config.js can turn on without a rebuild ("on", "true", "yes", "1" or true). Pure, so the unit tests load it. */
export const configOn = (v: unknown): boolean => v === true || (typeof v === "string" && /^(on|true|1|yes)$/i.test(v.trim()));
