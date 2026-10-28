import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly } from "../../lib/format";
import { Badge, Card, CardHead, DataTable, Notice, Skeleton, type Column } from "../../components/kit";
import { postKind, runLine, type Blog, type BlogPost } from "./blog";

/** Admin: the public blog (daily market briefs and research posts). Lists the posts, shows or hides one, adds posts for the briefs
 * already stored, and writes the research posts from the app's own data now (they are also written once a month). */
export function BlogPanel() {
  const { fail, notify } = useApp();
  const [b, setB] = useState<Blog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => { try { setB(await api<Blog>("/admin/blog")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!b?.running) return;
    const t = window.setInterval(() => { void load(); }, 5000);          // the generator runs in the background for a minute or so
    return () => window.clearInterval(t);
  }, [b?.running, load]);
  const act = async (key: string, fn: () => Promise<void>) => { setBusy(key); try { await fn(); } catch (e) { fail(e); } finally { setBusy(null); } };
  const research = () => act("research", async () => {
    const r = await api<{ started: boolean }>("/admin/blog/research", { method: "POST" });
    notify(r.started ? "Writing the research posts. It takes about a minute." : "The research posts are already being written.");
    await load();
  });
  const briefs = () => act("briefs", async () => {
    const r = await api<{ added: number; skipped: number }>("/admin/blog/briefs", { method: "POST" });
    notify(r.added ? `Added ${r.added} market brief post${r.added === 1 ? "" : "s"}.` : "Every stored brief already has its post.");
    await load();
  });
  const show = (p: BlogPost) => act(p.slug, async () => {
    await api(`/admin/blog/posts/${encodeURIComponent(p.slug)}/published`, { method: "POST", body: { published: !p.published } });
    notify(p.published ? "Post hidden. It answers 404 and is out of the list, the sitemap and the feed." : "Post published.");
    await load();
  });
  const cols: Column<BlogPost>[] = [
    { key: "t", header: "Post", rowHeader: true, wrap: true, cell: (p) => (
      <span className="k-stack"><a className="link" href={`/blog/${p.slug}`} target="_blank" rel="noreferrer">{p.title}<span className="sr-only"> (opens in a new tab)</span></a>
        <span className="k-note k-muted">{postKind(p)}</span></span>) },
    { key: "d", header: "Published", cell: (p) => dateOnly(p.published_at) },
    { key: "u", header: "Changed", cell: (p) => dateOnly(p.updated_at) },
    { key: "s", header: "Status", wrap: true, cell: (p) => (
      <span className="k-stack">
        {p.published ? <Badge tone="ok">Published</Badge> : <Badge tone="warn">Hidden</Badge>}
        {!p.indexable && <span className="k-note k-muted">Not for search: too little to say</span>}
      </span>) },
    { key: "a", header: "", action: true, corner: true, cell: (p) => (
      <button type="button" className="btn quiet sm" disabled={busy === p.slug} onClick={() => void show(p)}>{p.published ? "Hide" : "Publish"}</button>) },
  ];
  return (
    <Card label="Blog">
      <CardHead title="Blog"
        info="The public blog at /blog: each trading day's India and US market brief is saved as a post after it is built (market-level facts only, never anything from a user's account), and three research posts are written from StratLab's own data once a month and when you press the button. Hide a post to take it off the site."
        actions={<>
          <button type="button" className="btn quiet sm" disabled={busy === "briefs"} onClick={() => void briefs()}>Add posts for stored briefs</button>
          <button type="button" className="btn sm" disabled={busy === "research" || !!b?.running} onClick={() => void research()}>{b?.running ? "Writing…" : "Write the research posts"}</button>
        </>} />
      {!b ? <Skeleton label="Loading the posts" /> : (
        <>
          <p className="k-small k-muted">
            {b.counts.posts} post{b.counts.posts === 1 ? "" : "s"}: {b.counts.shown} on the site{b.counts.hidden ? `, ${b.counts.hidden} hidden` : ""}{b.counts.not_indexed ? `, ${b.counts.not_indexed} kept out of search` : ""}.
            {" "}<a className="link" href="/blog" target="_blank" rel="noreferrer">Open the blog<span className="sr-only"> (opens in a new tab)</span></a>
          </p>
          <p className={`k-small ${b.run.problems?.length ? "k-down" : "k-muted"}`} data-testid="blog-run">{runLine(b.run)}</p>
          {b.posts.length === 0 && <Notice>No posts yet. The first market brief is saved after the next close; "Add posts for stored briefs" saves the ones already built.</Notice>}
          {b.posts.length > 0 && <DataTable label="Blog posts" rows={b.posts} rowKey={(p) => p.slug} columns={cols} stack />}
        </>
      )}
    </Card>
  );
}
