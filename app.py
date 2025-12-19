import os, re, json, sqlite3, time, random, asyncio, threading
from typing import List, Optional, Dict, Any, Tuple

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ================== ENV ==================
load_dotenv(override=True)
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

MODEL        = os.getenv("QR_MODEL", "gpt-4o-mini")
TEMPERATURE  = float(os.getenv("QR_TEMPERATURE", "0.25"))
MAX_TOKENS   = int(os.getenv("QR_MAX_TOKENS", "220"))
USER_NAME    = os.getenv("QUICKRIZZ_NAME", "Wingman").strip()
USER_STYLE   = os.getenv("QUICKRIZZ_STYLE", "playful, concise, confident, flirty").strip()
CONTEXT_WINDOW = 10 # how many prior messages to consider
# anti-429 controls
MIN_INTERVAL_MS   = int(os.getenv("QR_MIN_INTERVAL_MS", "2500"))
MAX_RETRIES       = int(os.getenv("QR_MAX_RETRIES", "4"))
BACKOFF_BASE_SEC  = float(os.getenv("QR_BACKOFF_BASE", "0.9"))
BACKOFF_CAP_SEC   = float(os.getenv("QR_BACKOFF_CAP", "8.0"))

# ===== Memory knobs =====
MEM_ENABLE         = os.getenv("QR_MEM_ENABLE", "1") == "1"
MEM_TOPK_KEYS      = int(os.getenv("QR_MEM_TOPK_KEYS", "5"))       # max similar keys to consider
MEM_MIN_JACCARD    = float(os.getenv("QR_MEM_MIN_JACCARD", "0.22"))# similarity threshold
MEM_MIN_LEN        = int(os.getenv("QR_MEM_MIN_LEN", "6"))         # ignore very short inputs
MEM_PREF_LIKED     = os.getenv("QR_MEM_PREF_LIKED", "1") == "1"    # prefer rating == "Y"
MEM_MERGE_LIMIT    = int(os.getenv("QR_MEM_MERGE_LIMIT", "3"))     # how many memory lines to inject

# ===== Default heat floor =====
MIN_SPICE_FLOOR    = int(os.getenv("QR_MIN_SPICE_FLOOR", "2"))     # 0–3; assume flirty by default

