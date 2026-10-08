import type { Plugin } from "vite";

export const PUBLIC_FONTS: [string, string][];
export function fontSource(file: string, pkg: string): string;
export function publicFonts(): Plugin;
