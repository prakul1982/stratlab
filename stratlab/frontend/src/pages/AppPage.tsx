import { PhoneCard } from "../components/PhoneCard";
import { PageHeader } from "../components/kit";

/** /app (Get the app): put StratLab on the home screen and get alerts and the daily report as phone notifications. */
export function AppPage() {
  return (
    <div className="k-page">
      <PageHeader eyebrow="Mine · Get the app" title="Get the app" lede="Put StratLab on your phone's home screen, with its own icon and full screen, and get your alerts and the daily report as notifications." />
      <PhoneCard />
    </div>
  );
}
