"""Supabase access with the service-role key (bypasses RLS, server only)."""
from datetime import datetime, timezone
from supabase import create_client, Client
from .config import settings

_client: Client | None = None


def sb() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- profiles ----------
def get_profile(user_id: str, email: str | None = None) -> dict:
    r = sb().table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if r.data:
        return r.data[0]
    return sb().table("profiles").upsert({"id": user_id, "email": email, "plan": "free"}).execute().data[0]


def update_profile(user_id: str, **fields) -> dict:
    fields["updated_at"] = now_iso()
    return sb().table("profiles").update(fields).eq("id", user_id).execute().data[0]


def profile_by_subscription(sub_id: str) -> dict | None:
    r = sb().table("profiles").select("*").eq("razorpay_subscription_id", sub_id).limit(1).execute()
    return r.data[0] if r.data else None


# ---------- usage ----------
def count_usage(user_id: str, kind: str, since_iso: str) -> int:
    r = (sb().table("usage_events").select("id", count="exact")
         .eq("user_id", user_id).eq("kind", kind).gte("created_at", since_iso).execute())
    return r.count or 0


def add_usage(user_id: str, kind: str) -> None:
    sb().table("usage_events").insert({"user_id": user_id, "kind": kind}).execute()


# ---------- strategies ----------
def list_strategies(user_id: str) -> list[dict]:
    return (sb().table("strategies").select("id,name,body,instrument_token,updated_at")
            .eq("user_id", user_id).order("updated_at", desc=True).execute().data)


def get_strategy(user_id: str, sid: str) -> dict | None:
    r = sb().table("strategies").select("*").eq("user_id", user_id).eq("id", sid).limit(1).execute()
    return r.data[0] if r.data else None


def save_strategy(user_id: str, name: str, body: dict, token: int | None, sid: str | None = None) -> dict | None:
    row = {"user_id": user_id, "name": name, "body": body, "instrument_token": token, "updated_at": now_iso()}
    if sid:
        r = sb().table("strategies").update(row).eq("user_id", user_id).eq("id", sid).execute()
        return r.data[0] if r.data else None
    return sb().table("strategies").insert(row).execute().data[0]


def list_notebook_rows(user_id: str) -> list[dict]:
    """Notebook list without the (large) experiment history."""
    return (sb().table("strategies")
            .select("id,name,instrument_token,updated_at,kind:body->>kind,question:body->>question,"
                    "instrument:body->instrument,summary:body->summary,tf:body->>tf,pinned:body->>pinned,group:body->group")
            .eq("user_id", user_id).order("updated_at", desc=True).execute().data)


def delete_strategy(user_id: str, sid: str) -> None:
    sb().table("strategies").delete().eq("user_id", user_id).eq("id", sid).execute()


# ---------- live sessions ----------
def create_session(row: dict) -> dict:
    return sb().table("live_sessions").insert(row).execute().data[0]


def update_session(sid: str, **fields) -> None:
    sb().table("live_sessions").update(fields).eq("id", sid).execute()


def running_sessions() -> list[dict]:
    return sb().table("live_sessions").select("*").eq("status", "running").execute().data


def user_sessions(user_id: str, limit: int = 20) -> list[dict]:
    return (sb().table("live_sessions")
            .select("id,name,instrument,status,started_at,stopped_at,stop_reason")
            .eq("user_id", user_id).order("started_at", desc=True).limit(limit).execute().data)


def get_session_row(user_id: str, sid: str) -> dict | None:
    r = sb().table("live_sessions").select("*").eq("user_id", user_id).eq("id", sid).limit(1).execute()
    return r.data[0] if r.data else None


def delete_session(user_id: str, sid: str) -> None:
    """Remove one of the user's sessions; its orders go with it (on delete cascade)."""
    sb().table("live_sessions").delete().eq("user_id", user_id).eq("id", sid).neq("status", "running").execute()


def delete_stopped_sessions(user_id: str) -> int:
    r = sb().table("live_sessions").delete().eq("user_id", user_id).neq("status", "running").execute()
    return len(r.data or [])


def add_order(row: dict) -> None:
    sb().table("live_orders").insert(row).execute()


def session_orders(session_id: str) -> list[dict]:
    return (sb().table("live_orders").select("*").eq("session_id", session_id)
            .order("ts", desc=True).limit(200).execute().data)


# ---------- app settings (Kite token) ----------
def get_setting(key: str) -> str | None:
    r = sb().table("app_settings").select("value").eq("key", key).limit(1).execute()
    return r.data[0]["value"] if r.data else None


def set_setting(key: str, value: str) -> None:
    sb().table("app_settings").upsert({"key": key, "value": value, "updated_at": now_iso()}).execute()


def delete_setting(key: str) -> None:
    sb().table("app_settings").delete().eq("key", key).execute()