# ================== APP & CORS ==================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ================== DB for feedback ==================
DB_PATH = os.getenv("QR_DB", "qrizz.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY,
  ts INTEGER,
  stage TEXT,
  latest TEXT,
  option TEXT,
  label TEXT,
  meta  TEXT
)
""")
conn.commit()
_db_lock = threading.Lock()

# --- Commit store json file ---
COMMITS_PATH = os.getenv("QR_COMMITS", "qr_commits.json")

def _load_commits():
    try:
        with open(COMMITS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_commits(obj):
    with open(COMMITS_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ================== MODELS ==================
class Msg(BaseModel):
    role: str   # "them" or "you"
    text: str

class SuggestReq(BaseModel):
    context: List[Msg] = []
    n: int = 3
    site: Optional[str] = None
    thread: Optional[str] = None  #what does optional do here
    spice: Optional[int] = None

class FeedbackReq(BaseModel):
    stage: str
    latest: str
    option: str                                                 #whats difference between feedbackReq and commitReq
    label: str = "clicked"    # also accept "up"/"down"
    meta: Optional[Dict[str, Any]] = None

class CommitReq(BaseModel):
    text: str                 # latest incoming text 
    stage: str                # stage at time of commit
    heat: int                 # spice level 0-4
    options: List[Dict[str, Any]]  # [{ "text":..., "spice":..., "rating":"yes"/"no", "reason":"..." }]

# ================== HELPERS ==================
STAGES = ["opener","banter","rapport","logistics","plan","confirm","wrap"]

def clamp(s: str, max_chars=350) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())[:max_chars]

def stitched(history: List[Msg], k=15) -> str:
    xs = history[-k:]
    return "\n".join(f"{m.role}: {clamp(m.text)}" for m in xs)

def stitched_k(history: List[Msg], k=CONTEXT_WINDOW) -> str:
    xs = history[-k:]
    return "\n".join(f"{m.role}: {clamp(m.text)}" for m in xs)

def last_incoming(history: List[Msg]) -> str:
    for m in reversed(history):
        if m.role == "them" and m.text.strip():
            return clamp(m.text)
    return ""

def clean_option(s: str) -> str:
    s = s.replace(" Enter", " ")
    s = re.sub(r"\s+", " ", s or "")
    return s.strip()

# ---- Slang glossary ----
SLANG_PATH = os.getenv("QR_SLANG", "qr_slang.json")
_SL_DEFAULT = {
    "dyk":"do you know","fomo":"fear of missing out","ftw":"for the win", "dy": "do you", 
  "idc":"i don't care","idk":"i don't know","lol":"laughing out loud",
  "lmao":"laughing my ass off","lmfao":"laughing my fucking ass off",
  "wtf":"what the fuck","wyd":"what are you doing","wys":"what's up",
  "stfu":"shut the fuck up","su":"shut up","ngl":"not gonna lie","tbh":"to be honest",
  "icl":"i can't lie","af":"as fuck","asl":"as hell","brb":"be right back",
  "btw":"by the way","imo":"in my opinion","imho":"in my honest opinion",
  "iirc":"if i recall correctly","nvm":"never mind","rn":"right now","bc":"because","bs":"bullshit",
  "fr":"for real","bet":"okay","cap":"lie","no cap":"no lie","ong":"on god","smh":"shaking my head",
  "ttyl":"talk to you later","gm":"good morning","gn":"good night","g2g":"got to go",
  "wya":"where you at","hbu":"how about you","wbu":"what about you",
  "tl;dr":"too long didn't read","rofl":"rolling on the floor laughing",
  "ffs":"for fuck's sake","fml":"fuck my life","dead":"that's so funny i'm dead","ded":"that's so funny i'm dead",
  "iykyk":"if you know you know","lowkey":"subtly","highkey":"openly","mood":"same vibe",
  "sus":"suspicious","cringe":"embarrassing","based":"confidently true","mid":"mediocre","goated":"greatest of all time",
  "ate":"did amazingly well","slay":"crushed it","oomf":"one of my followers","ratio":"owned by replies",
  "delulu":"delusional","rizz":"charisma","skibidi":"absurd silly meme",
  "omw":"on my way","eta":"estimated time of arrival","dm":"direct message","pm":"private message",
  "tfti":"thanks for the invite","otp":"on the phone","pov":"point of view","ft":"facetime","irl":"in real life",
  "yk":"you know","ykwim":"you know what i mean","ymmv":"your mileage may vary",
  "yw":"you're welcome","np":"no problem","glhf":"good luck have fun","gg":"good game", "gyatt": "butt", "chonk":"big", 
  "pum": "vagina", "pussy": "vagina", "dih" : "penis", 
}
def _load_slang():
    try:
        with open(SLANG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and data:                             # checks if data is in slang dictionary
                return {str(k).lower(): str(v).lower() for k,v in data.items()}
    except Exception:
        pass
    return _SL_DEFAULT
_SLANG = _load_slang()
# longest first; allow tokens like "tl;dr"
_keys = sorted(_SLANG.keys(), key=len, reverse=True)
_pat  = re.compile(r'\b(' + '|'.join(re.escape(k).replace(r'\;',';') for k in _keys) + r')\b', re.I)
def expand_slang(s: str) -> str:
    if not s: return s
    def repl(m):                #make it so that it knows what lolllll is or something, rn it just sees lol
        k = m.group(0).lower()
        return _SLANG.get(k, k)
    return _pat.sub(repl, s)

def stitched_k_exp(history: List[Msg], k=CONTEXT_WINDOW) -> str:
    xs = history[-k:]
    return "\n".join(f"{m.role}: {expand_slang(clamp(m.text))}" for m in xs)

# ===== Memory index (approx lookup from qr_commits.json) =====
_WORD_RX = re.compile(r"[a-z0-9']+")
def _norm_text(s: str) -> str:
    s = expand_slang(clamp(s).lower())
    s = re.sub(r"[^\w\s';:/-]+", " ", s)  # keep simple word chars
    return re.sub(r"\s+", " ", s).strip()

def _trigrams(tokens: List[str]) -> List[str]:
    if len(tokens) < 3:  # backoff to unigrams/bigrams for very short
        return tokens[:]
    return [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens)-2)]

def _tokens(s: str) -> List[str]:
    return _WORD_RX.findall(s)

def _jaccard(a: set, b: set) -> float:
    if not a or not b: return 0.0
    inter = len(a & b)
    if inter == 0: return 0.0
    return inter / float(len(a | b))

class MemIndex:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {}
        self.key_grams: Dict[str, set] = {}
        self.postings: Dict[str, set] = {}  # gram -> set(keys)
        self._load_and_build()

    def _load_and_build(self):
        self.data = _load_commits()
        self.key_grams.clear()
        self.postings.clear()
        for key in self.data.keys():
            nk = _norm_text(key)
            toks = _tokens(nk)
            grams = set(_trigrams(toks) or toks)
            self.key_grams[key] = grams
            for g in grams:
                self.postings.setdefault(g, set()).add(key)
        print(f"[QR][mem] built index keys={len(self.data)} grams={len(self.postings)}")

    def reload(self):
        self._load_and_build()

    def add_or_update_key(self, key: str, items: List[Dict[str, Any]]):
        # update in-memory structures after /commit
        self.data[key] = {"items": items}
        nk = _norm_text(key)
        toks = _tokens(nk)
        grams = set(_trigrams(toks) or toks)
        # remove old postings if existed
        old = self.key_grams.get(key)
        if old:
            for g in old:
                s = self.postings.get(g)
                if s:
                    s.discard(key)
        # add new
        self.key_grams[key] = grams
        for g in grams:
            self.postings.setdefault(g, set()).add(key)

    def similar(self, latest: str, topk: int = MEM_TOPK_KEYS) -> List[Tuple[str, float]]:
        if not MEM_ENABLE: return []
        if not latest or len(latest) < MEM_MIN_LEN: return []
        qn = _norm_text(latest)
        qtoks = _tokens(qn)
        qgrams = set(_trigrams(qtoks) or qtoks)
        if not qgrams: return []
        # candidate gather
        cand_keys: set = set()
        for g in qgrams:
            if g in self.postings:
                cand_keys |= self.postings[g]
        scored: List[Tuple[str, float]] = []
        for k in cand_keys:
            kg = self.key_grams.get(k) or set()
            sc = _jaccard(qgrams, kg)
            if sc >= MEM_MIN_JACCARD:
                scored.append((k, sc))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:topk]

    def best_lines_for(self, key: str, limit: int = 3) -> List[str]:
        entry = self.data.get(key) or {}
        items = entry.get("items") or []
        # prefer rating == "Y"
        if MEM_PREF_LIKED:
            pos = [it.get("resp") for it in items if (isinstance(it, dict) and (it.get("rating") == "Y"))]
            if pos:
                return [clean_option(x) for x in pos if x][:limit]
        # else fall back to any historical
        any_lines = [it.get("resp") for it in items if isinstance(it, dict)]
        return [clean_option(x) for x in any_lines if x][:limit]

MEM = MemIndex(COMMITS_PATH)

# ---- Style rubric + exemplars ----
STYLE_RUBRIC = """
You are a gen Z dating GURU. You know exactly how to  reply to dating app messages written by people in their late teens
and early twenties.
Write ultra-short dating replies that are (a) flirty (b) direct (c) confident
(d) witty (e) teasing. Avoid corny or formal tone. Prefer decisive verbs and concrete moves.
Length: 4–10 words. No markdown, No quotes, No emdash, No dash, No semi-colons, No exclamation marks, No periods, No links.
Never defer decisions (“you pick”, “your call”, “up to you”, “whatever works”).
Do not re-introduce my name unless LATEST explicitly asks identity.
Never say "hey" with more than one y, or "hi" with more than one i.
Heat policy (progression):
- heat 0–1: playful/casual; respectful. Try to push toward heat 2 fast. 
- heat 2: escalate: bolder teasing, clearer intent. Allow one 😉 or 😏 at the END. Try to push toward heat 3.
- heat 3: very flirty, confident push toward meeting/physical proximity. One 😉 or 😏 allowed at END.
- heat 4: direct, consent-affirming, proximity-forward, concrete plan. No coyness. Very sexual undertones extremely encouraged if appropriate.

