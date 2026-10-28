import { CFG } from "./config";
import { adsConfig } from "./ads";

/** The ads and trackers settings this build runs with (ADS-1): the build's VITE_ values, overridden by public/config.js. On its
 *  own so the consent banner and the public pages read it without loading the ad slot's code. */
export const CONFIG = adsConfig(import.meta.env as Record<string, unknown>, CFG as unknown as Record<string, unknown>);
