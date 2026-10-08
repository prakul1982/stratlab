"""What StratLab knows about each AI provider and model, kept in code so it can be read and reviewed.

Every provider here has a genuinely free allowance (except Anthropic, which is paid and always asked last). Each one
is used only when its key is set. The free limits, the terms and where to get a key are shown on the Admin page and
in docs/ADMIN.md; keep the three in step when a provider changes its offer.

Which models are actually used is decided by measurement (ai_rank.py): a provider's model list is filtered here,
then each remaining model is asked a small fixed test, and the ones that answer correctly and quickly are kept. The
curated `defaults` below are only the cold start: what is tried before the first measurement, or when the provider
can't list its models."""
import re
from dataclasses import dataclass, field

from .config import settings


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    kind: str                       # "openai" (OpenAI-style chat API), "gemini" (Google's own API) or "anthropic"
    base: str                       # chat API base URL; {account} is filled from an extra setting (Cloudflare)
    key_env: str                    # the Railway variable that holds the key
    key_url: str                    # where the owner gets a key
    free: str                       # the free allowance, in plain English
    terms: str                      # "ok" (production use allowed), "prototype" (free tier is for trying things out
                                    # only: used last, after every production-ready provider), or "paid"
    defaults: tuple[str, ...]       # known-good models, best first: the cold start, never the final word
    extra_env: tuple[str, ...] = ()     # more settings the provider needs (Cloudflare's account id)
    models_url: str | None = "/models"  # where the provider lists its models (relative to `base`, or a full URL);
                                        # None = it doesn't, so the curated defaults are the list
    allow: str | None = None        # only models matching this are free / usable on this provider
    deny: str | None = None         # more models to leave out on this provider only
    limit_scope: str = "provider"   # a rate limit applies to the whole key ("provider") or to one model ("model")
    max_out: int = 16000            # the most reply tokens the provider allows per request
    ctx: int = 32000                # context window (tokens) assumed when the model list doesn't say
    probe_max: int = 6              # models measured per re-rank (each costs two small requests of free quota)
    probe_every_h: float = 6.0      # hours between automatic re-ranks; 0 = only when the Admin page asks (paid)
    prior: tuple[int, int, int] = (50, 50, 50)    # cold-start order for quick / research / long jobs (lower first)
    tight_daily_tokens: bool = False    # few tokens a day free: keep it for short jobs
    note: str = ""                  # anything else the owner should know, shown in Admin
    headers: dict = field(default_factory=dict)

    @property
    def model_env(self) -> str:
        return self.key_env.rsplit("_", 2)[0] + "_MODEL" if self.key_env.endswith("_API_KEY") else self.name.upper() + "_MODEL"