Stay strictly on-topic to IDEA and GOAL; LATEST matters but do not lose the IDEA.
Return JSON: {"options":["...", "..."]}.
"""

EXEMPLARS = [
    ("She: i'm in bed rn", {"options": [
        "Move over, I'm stealing the warm side",
        "when am i pulling up?",
        "tuck you in or keep you up when i come over?",
    ]}),
    ("She: hey, wyd tmrw?", {"options": [
        "nm, I wouldnt mind some company",
        "let's grab that coffee we mentioned"
    ]}),
    ("She: not sure yet", {"options": [
        "I’ll decide. You’ll like it"
    ]}),
    ("She: that’s bold", {"options": [
        "Confidence looks good on us"
    ]}),
    ("She: where are you from?", {"options": [
        "Toronto, wbu?", "Toronto, u want a tour?"
    ]}),
    ("She: brunch sounds great, where are we going?", {"options": [
        "Cafe Luna 11:30, I’ll grab a table",
        "Union Market at 12. I’ll meet you out front"
    ]}),
]

# ========= LEXICONS / CUES =========
DECISIVE_VERBS = r"\b(pull|bring|call|pick|book|meet|come|come over|sneak|steal|decide|swing|drop|slide|plan)\b"
DEFERRALS      = r"\b(you pick|your call|up to you|whatever works|either works|you decide|idc|i don'?t care)\b"
LIGHT_SPICE    = r"\b(warm|bed|steal|tuck|keep you up)\b"  # removed "snacks" to reduce usage
HEDGES         = r"\b(maybe|kinda|sort of|might|could|i guess)\b"
WINK_EMOJI_RX  = r"[😉😏]"
INNUENDO_RX    = r"\b(cuddle|wild|kiss|closer|blanket|spoon|massage|back rub|lap|whisper|stay over|come over|movie night|truth or dare)\b"

# ====== EXTRA HEAT CUES  ======
DESIRE_RX     = re.compile(r"\b(want you|need you|can'?t wait|begging for|crave|dying to|i aim to please|please me)\b", re.I)
TOUCH_RX      = re.compile(r"\b(kiss|touch|feel|grab|pull you|hold (you|me)|hands? on|lips?|neck|waist|hips?)\b", re.I)
PROX_RX       = re.compile(r"\b(come over|pull up|at (my|ur|your) place|now|tonight|after|later|swing by|on my way)\b", re.I)
BODY_RX       = re.compile(r"\b(neck|lips?|thighs?|waist|hips?|back|skin|hair)\b", re.I)
PERMISSION_RX = re.compile(r"\b(if you'?re into it|if you want|want me to|should i|can i)\b", re.I)
EXCLUSIVE_RX  = re.compile(r"\b(just us|just you and me|our night|my place|your place)\b", re.I)
SENSORY_RX    = re.compile(r"\b(warm|soft|slow|close|closer|whisper|taste|smell|skin|breathe)\b", re.I)
COMMAND_RX    = re.compile(r"\b(come|pull|kiss|bring|meet|slide|sneak|decide|book)\b", re.I)
TEASE_RX      = re.compile(r"\b(tease|teasing|make you beg|earn it|behave|be good)\b", re.I)
WINK_OR_SMIRK = re.compile(r"[😉😏]|;\)", re.U)

# erotic/consent questions & readiness
EROTIC_Q_RX   = re.compile(r"\b(what are you (gonna|going to) do to me|how (are|r) you (gonna|going to) please me|how will you please me)\b", re.I)
READINESS_RX  = re.compile(r"\b(i('|’)?m so ready|i('?m)? ready|can'?t wait|don'?t keep me waiting)\b", re.I)
INVITE_RX     = re.compile(r"\b(when are we meeting|so when|let'?s meet|set a time)\b", re.I)

# legacy soft cues
GREEN_UP = re.compile(r"(?:\b(dare|bold|come|pull up|when|where|tonight|in bed|miss you|wink)\b|;\)|😉|😏)", re.I)
RED_DOWN = re.compile(r"\b(busy|tired|idk|not sure|another time|later)\b", re.I)

IDEA_TRIGGER   = re.compile(r"\b(idea|plan|what('?s|s)\s*the\s*plan|what.*doing|what.*we.*doing)\b", re.I)

# ---- Opener hygiene ----
BAD_GREETS_RX   = re.compile(r"\b(he+y+|hi+i+)\b", re.I)   # e.g., heyyy, hiii
OPENER_BAN_RX   = re.compile(r"\b(weekend|plan|ready|fun|meet|date|tonight|tmr|tomorrow|call|book|pick|movie|walk|come over)\b", re.I)

# ===== Spice-4 triggers =====
SPICE4_LIST = [
  r"\bexplore me\b",
  r"\bmake me( yours)?\b",
  r"\bdo (me|it to me)\b",
  r"\b(take|use) me\b",
  r"\bhave your way with me\b",
  r"\bi want you inside me\b",
  r"\bput it in\b",
  r"\bi'?m (all )?yours( tonight)?\b",
  r"\b(come )?claim me\b",
  r"\bmake me (beg|scream)\b",
  r"\b(ruin|destroy) me\b",
  r"\b(hands on|touch) (me|my)\b",
  r"\bkiss me (now|everywhere)\b",
  r"\b(come over|pull up) now\b",
  r"\bi'?m ready for you\b|\btake me now\b",
  r"\bi want all of you\b|\bgive it to me\b",
  r"\bdo your worst\b",
  r"\b(harder|deeper|faster|don'?t stop)\b",
  r"\b(you can|you should|i want you to)\s+(?:kiss|touch|pin|choke|spank|grab|hold|take)\b",
  r"\b(mmm+|god yes|ugh yes)\b",
  r"(?:🍑|🍆|💦|👅|🫦)+(?:\s*(?:now|tonight))?"
]
SPICE4_RX = re.compile("|".join(SPICE4_LIST), re.I)

# ========= FEEDBACK-AWARE FEW-SHOTS =========
def liked_exemplars(k: int = 6, stage: Optional[str] = None):
    try:
        rows = conn.execute(
            "SELECT latest, option, stage FROM feedback WHERE label IN ('up','clicked','like','liked') "
            "ORDER BY ts DESC LIMIT ?", (max(6, k),)
        ).fetchall()
        out = []
        for latest, opt, st in rows:
            latest = latest or ""
            opt = (opt or "").strip()
            if not (latest and opt):
                continue
            if stage and st and st != stage:
                continue
            out.append( (f"She: {latest}", {"options":[opt]}) )
        return out
    except Exception:
        return []

# ---- Opener fallbacks ----
OPENER_FALLBACKS = [
    "Opener Fallback Triggered"
]

# ========= SCORER =========
def score_line(s: str, spice: int) -> float:
    if not s: return -999
    t = s.strip()
    words = len(t.split())
    score = 0.0
    if 4 <= words <= 10: score += 2.0
    elif words <= 13:    score += 1.0
    else:                score -= 1.5
    if re.search(DECISIVE_VERBS, t, flags=re.I): score += 1.2
    score += 0.8 if t.endswith("?") else 0.3
    if re.search(LIGHT_SPICE, t, flags=re.I): score += (0.6 if spice <= 1 else 1.0)
    if spice >= 2 and re.search(INNUENDO_RX, t, flags=re.I): score += (1.1 if spice == 2 else 1.6)
    if re.search(HEDGES, t, flags=re.I): score -= 1.0
    if t[0:1].isupper() and t.endswith("."): score -= 0.6
    if ";" in t: score -= 2.5
    if re.search(DEFERRALS, t, flags=re.I): score -= 4.0
    has_wink = re.search(WINK_EMOJI_RX, t)
    if has_wink and spice >= 2: score += 0.9
    if has_wink and spice < 2: score -= 1.2
    return score

def strip_winks(s: str) -> str:
    return re.sub(WINK_EMOJI_RX, "", s)

# ---- single-flight + throttle state ----
_openai_lock = asyncio.Semaphore(1)
_last_call_ms = 0

async def _throttle():
    global _last_call_ms
    now = int(time.time() * 1000)
    wait_ms = (_last_call_ms + MIN_INTERVAL_MS) - now
    if wait_ms > 0:
        await asyncio.sleep(wait_ms / 1000.0)
    _last_call_ms = int(time.time() * 1000)

async def openai_chat_async(messages, temperature=0.2, max_tokens=200, timeout=18) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "n": 1}
    async with _openai_lock:
        await _throttle()
        attempt, last_err = 0, None
        while attempt < MAX_RETRIES:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("retry-after")
                    if ra and ra.isdigit():
                        delay = min(BACKOFF_CAP_SEC, int(ra))
                    else:
                        base = BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                        delay = min(BACKOFF_CAP_SEC, base + random.uniform(0, 0.75))
                    print(f"[QR][openai] {r.status_code} -> backoff {delay:.2f}s (attempt {attempt}/{MAX_RETRIES})")
                    last_err = r.text
                    await asyncio.sleep(delay); continue
                r.raise_for_status()
                data = r.json()
                content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
                print(f"[QR][openai] ok in attempt {attempt}, len={len(content)}")
                return content
            except Exception as e:
                last_err = str(e)
                delay = min(BACKOFF_CAP_SEC, BACKOFF_BASE_SEC + random.uniform(0, 0.5))
                print(f"[QR][openai][exception] {type(e).__name__}: {e} -> sleep {delay:.2f}s (attempt {attempt}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
        print("[QR][openai][giveup]", last_err)
        return ""

async def openai_chat_json(messages, temperature=0.7, max_tokens=120, timeout=18) -> Dict[str, Any]:
    content = await openai_chat_async(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    try:
        start = content.find("{"); end = content.rfind("}")
        if start != -1 and end != -1: content = content[start:end+1]
        return json.loads(content)
    except Exception:
        return {}

# ================== SPICE CUES ==================
def infer_spice(history: List[Msg], latest: str, k:int=CONTEXT_WINDOW) -> Tuple[int, Dict[str,Any]]: #infers spice level from 0-4 based on cues
    """
    Heuristic heat detector over last k turns:
    - weighted cues: desire, touch, proximity, body, permission, exclusivity, sensory, command, tease, wink,
      erotic questions, readiness/consent, invites
    - reciprocity bonus (both roles hot)
    - softer cooling from RED_DOWN to avoid false drops
    - Spice-4 triggers escalate above level 3 when explicit invite phrases appear
    """
    window = history[-k:]
    window_text = " ".join(m.text for m in window if m.text).lower()
    window_text = expand_slang(window_text)  
    latest_low  = expand_slang((latest or "").lower()) 

    score = 1.0
    hits: List[Tuple[str,str]] = []

    def bump(rx: re.Pattern, w: float, tag: str):
        nonlocal score
        if rx.search(window_text):
            score += w
            hits.append((tag, "win"))

    # strong up-signals
    bump(DESIRE_RX,     1.0, "desire")
    bump(TOUCH_RX,      1.0, "touch")
    bump(PROX_RX,       0.9, "proximity")
    bump(BODY_RX,       0.7, "body")
    bump(PERMISSION_RX, 0.4, "permission")
    bump(EXCLUSIVE_RX,  0.4, "exclusive")
    bump(SENSORY_RX,    0.6, "sensory")
    bump(COMMAND_RX,    0.4, "command")
    bump(TEASE_RX,      0.6, "tease")
    bump(WINK_OR_SMIRK, 0.8, "wink")
    bump(EROTIC_Q_RX,   1.2, "erotic_q")
    bump(READINESS_RX,  0.9, "readiness")
    bump(INVITE_RX,     0.5, "invite")

    # reciprocity bonus (both sides spicy)
    them_text = expand_slang(" ".join(m.text for m in window if m.role=="them")).lower()
    you_text  = expand_slang(" ".join(m.text for m in window if m.role=="you")).lower()
    mutual = 0
    for rx in (DESIRE_RX, TOUCH_RX, PROX_RX, TEASE_RX, WINK_OR_SMIRK, EROTIC_Q_RX, READINESS_RX):
        if rx.search(them_text) and rx.search(you_text): mutual += 1
    if mutual:
        score += 0.45 * mutual
        hits.append(("mutual", str(mutual)))

    # consecutive-hot bonus
    last4 = [m for m in window if m.text][-4:] # if last 4 consecutive messages from them are spicy, gives streak bonus 
    hot_theirs = sum(1 for m in last4 if m.role=="them" and ( 
        DESIRE_RX.search(m.text.lower()) or TOUCH_RX.search(m.text.lower()) or
        EROTIC_Q_RX.search(m.text.lower()) or READINESS_RX.search(m.text.lower()) or
        WINK_OR_SMIRK.search(m.text) 
    ))
    if hot_theirs >= 2: #if at least 2 of their last 4 messages are spicy, add .8 to score
        score += 0.8
        hits.append(("streak", str(hot_theirs)))

    # legacy soft cues 
    red_hit = False
    if GREEN_UP.search(window_text): score += 0.6; hits.append(("green_up","1"))
    if RED_DOWN.search(window_text): 
        score -= 0.35; hits.append(("red_down","1")); red_hit = True

    # latest nudge
    if any(rx.search(latest_low) for rx in (DESIRE_RX, TOUCH_RX, PROX_RX, TEASE_RX, WINK_OR_SMIRK, EROTIC_Q_RX, READINESS_RX)):
        score += 0.8; hits.append(("latest_hot","1"))

    # thresholds tuned (base 0–3)
    if score >= 3.5: lvl = 4
    elif score >= 2.6: lvl = 3
    elif score >= 1.8: lvl = 2
    elif score >= 1.1: lvl = 1
    else: lvl = 0

    # ---- DEFAULT HEAT FLOOR unless cooling cues --
    if not red_hit:
        lvl = max(lvl, MIN_SPICE_FLOOR)

    # ---- Spice-4 escalation on explicit invites  ----
    if lvl >= 3 and (SPICE4_RX.search(window_text) or SPICE4_RX.search(latest_low)):
        lvl = 4
        hits.append(("spice4", "trigger"))

    dbg = {"score": round(score,2), "hits": hits[-10:], "latest": latest, "red_hit": red_hit, "level": lvl}
    print("[QR][spice]", dbg)
    return lvl, dbg

def temp_for_spice(spice: int) -> float:
    return {0: 0.2, 1: 0.35, 2: 0.5, 3: 0.65, 4: 0.75}.get(int(spice), 0.35) #what does this do

def mode_guide(spice: int) -> str:
    guides = {
        0: "Mode: Casual. Keep it light, no emoji, soft tease only.",
        1: "Mode: Playful. Gentle tease allowed, no emoji.",
        2: "Mode: Flirty. Suggestive ideas, decisive invites, one wink emoji allowed.",
        3: "Mode: Bold. Cheeky, proximity-forward, one wink emoji allowed; keep respectful.",
        4: "Mode: Charged. Consent-affirming, direct, concrete proximity/plan; no coyness.",
    }
    return guides.get(int(spice), guides[1])

# ================== STAGE : FORWARD ONLY ==================
STAGE_INDEX = {s:i for i,s in enumerate(STAGES)}

def heuristic_stage_from_history(history: List[Msg]) -> Tuple[str, Dict[str,Any]]: # finds stage based on keywords
     #this is bugged gotta fix this make it a general wieght not just if it discovers a word
     #maybe have a floor, like cr arenas. if you get to a later stage, you cant go back
    text = " ".join((m.text or "") for m in history[-CONTEXT_WINDOW:]).lower()
    text = expand_slang(text)  
    idx = 0
    why = []
    if re.search(r"\b(hey|hi|hello)\b", text): idx = max(idx, STAGE_INDEX["opener"])
    if re.search(r"\b(lol|haha|jk|tease|cute|music|movie)\b", text): 
        idx = max(idx, STAGE_INDEX["banter"])
    if re.search(r"\b(i like|i love|that’s bold|you’re fun|miss you|attracted)\b", text):
        idx = max(idx, STAGE_INDEX["rapport"]); why.append("rapport-cues")
    if re.search(r"\b(when|what time|tonight|tmr|tomorrow|where|which place)\b", text):
        idx = max(idx, STAGE_INDEX["logistics"]); why.append("time/place-cues")
    if re.search(r"\b(let'?s|lets)\s+(meet|hang|grab|do|cook|watch|walk|picnic)\b", text):
        idx = max(idx, STAGE_INDEX["plan"]); why.append("lets+verb")
    if re.search(r"\b(\d{1,2}(:\d\d)?\s*(am|pm)?)\b", text) or re.search(r"\btonight|8\b", text):
        idx = max(idx, STAGE_INDEX["confirm"]); why.append("explicit time")
    if re.search(r"\b(see you|on my way|locked in|it'?s a date|it’s a date)\b", text):
        idx = max(idx, STAGE_INDEX["wrap"]); why.append("locked-in")
    idx = max(0, min(idx, len(STAGES)-1))
    return STAGES[idx], {"why": why}

async def classify_stage(history: List[Msg], latest: str) -> Tuple[str, Dict[str,Any]]:
    heur_stage, heur_dbg = heuristic_stage_from_history(history)
    sys = "Label the dating chat stage with one token: " + ", ".join(STAGES) + ". Respond with just the token. Prefer later stage when mixed."
    hist_exp = stitched_k_exp(history, CONTEXT_WINDOW)  
    latest_exp = expand_slang(latest)       
    usr = f"HISTORY(last {CONTEXT_WINDOW}):\n{hist_exp}\n\nLATEST:\n{latest_exp}\n\nStage:"
    out = await openai_chat_async([{"role":"system","content":sys},{"role":"user","content":usr}],
                                  temperature=0.1, max_tokens=5)
    token = (out.strip().split()[0] if out else "").lower()
    model_stage = token if token in STAGES else "banter"
    final_stage = STAGES[max(STAGE_INDEX[model_stage], STAGE_INDEX[heur_stage])]
    dbg = {"model_raw": out, "model": model_stage, "heuristic": heur_stage, "chosen": final_stage, **heur_dbg}
    print("[QR][classify_stage]", dbg)
    return final_stage, dbg

# ================== IDEA (LLM-SUMMARIZED) ==================
async def extract_idea(history: List[Msg], latest: str) -> Tuple[str, Dict[str,Any]]:
    sys = "Summarize the core conversational idea/goal in 2–5 words (no punctuation). Examples: 'come over tonight', 'set a time', 'flirty teasing escalates'. Respond with only the phrase."
    hist_exp = stitched_k_exp(history, 20)  
    latest_exp = expand_slang(latest)       
    usr = f"HISTORY(last 20):\n{hist_exp}\n\nLATEST:\n{latest_exp}\n\nIDEA:"
    out = await openai_chat_async([{"role":"system","content":sys},{"role":"user","content":usr}],
                                  temperature=0.2, max_tokens=8)
    idea = clamp(out).strip().lower()
    idea = re.sub(r"[^a-z0-9\s']", "", idea)[:40]
    idea = idea or "move things forward" #can i switch or to and
    return idea, {"raw": out}

# ================== PLAN ==================
def plan_strategy(stage: str) -> Dict[str,str]:
    goals = {
        "opener":"Be warm and share a tiny fact; learn 1 detail. Move conversation forward to banter stage.",
        "banter":"Keep it light; ask one fun, low-stakes question. Move conversation forward to rapport stage. Avoid moving conversations back to opener stage.",
        "rapport":"Mirror tone; reveal small personal detail; invite reciprocity. Move conversation forward to logistics stage. Avoid moving conversations back to banter stage.",
        "logistics":"Move toward concrete times/places; give 2 choices. Move conversation forward to plan stage. Avoid moving conversations back to rapport whenever possible.",
        "plan":"Propose clear plan with day/time + easy out. Move conversation forward to confirm stage. Avoid moving conversations back to logistics whenever possible.",
        "confirm":"Confirm time/place; keep friendly; **at heat≥3 allow a flirty edge and decisive push**. Move conversation forward to wrap stage. Avoid moving conversations back to confirm whenever possible.",
        "wrap":"Close positive; set next touchpoint."
    }
    tips = {
        "opener":"Answer directly; include your name if asked. Move conversation forward to banter stage.",
        "banter":"Avoid interview vibe; one-liner + playful follow-up. Move conversation forward to rapport stage. Avoid moving conversations back to opener stage.",
        "rapport":"Acknowledge their last point; stay under 14 words. Move conversation forward to logistics stage. Avoid moving conversations back to banter stage.",
        "logistics":"Offer A/B times; end with a crisp question. Move conversation forward to plan stage. Avoid moving conversations back to rapport whenever possible.",
        "plan":"Specific, simple, flexible; end with micro-CTA. Move conversation forward to confirm stage. Avoid moving conversations back to logistics whenever possible.",
        "confirm":"Restate details; check fit; keep friendly. If heat≥3, add flirty confidence.",
        "wrap":"Positive note; confirm next step."
    }
    return {"goal": goals.get(stage,"Be natural and move things forward. Always try to progress forward stages. Stages in order from backward to forward: opener, banter, rapport, logistics, plan, confirm, wrap."),
            "tip":  tips.get(stage,"Direct answer; 5–14 words; single CTA.")}

# ================== GENERATE  ==================
async def generate_options(history: List[Msg], latest: str, stage: str, plan: Dict[str,str], spice: int, idea: str, n=1) -> Tuple[List[str], Dict[str, Any]]:
    low = (latest or "").lower()
    ask_name = any(k in low for k in ["name", "who are you", "who’s this", "who is this"])

    idea_hint = ""
    if IDEA_TRIGGER.search(latest):
        idea_hint = (
            "\nIf LATEST asks for an idea/plan, prefer cheeky, proximity-forward ideas, e.g.: "
            "\"movie and blanket on my couch\", "
            "\"truth or dare, loser owes a kiss\", "
            "\"massage trade, then dessert\", "
            "\"pasta night. I’ll cook, you taste-test\", "
            "\"late walk then warm up at mine\"."
        )

    opener_hint = ""
    if stage == "opener":
        opener_hint = (
            "\nFor STAGE opener: keep it light and curious. "
            "No plans, no specifics, no ‘ready/fun/weekend/plan’. "
            "Absolutely avoid elongated greets (heyyy/hiii). "
            "Keep 3–5 words; light, open-ended energy."
        )

    system = (
        "You are QuickRizz.\n" + STYLE_RUBRIC +
        mode_guide(spice) + idea_hint + opener_hint + "\n" +
        (f"If asked name/identity, answer briefly as {USER_NAME}. Otherwise never introduce my name.\n" if USER_NAME else "") +
        f"IDEA: {idea}\n" +
        f"Stage: {stage}. Goal: {plan['goal']}. Tip: {plan['tip']}.\n" +
        "If heat is 3, prioritize flirty proximity-forward lines (suggestive, confident). "
        "If heat is 4, be direct, consent-affirming, and concrete about proximity or plan."
    )

    msgs = [{"role":"system","content":system}]

    for u,a in EXEMPLARS:
        msgs += [{"role":"user","content":u},{"role":"assistant","content":json.dumps(a)}]
    for u,a in liked_exemplars(6, stage):
        msgs += [{"role":"user","content":u},{"role":"assistant","content":json.dumps(a)}]

    user = (
        "HISTORY (latest last, keep context):\n"
        f"{stitched_k(history, CONTEXT_WINDOW)}\n\n"
        "LATEST:\n"
        f"{latest}\n\n"
        "Return 6 candidates in JSON."
    )
    msgs.append({"role":"user","content":user})

    obj = await openai_chat_json(msgs, temperature=temp_for_spice(spice), max_tokens=120)
    cands = obj.get("options", []) if isinstance(obj, dict) else []

    pool: List[str] = []
    for s in cands:
        s = clean_option(str(s)).strip(" \t\n\r-*•")
        if not s: continue
        if BAD_GREETS_RX.search(s):  # block heyyy/hiii in outputs
            continue
        if not ask_name and re.search(r"\b(i\s*'?m|i am)\s+" + re.escape(USER_NAME), s, flags=re.I): continue
        if ";" in s: continue
        if re.search(DEFERRALS, s, flags=re.I): continue
        if spice < 2:
            s = strip_winks(s).strip()
            if not s: continue
        # Soft downweight common words "vibe"/"snack" by simple filter 
        if re.search(r"\b(vibe|snack|snacks)\b", s, flags=re.I):
            continue
        pool.append(s)

    ranked = sorted(pool, key=lambda x: score_line(x, spice), reverse=True)

    # Extra guardrails for openers: keep things vague/non-directional
    if stage == "opener":
        filtered = []
        for line in ranked:
            if BAD_GREETS_RX.search(line):       # no heyyy/hiii
                continue
            if OPENER_BAN_RX.search(line):       # no weekend/plan/ready/fun/etc.
                continue
            if len(line.split()) > 8:
                continue
            filtered.append(line)
        if not filtered:
            filtered = OPENER_FALLBACKS[:]
        ranked = filtered

    chosen = ranked[:max(1, n)]

    dbg = { "generated": cands, "ranked_top": chosen, "latest": latest, "stage": stage, "spice": spice, "idea": idea }
    print("[QR][rank]", json.dumps(dbg, ensure_ascii=False))
    return chosen, dbg

# ===== Forward-only stage enforcer =====
STAGE_ORDER = STAGES[:]  
STAGE_POS = {s:i for i,s in enumerate(STAGE_ORDER)}

# cues that mean progress (booking/time/concrete meet/proximity)
FORWARD_CUES_RX = re.compile(
    r"\b(let'?s|set|pick|book|reserve|lock|plan|meet|grab|call|swing by|pull up|come over|my place|your place|"
    r"tonight|tmr|tomorrow|after|later|7|8|9|10\s*(?:am|pm)?)\b|:\d\d", re.I)

# cues that drag us back to opener/banter (small talk)
REGRESS_CUES_RX = re.compile(
    r"^\s*(he+y+|hi+i+)\b|"
    r"\b(wyd|what'?s up|hbu|wbu|how('s| is)\s*(your\s*)?(day|week)|where (are|r) you from|"
    r"favorite|favourite|music|movie|song|netflix|major|work|study|tell me about)\b",
    re.I)

_NEXT = {s: STAGE_ORDER[i+1] if i+1 < len(STAGE_ORDER) else None for i,s in enumerate(STAGE_ORDER)}
_PREV = {s: STAGE_ORDER[i-1] if i-1 >= 0 else None for i,s in enumerate(STAGE_ORDER)}

# keep original generator
__generate_options_orig = generate_options

async def generate_options(*args, **kwargs):
    """
    Wrapper: calls original generator, then
    - prefers forward-cue lines,
    - blocks regression cues once stage >= logistics,
    - re-ranks with a small forward bonus.
    """
    options, dbg = await __generate_options_orig(*args, **kwargs)

    # unpack current stage (positional args: history, latest, stage, plan, spice, idea, n)
    try:
        stage = (args[2] if len(args) >= 3 else kwargs.get("stage")) or "banter"
    except Exception:
        stage = "banter"

    target = _NEXT.get(stage)
    stage_i = STAGE_POS.get(stage, 1)

    # ----- hard regression filter only when we're past chit-chat -----
    filtered = options[:]
    if stage_i >= STAGE_POS["logistics"]:
        filtered = [o for o in filtered if not REGRESS_CUES_RX.search(o)]

    # ----- forward preference bucket -----
    forward_bucket = [o for o in filtered if FORWARD_CUES_RX.search(o)]
    pool = forward_bucket or filtered or options

    # ----- light forward bonus re-rank -----
    def _bonus(o: str) -> float:
        b = 0.0
        if FORWARD_CUES_RX.search(o): b += 1.2
        if target in ("plan","confirm","wrap") and re.search(r"\b\d{1,2}(:\d\d)?\s*(am|pm)?\b|\btonight|tmr|tomorrow\b", o, re.I):
            b += 0.8
        if target in ("logistics","plan") and re.search(r"\bmy place|your place|meet\b", o, re.I):
            b += 0.5
        return b

    pool = sorted(pool, key=lambda x: _bonus(x), reverse=True)

    # keep original debug + note
    dbg = dict(dbg)
    dbg["forward_enforcer"] = {
        "stage": stage, "target": target,
        "dropped_regress": [o for o in options if o not in filtered],
        "forward_kept": [o for o in pool if FORWARD_CUES_RX.search(o)][:3]
    }
    return pool[:len(options)], dbg

# ================== ROUTES ==================
@app.get("/")
def ok():
    return {"ok": True}

@app.post("/suggest")
async def suggest(req: Request):
    body = await req.json()
    if isinstance(body, dict):
        if "messages" in body and "context" not in body:
            body["context"] = [
                {"role": (m.get("role") or "them"), "text": (m.get("content") or m.get("text") or "")}
                for m in (body.get("messages") or [])
            ]
        elif "context" in body:
            body["context"] = [
                {"role": (m.get("role") or "them"), "text": (m.get("text") or m.get("content") or "")}
                for m in (body.get("context") or [])
            ]

    data = SuggestReq(**(body if isinstance(body, dict) else {}))
    hist = [Msg(role=m.role, text=clamp(m.text)) for m in (data.context or [])][-CONTEXT_WINDOW:]
    latest = last_incoming(hist)
    print("[QR][suggest][input]", {"hist_len": len(hist), "latest": latest})

    if not latest:
        return {"stage":"banter", "plan":plan_strategy("banter"), "options":[], "spice": 1, "debug":{"why":"no latest"}}

    # ===== Memory lookup  =====
    mem_lines: List[str] = []
    if MEM_ENABLE:
        try:
            sims = MEM.similar(latest)
            for key, score in sims:
                lines = MEM.best_lines_for(key, limit=MEM_MERGE_LIMIT)
                for ln in lines:
                    if ln and ln not in mem_lines:
                        mem_lines.append(ln)
                if len(mem_lines) >= MEM_MERGE_LIMIT:
                    break
            if mem_lines:
                print("[QR][mem][hit]", {"keys": [k for k,_ in sims], "picked": mem_lines})
        except Exception as e:
            print("[QR][mem][err]", str(e))

    stage, stage_dbg = await classify_stage(hist, latest)
    plan  = plan_strategy(stage)
    inferred_spice, spice_dbg = infer_spice(hist, latest, k=CONTEXT_WINDOW)
    # allow inferred spice 4; user-specified spice only honored for 0–3
    spice = data.spice if isinstance(data.spice, int) and 0 <= data.spice <= 3 else inferred_spice

    # ---- enforce floor unless RED_DOWN seen ----
    hist_text = " ".join(m.text for m in hist[-CONTEXT_WINDOW:] if m.text).lower()
    if not RED_DOWN.search(hist_text):
        spice = max(spice, MIN_SPICE_FLOOR)

    # ---- Trim memory influence at high spice (H3+)  ----
    if spice >= 3 and mem_lines:
        mem_lines = mem_lines[:1]

    idea, idea_dbg = await extract_idea(hist, latest)

    options, gen_dbg = await generate_options(hist, latest, stage, plan, spice=spice, idea=idea, n=max(1, min(data.n, 3)))
    print("[QR][generate_options]", json.dumps(gen_dbg, ensure_ascii=False))

    # ===== Merge memory-first =====
    merged: List[str] = []
    for s in (mem_lines + options):
        s = clean_option(s)
        if s and s not in merged:
            merged.append(s)
        if len(merged) >= data.n:
            break
    options = merged

    if len(options) < data.n: # fill-ins
        low = latest.lower()
        if "name" in low:
            fill = [f"I'm {USER_NAME}. Nice to meet you",
                    f"I go by {USER_NAME}. You?",
                    f"I’m {USER_NAME}. What should I call you?"]
        elif latest.endswith("?"):
            fill = ["I’m down. What timing works best?",
                    "Can do. Any preference on day/place?",
                    "Let’s pick a time that works"]
        else:
            fill = ["filler triggered"]
        for f in fill:
            f = clean_option(f)
            if ";" in f or re.search(DEFERRALS, f, flags=re.I): continue
            if spice < 2:
                f = strip_winks(f).strip()
                if not f: continue
            if f and f not in options: options.append(f)
            if len(options) >= data.n: break

    resp = {
        "stage": stage,
        "plan": plan,
        "options": options[:data.n],
        "spice": spice,
        "idea": idea,
        "debug": {
            "stage": stage_dbg,
            "spice": spice_dbg,
            "idea": idea_dbg
        }
    }
    print("[QR][suggest][resp]", json.dumps(resp, ensure_ascii=False))
    return resp

@app.post("/feedback")
def feedback(req: FeedbackReq):
    payload = (
        int(time.time()*1000),
        req.stage,
        req.latest,
        req.option,
        req.label,
        json.dumps(req.meta or {})
    )
    with _db_lock:
        conn.execute(
            "INSERT INTO feedback(ts, stage, latest, option, label, meta) VALUES (?,?,?,?,?,?)",
            payload
        )
        conn.commit()
    return {"ok": True}

# ==============COMMIT TO DATABASE==========================
@app.post("/commit")
async def commit(req: Request):
    """
    Writes commits in CMH shape:
    {
      "<latest text>": {
        "items": [
          { "resp": "...", "stage": "...", "heat": 1, "rating": null, "reason": "", "ts": 1762641255643 },
          ...
        ]
      }
    }
    """
    from pathlib import Path

    # read body (no Pydantic model → tolerant)
    try:
        body = await req.json()
    except Exception:
        return {"ok": False, "error": "bad_json"}

    key   = clamp(str(body.get("text", "")))
    stage = str(body.get("stage", "banter")).lower()
    heat  = int(body.get("heat") or 0)
    ts    = int(body.get("ts") or int(time.time() * 1000))
    opts  = body.get("options") or []

    if not key:
        return {"ok": False, "error": "missing text"}
    if not isinstance(opts, list) or not opts:
        return {"ok": False, "error": "missing options"}

    # normalize options -> keep text + optional rating/reason 
    norm: List[Tuple[str, Optional[str], str]] = []  # (resp, rating, reason)
    for o in opts:
        if isinstance(o, str):
            s = clean_option(o)
            r, reason = None, ""
        elif isinstance(o, dict):
            s = clean_option(str(o.get("resp") or o.get("text") or ""))
            r = o.get("rating")
            reason = str(o.get("reason") or "")
        else:
            s, r, reason = "", None, ""
        if s:
            r = (str(r).upper() if isinstance(r, str) else None)
            if r not in ("Y", "N"):
                r = None
            norm.append((s, r, reason))

    # file path
    path = Path(os.getenv("QR_COMMITS", "qr_commits.json"))
    if not path.exists():
        path.write_text("{}", encoding="utf-8")

    # load existing
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        data = {}

    entry = data.get(key) or {}
    items: List[Dict[str, Any]] = entry.get("items") or []

    # de-dupe by resp; update if exists, else append 
    index_by_resp = {it.get("resp"): i for i, it in enumerate(items) if isinstance(it, dict)}
    added = 0
    for s, rating, reason in norm:
        rec = {
            "resp": s,
            "stage": stage,
            "heat": heat,
            "rating": rating,           # preserve incoming rating (Y/N/None)
            "reason": reason or "",
            "ts": ts,
        }
        if s in index_by_resp:
            i = index_by_resp[s]
            old = items[i] if isinstance(items[i], dict) else {}
            if rating is None:                 # keep previous rating if not provided
                rec["rating"] = old.get("rating")
            if not reason:
                rec["reason"] = old.get("reason", "")
            items[i] = rec
        else:
            items.append(rec)
            added += 1

    entry["items"] = items
    data[key] = entry

    # persist
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ===== update in-memory index immediately ====
    try:
        MEM.add_or_update_key(key, items)
        print("[QR][mem][update]", {"key": key, "items": len(items)})
    except Exception as e:
        print("[QR][mem][update][err]", str(e))

    return {"ok": True, "key": key, "added": added, "total_items": len(items)}
#+++++++++++++++++++++++++++++++++++++
