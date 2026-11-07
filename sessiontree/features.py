import math
import re
from collections import Counter, defaultdict

from .lineage import Thread

STOPWORDS = set("""
the a an and or of to in for on with this that these those is are was were
be been being it its as at by from not no but if then than so such can could
should would will may might do does did have has had you your we our they
their them he she his her i me my mine us also use used using into about over
under more most other some any all each both very just only own same too now
how what why when where which who project projects build let make made want
need need get got run running check one two new create created add change
update file files folder directory repo repository code task tasks work working
current start starting show tell give take see look like
""".split())

# CJK bigrams containing these characters are mostly grammar, not topic.
CJK_SKIP_CHARS = set("的了是在我你他她它们这那个什么如何一不有和与或也就都还要会能可以为对把被让给从到向上中里外前后")
CJK_STOP = set("""
项目 这个 一个 我们 什么 怎么 如何 可以 需要 现在 还是 就是 因为 所以 但是
如果 然后 已经 没有 不是 这样 那样 这些 那些 问题 内容 文件 代码 工作 使用
""".split())

ASCII_TOKEN = re.compile(r"[a-z0-9_./:+-]{3,}")
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    lowered = re.sub(r"https?://\S+", " ", lowered)
    words = [
        w for w in ASCII_TOKEN.findall(lowered)
        if w not in STOPWORDS and not w.startswith("http")
    ]
    cjk = CJK_CHAR.findall(lowered)
    bigrams = [
        "".join(cjk[i:i + 2])
        for i in range(len(cjk) - 1)
        if not (set(cjk[i:i + 2]) & CJK_SKIP_CHARS)
        and "".join(cjk[i:i + 2]) not in CJK_STOP
    ]
    return words + bigrams


def is_general(thread: Thread) -> bool:
    return len(thread.user_text.strip()) < 20


def build_vectors(threads: list[Thread]) -> tuple[dict[str, dict[str, float]], list[str]]:
    docs = []  # (root_id, role_weight, Counter)
    general = []
    for thread in threads:
        if is_general(thread):
            general.append(thread.root_id)
            continue
        seen_texts = set()
        for event in thread.events:
            if len(event.text.strip()) < 20:
                continue
            # forks copy the root's messages; count each distinct message once so
            # duplicated history does not inflate document frequency
            key = (event.role, event.text)
            if key in seen_texts:
                continue
            seen_texts.add(key)
            weight = 2.0 if event.role == "user" else 1.0
            docs.append((thread.root_id, weight, Counter(tokenize(event.text))))
        if not any(d[0] == thread.root_id for d in docs):
            general.append(thread.root_id)

    df = Counter()
    for _, _, counter in docs:
        df.update(counter.keys())
    total = len(docs)

    message_vectors = []
    for root_id, weight, counter in docs:
        vec = {
            term: (1 + math.log(count)) * (math.log((total + 1) / (df[term] + 1)) + 1)
            for term, count in counter.items()
            if df[term] <= 0.35 * total
        }
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        message_vectors.append((root_id, weight, {k: v / norm for k, v in vec.items()}))

    acc = defaultdict(lambda: defaultdict(float))
    for root_id, weight, vec in message_vectors:
        for term, value in vec.items():
            acc[root_id][term] += value * weight

    vectors = {}
    for root_id, terms in acc.items():
        norm = math.sqrt(sum(v * v for v in terms.values())) or 1.0
        vectors[root_id] = {k: v / norm for k, v in terms.items()}

    represented = set(vectors) | set(general)
    missing = sorted(t.root_id for t in threads if t.root_id not in represented)
    general.extend(missing)
    return vectors, general
