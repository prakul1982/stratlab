import type { Plugin } from "vite";
export function homeJsonLd(): string;
export function pageHtml(template: string, page: { title: string; description: string; canonical: string; index: boolean; jsonld?: string }): string;
export function pageFiles(template: string): [string, string][];
export function libraryFiles(template: string): [string, string][];
export function seoPages(): Plugin;
