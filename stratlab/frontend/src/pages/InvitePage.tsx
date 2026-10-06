import { InviteCard } from "../components/ShareCompany";
import { PageHeader } from "../components/kit";

/** /invite: your own link, how many friends joined through it, and the free months earned. */
export function InvitePage() {
  return (
    <div className="k-page">
      <PageHeader eyebrow="Mine · Invite friends" title="Invite friends" lede="Share your link. When a friend joins and uses StratLab, you both get a month of Basic." />
      <InviteCard />
    </div>
  );
}
