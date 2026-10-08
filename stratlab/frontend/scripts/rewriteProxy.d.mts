export function forwardedPaths(vercelPath?: URL | string): string[];
export function sourceRegex(source: string): string;
export function rewriteProxy(target?: string, sources?: string[]): Record<string, { target: string; changeOrigin: boolean }>;
