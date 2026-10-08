export function forwardedPaths(vercelPath?: URL | string): string[];
export function rewriteProxy(target?: string, paths?: string[]): Record<string, { target: string; changeOrigin: boolean }>;