PROVIDERS: dict[str, Provider] = {p.name: p for p in [
    Provider("groq", "Groq", "openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "https://console.groq.com/keys",
             "Free: about 30 requests a minute and 1,000 a day per model; the big models have a daily token cap.", "ok",
             ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"),
             limit_scope="model", ctx=128000, prior=(1, 5, 4), tight_daily_tokens=True),
    Provider("cerebras", "Cerebras", "openai", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "https://cloud.cerebras.ai",
             "Free tier: about 1 million tokens a day (new accounts may get trial credit instead).", "ok",
             ("llama-3.3-70b", "gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507", "llama3.1-8b"),
             ctx=64000, prior=(2, 1, 3)),
    Provider("gemini", "Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY",
             "https://aistudio.google.com/apikey",
             "Free tier: Flash models allow a few hundred to a thousand requests a day; Gemma models far more.", "ok",
             # 2.5 Flash and Flash-Lite are "no longer available to new users" (404, Oct 2026); Google names 3.8 Flash and
             # 3.5 Flash-Lite instead, and 3.5 Flash answered every test on the live key
             ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemma-3-27b-it"),
             # Pro models get few or no free requests; "live", "native-audio" and "image" models aren't text chat
             deny=r"pro|live|native|image|tts|robotics|computer|aqa|learnlm|nano-banana",
             limit_scope="model", ctx=1000000, max_out=65536, prior=(3, 3, 1),
             note="Free-tier prompts may be used by Google to improve its products."),
    Provider("mistral", "Mistral", "openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "https://console.mistral.ai/api-keys",
             "Free \"Experiment\" plan: about 1 request a second and a large monthly token allowance.", "ok",
             ("mistral-small-latest", "mistral-medium-latest", "open-mistral-nemo"),
             ctx=128000, prior=(4, 2, 2), note="The Experiment plan may use prompts to train models."),
    Provider("sambanova", "SambaNova", "openai", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY", "https://cloud.sambanova.ai/apis",
             "Free tier: a few requests a minute on each model.", "ok",
             ("Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1", "gpt-oss-120b", "Llama-4-Maverick-17B-128E-Instruct"),
             ctx=32000, prior=(5, 4, 5)),
    Provider("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "https://openrouter.ai/settings/keys",
             "Free models (marked :free): 20 requests a minute; 50 a day, or 1,000 a day once $10 of credit was ever bought.", "ok",
             ("meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-oss-120b:free", "deepseek/deepseek-chat-v3.1:free",
              "google/gemma-3-27b-it:free"),
             allow=r":free$", limit_scope="model", ctx=64000, prior=(6, 6, 6),
             headers={"HTTP-Referer": "https://stratlab.studio", "X-Title": "StratLab"}),
    Provider("cloudflare", "Cloudflare Workers AI", "openai", "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
             "CLOUDFLARE_API_TOKEN", "https://dash.cloudflare.com/profile/api-tokens",
             "Free: 10,000 \"neurons\" a day (roughly a few hundred short answers), reset at midnight UTC.", "ok",
             ("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/openai/gpt-oss-120b", "@cf/mistralai/mistral-small-3.1-24b-instruct",
              "@cf/meta/llama-4-scout-17b-16e-instruct"),
             extra_env=("CLOUDFLARE_ACCOUNT_ID",),
             models_url="https://api.cloudflare.com/client/v4/accounts/{account}/ai/models/search?task=Text%20Generation&per_page=200",
             ctx=24000, max_out=4000, probe_max=3, probe_every_h=12, prior=(7, 7, 9),   # measuring costs neurons
             note="Needs the account id too (CLOUDFLARE_ACCOUNT_ID) and a token with the Workers AI permission."),
    Provider("zai", "Z.ai (GLM Flash)", "openai", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", "https://z.ai/manage-apikey/apikey-list",
             "Free: the GLM Flash models cost nothing; about one request at a time.", "ok",
             ("glm-4.7-flash", "glm-4.5-flash"),
             # only the Flash models are free; FlashX is the paid fast tier
             allow=r"flash$|flash-\d", deny=r"flashx|-v\b|v-flash|\dv-", ctx=128000, max_out=8000, probe_max=3, prior=(8, 8, 7),
             note="A China-based service: prompts are processed outside India and the US."),
    Provider("huggingface", "Hugging Face", "openai", "https://router.huggingface.co/v1", "HF_TOKEN", "https://huggingface.co/settings/tokens",
             "Free: $0.10 of credit a month (about a hundred short answers); $2 a month with a PRO account.", "ok",
             ("meta-llama/Llama-3.3-70B-Instruct", "openai/gpt-oss-120b", "Qwen/Qwen3-235B-A22B-Instruct-2507", "deepseek-ai/DeepSeek-V3.1"),
             ctx=32000, probe_max=2, probe_every_h=72, prior=(10, 10, 10)),   # the credit is tiny: measure rarely
    Provider("vercel", "Vercel AI Gateway", "openai", "https://ai-gateway.vercel.sh/v1", "AI_GATEWAY_API_KEY",
             "https://vercel.com/dashboard/ai-gateway",
             "Free: $5 of credit every 30 days, on a set of free-tier models. Buying credit ends the free monthly $5.", "prototype",
             ("openai/gpt-oss-120b", "google/gemini-2.5-flash", "meta/llama-4-maverick"),
             # only the cheap open and Flash models: the $5 should last the month
             allow=r"gpt-oss|gemini-[\d.]+-flash|llama-4|gemma|glm-[\d.]+-flash|qwen[\d.-]*-?flash|nemotron|deepseek-v3",
             ctx=128000, probe_max=4, prior=(19, 19, 19),
             note="Fine on a Vercel Pro team; Vercel's Hobby plan is for personal, non-commercial use, so it's asked after "
                  "the production-ready providers."),
    Provider("github", "GitHub Models", "openai", "https://models.github.ai/inference", "GITHUB_MODELS_TOKEN",
             "https://github.com/settings/personal-access-tokens/new",
             "Free: 50 to 150 requests a day per model (8,000 tokens in, 4,000 out per request).", "prototype",
             ("openai/gpt-4.1-mini", "meta/Llama-3.3-70B-Instruct", "openai/gpt-4.1", "mistral-ai/mistral-small-2503"),
             models_url="https://models.github.ai/catalog/models", limit_scope="model", ctx=8000, max_out=4000, probe_max=2, probe_every_h=24,
             prior=(20, 20, 20), headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
             note="GitHub's free tier is meant for prototyping, so StratLab asks it only after every other free provider."),
    Provider("nvidia", "NVIDIA API catalog", "openai", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "https://build.nvidia.com/settings/api-keys",
             "Free for development: about 40 requests a minute.", "prototype",
             ("meta/llama-3.3-70b-instruct", "openai/gpt-oss-120b", "deepseek-ai/deepseek-v3.1", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
             # listed in the catalog but not served to a free account ("Function ... Not found for account", 404)
             deny=r"palmyra|llama2-|chatqa", ctx=32000, probe_max=4, prior=(21, 21, 21),
             note="NVIDIA's terms allow the free API for development and testing only, so StratLab asks it last among the free ones."),
    Provider("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys",
             "Paid only: no free allowance.", "paid", (), models_url=None, ctx=200000, probe_max=1, probe_every_h=0, prior=(99, 99, 99)),
]}

# Providers left out on purpose (checked October 2026), so nobody adds them back by mistake:
# - Chutes: its free API tier ended on 30 September 2026 (subscriptions from $3 a month).
# - Cohere: the free trial key is for non-commercial use only.
# - Anonymous gateways (LLM7, Pollinations): no account, no terms we can rely on, and prompts pass through a third party.

TASKS = ("quick", "research", "long")
TASK_LABELS = {"quick": "Idea builder and quick answers", "research": "Research reads", "long": "Long documents"}


def setting(name: str) -> str:
    return (getattr(settings, name, "") or "").strip()


def key_for(name: str) -> str:
    p = PROVIDERS.get(name)
    return setting(p.key_env) if p else ""


def configured(name: str) -> bool:
    """A key, plus any other setting the provider needs."""
    p = PROVIDERS.get(name)
    return bool(p and key_for(name) and all(setting(e) for e in p.extra_env))


def missing(name: str) -> list[str]:
    """The Railway variables still to set for this provider."""
    p = PROVIDERS[name]
    return [v for v in (p.key_env, *p.extra_env) if not setting(v)]


def model_setting(name: str) -> str:
    """A model pinned in Railway (<NAME>_MODEL), or "" for automatic."""
    p = PROVIDERS.get(name)
    raw = setting(p.model_env) if p else ""
    if name == "anthropic":
        return raw or "claude-sonnet-5"
    return "" if raw.lower() in ("", "auto") else raw


def base_url(name: str) -> str:
    p = PROVIDERS[name]
    return p.base.replace("{account}", setting("CLOUDFLARE_ACCOUNT_ID")) if "{account}" in p.base else p.base


# ---------- which models can be used at all ----------

# Never chat models: speech, pictures, search indexes and safety filters.
NOT_CHAT = re.compile(
    r"embed|whisper|tts|speech|audio|transcri|voice|voxtral|orpheus|playai|"     # speech in or out
    r"image|vision|-vl\b|-vl-|\bvl-|pixtral|diffusion|flux|sdxl|dall-?e|imagen|veo|video|"   # pictures (vision-first models)
    r"guard|moderation|safety|shield|prompt-?guard|"                    # safety classifiers, not answerers
    r"rerank|retriev|ocr|\bbge-|\be5-|\bgte-|nomic|minilm|colbert|"      # search and document tools (embedders)
    r"compound|search|deep-?research|"                                 # agent systems with their own tools and quotas
    r"realtime|-live\b|computer-use|robotics", re.I)

# Specialists that write poor English prose or JSON for our jobs.
SPECIALIST = re.compile(
    r"code|codestral|devstral|coder|starcoder|math|"      # code and maths specialists
    r"translat|nllb|m2m|seamless|"                        # translators
    r"reward|\bprm\b|lora|-base\b|instruct-base", re.I)

# Built for a language other than English (they answer English questions badly or in the wrong language).
NON_ENGLISH = re.compile(
    r"allam|jais|falcon-?arabic|"               # Arabic
    r"swallow|elyza|plamo|llm-jp|"              # Japanese
    r"kanana|hyperclova|"                       # Korean
    r"baichuan|chatglm|"                        # Chinese
    r"sea-?lion|typhoon|taide|bielik", re.I)

# Models that think before they answer always need far more reply room; the long `-r1`/distill ones also ignore
# requests to keep it short, so they're left out up front rather than measured.
ALWAYS_LONG_THINKERS = re.compile(r"-r1\b|r1-|distill|qwq|deepseek-reasoner|-thinking\b|thinking-", re.I)


def size_b(model_id: str) -> float | None:
    """Parameters in billions, when the name says (llama-3.1-8b → 8, qwen3-30b-a3b → 30, gemma-3n-e4b → 4).
    Names with an active count (a3b, a22b) are counted by their total."""
    m = model_id.lower().split("/")[-1]
    sizes = [float(x) for x in re.findall(r"(?<![a-z0-9.])e?(\d+(?:\.\d+)?)b(?![a-z0-9])", m.replace("_", "-"))]
    sizes += [float(x) * 1000 for x in re.findall(r"(?<![a-z0-9.])(\d+(?:\.\d+)?)t(?![a-z0-9])", m)]
    return max(sizes) if sizes else None


TINY_B = 8.0            # under about 8B parameters, answers to finance questions are too often wrong


def unusable(name: str, model_id: str) -> str | None:
    """Why a listed model isn't tried, or None if it is."""
    p = PROVIDERS[name]
    m = model_id or ""
    if p.allow and not re.search(p.allow, m, re.I):
        return "not free"
    if p.deny and re.search(p.deny, m, re.I):
        return "not for this job"
    if NOT_CHAT.search(m):
        return "not a chat model"
    if SPECIALIST.search(m):
        return "specialist"
    if NON_ENGLISH.search(m):
        return "not English-first"
    if ALWAYS_LONG_THINKERS.search(m):
        return "thinks too long"
    s = size_b(m)
    if s is not None and s < TINY_B:
        return "too small"
    return None


# ---------- models that reason before answering ----------
_THINKERS = ("gptoss", "qwen3", "qwen35", "deepseekr", "magistral", "thinking", "reasoning", "gemma4", "glm4", "glm5",
             "kimik2", "minimax", "nemotron", "gpt5", "phi4reasoning", "seedoss", "hermes4")


def thinks(model: str) -> bool:
    """A model that may reason before answering (gpt-oss, qwen-3.x, gemma-4, MiniMax, o-series…): it needs room for
    both, and is asked to think little where the provider allows it. Qwen's "instruct" builds don't think."""
    m = (model or "").lower()
    flat = re.sub(r"[^a-z0-9]", "", m)
    if "qwen3" in flat and "instruct" in flat and "thinking" not in flat:
        return False
    if re.search(r"(^|/)o\d(-|$)", m):
        return True
    return any(k in flat for k in _THINKERS)


def family(model: str) -> str:
    """The model family, for the provider-specific "don't think" switches."""
    flat = re.sub(r"[^a-z0-9]", "", (model or "").lower())
    for fam, keys in (("gpt-oss", ("gptoss",)), ("qwen", ("qwen",)), ("glm", ("glm",)), ("nemotron", ("nemotron",)),
                      ("deepseek", ("deepseek",)), ("minimax", ("minimax",)), ("openai-reasoning", ("gpt5",))):
        if any(k in flat for k in keys):
            return fam
    if re.search(r"(^|/)o\d(-|$)", (model or "").lower()):
        return "openai-reasoning"
    return ""


# ---------- how strong a model is, before it's measured ----------
_STRONG = re.compile(r"70b|72b|90b|120b|235b|405b|480b|671b|maverick|deepseek-v3|deepseek-chat|mistral-large|mistral-medium|"
                     r"gpt-4\.1(?!-nano|-mini)|gpt-4o(?!-mini)|gpt-5|gemini-[\d.]+-flash(?!-lite)|kimi|glm-[45]|qwen3-235|"
                     r"llama-4|nemotron-super|nemotron-ultra|command-a", re.I)


def strength(model: str) -> int:
    """+1 for a model known to read long documents well, -1 for a small one, 0 when unsure. Measurement decides the
    rest; this only breaks ties between models that answer the test equally well."""
    s = size_b(model)
    if _STRONG.search(model or "") or (s is not None and s >= 60):
        return 1
    if (s is not None and s < 20) or re.search(r"lite|mini|nano|small|instant|flash-8b|nemo\b", model or "", re.I):
        return -1
    return 0
