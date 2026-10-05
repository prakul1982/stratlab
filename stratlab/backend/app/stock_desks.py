"""The per-stock market desks wired together: stock futures (stock_futures.py), stock lending (slb.py) and
margin-funded positions (mtf.py) share one runner and one job (exchange_days.py) over the exchange client, and the
admins' view of them. Every user-facing route lives with its desk."""
import threading

from fastapi import APIRouter, Depends

from . import admin, exchange_days as X, mtf, slb, stock_futures
from .responses import err

DESKS = [stock_futures.DESK, slb.DESK, mtf.DESK]


def _m():
    """The main module, for the exchange client and the stock alerts' limits. Imported late: it imports us."""
    from . import main
    return main


def _fire(events: list[dict], now) -> int:
    """A desk's new day into the stock alerts (MWPL crossing 80%, a margin-funded level), within each user's limits."""
    from . import stock_alerts
    m = _m()
    return stock_alerts.fire_events(events, now, m._alert_limit, kind_ok=m._alert_kind_ok)


runner = X.Runner(DESKS, lambda: _m().filings_feed, fire=_fire)
job = X.Job(runner)

admin_router = APIRouter(prefix="/admin/stock-desks", tags=["admin"])


@admin_router.get("")
def desks_state(_=Depends(admin.admin_profile)):
    """Each desk's stored days, its last try and its archive walk, and the job's last run."""
    return {"desks": {d.name: {**X.status(d), "state": d.store.state()} for d in DESKS}, "job": job.status,
            "running": runner.running}


@admin_router.post("/{name}/run")
def desks_run(name: str, backfill: bool = False, _=Depends(admin.admin_profile)):
    """Read a desk's missing recent days now (or, with backfill, a few more archive days), in the background."""
    desk = runner.desks.get(name)
    if desk is None:
        err(404, "no_desk", f"No desk called {name}. Pick one of {', '.join(runner.desks)}.")
    if runner.running:
        err(409, "busy", "A desk run is already going.")

    def work():
        try:
            if backfill:
                runner.backfill(desk, X.ist_now().date())
            else:
                job.status["desks"][name] = {"catch_up": runner.catch_up(desk)}
        except Exception as e:
            print(f"stock desk {name} run failed:", str(e)[:160])
    threading.Thread(target=work, daemon=True, name=f"desk-{name}").start()
    return {"started": True, "desk": name, "status": X.status(desk)}
