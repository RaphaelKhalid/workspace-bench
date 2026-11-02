"""Build ``evals/introspection/items_v2.json`` from ``items.json`` (plan 0045; deterministic, no
model, no API call). ``items.json`` is left untouched (D9). Run after
``scripts/introspection_export_vectors.py`` (the ``vectors`` block records the files' sha256).

What v2 adds to v1 (the visible text, the concepts, the seeds and the option ORDER are v1's):

- ``items[].twins`` (inject items): ``{gaussian, cross, beta0}`` ids of the paired controls
  (decision Q12: the gaussian twin voids a hit; cross and beta0 are reported columns).
- 7-option lists: every item's ``options`` and every beta0 ``options_by_cluster`` list gains
  ``mc.CANNOT`` LAST (``mc.options_with_cannot``; never shuffled in).
- ``equivalents``: ``{concept: [cluster-mates that count as it]}`` (Q12, symmetric, no
  one-directional rows), A(c) = {c} | equivalents[c].
- ``concepts[].surface_forms`` (the concept's label, singular / plural, irregulars and curated
  Chinese translations of >= 2 characters; the regex twin leg's forms) and
  ``concepts[].extra_forms`` (non-option words that name the concept, rendered as "also").
- ``renders[*].lite``: the reads=lite site, absolute positions (protocol: the final token, the
  open quote; neutral: ``grid[1]``, the ``\\n`` after ``<|im_end|>``).
- ``items[].vector.row`` / ``vectors``: the shipped ``.npy`` rows and the files' sha256.

    uv run --no-sync python scripts/introspection_build_v2.py
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from wsbench import mc  # noqa: E402

V1 = REPO / "evals/introspection/items.json"
V2 = REPO / "evals/introspection/items_v2.json"
VEC = "evals/introspection/vectors"
FROZEN = "2026-10-30"

# ---------------------------------------------------------------- Q12 equivalents (frozen)

# Camila's groups (decision Q12) as cliques / pairs, then the spec-proposed pairs (plan 0045
# §2.2; listed on the site under "Decisions taken (override if you disagree)")
CLIQUES = [
    ("machines", "gadgets", "contraptions"),
    ("trees", "leaves", "forests"),
    ("youths", "teenagers", "children"),
]
PAIRS_Q12 = [("robots", "machines"), ("bags", "backpacks")]
PAIRS_PROPOSED = [
    ("bags", "purses"),
    ("bags", "suitcases"),
    ("purses", "wallets"),
    ("trees", "branches"),
    ("trees", "roots"),
    ("elders", "grandparents"),
    ("snow", "blizzards"),
    ("poetry", "sonnets"),
    ("novels", "stories"),
    ("sadness", "grief"),
    ("empires", "kingdoms"),
    ("emperors", "pharaohs"),
    ("ash", "soot"),
    ("deserts", "dunes"),
]
# non-option words that name the concept (Q12: "devices" for gadgets and machines, "robotics")
EXTRA_FORMS = {"gadgets": ["devices"], "machines": ["devices"], "robots": ["robotics"]}

# ---------------------------------------------------------------- surface forms

MASS = {
    "snow", "sugar", "milk", "bread", "rubber", "plastic", "denim", "leather", "nylon", "silver",
    "gold", "sadness", "peace", "joy", "fear", "grief", "secrecy", "information", "dust", "ash",
    "soot", "pollen", "blood", "skin", "origami", "glue", "poetry", "lightning", "scissors",
}  # fmt: skip
# irregular / non-strip singulars and spelling variants (anything not "label minus s")
VARIANTS = {
    "harmonies": ["harmony"],
    "quarries": ["quarry"],
    "volcanoes": ["volcano", "volcanos"],
    "oases": ["oasis"],
    "cacti": ["cactus", "cactuses"],
    "memories": ["memory"],
    "rumors": ["rumor", "rumour", "rumours"],
    "lies": ["lie"],
    "dynasties": ["dynasty"],
    "youths": ["youth"],
    "children": ["child"],
    "leaves": ["leaf"],
    "branches": ["branch"],
    "stories": ["story"],
    "amphitheaters": ["amphitheater", "amphitheatre", "amphitheatres"],
    "aquariums": ["aquarium", "aquaria"],
    "airplanes": ["airplane", "aeroplane", "aeroplanes"],
    "frosts": ["frost"],
    "fear": ["fears"],
    "joy": ["joys"],
    "dreams": ["dream"],
    "plastic": ["plastics"],
    "ash": ["ashes"],
    "cheese": ["cheeses"],
    "vegetables": ["vegetable", "veggies"],
    "teenagers": ["teenager"],
}
# curated Chinese translations of >= 2 characters (1-character forms such as 金 / 雪 / 鼓 are
# never listed: they produce too many incidental hits); none is a substring of another
# concept's form (test_regex_forms_irregular_and_zh)
ZH = {
    "trumpets": ["小号"], "xylophones": ["木琴"], "harmonies": ["和声"], "violins": ["小提琴"],
    "drums": [], "mirrors": ["镜子"], "kaleidoscopes": ["万花筒"], "illusions": ["错觉", "幻象"],
    "cameras": ["相机", "摄像机"], "prisms": ["棱镜"], "satellites": ["卫星"],
    "constellations": ["星座"], "comets": ["彗星"], "planets": ["行星"],
    "telescopes": ["望远镜"], "dirigibles": ["飞艇"], "airplanes": ["飞机"], "kites": ["风筝"],
    "helicopters": ["直升机"], "parachutes": ["降落伞"], "snow": [], "frosts": ["霜冻"],
    "avalanches": ["雪崩"], "blizzards": ["暴风雪"], "icicles": ["冰柱", "冰锥"],
    "boulders": ["巨石"], "quarries": ["采石场"], "monoliths": ["独石柱"],
    "caverns": ["洞穴", "岩洞"], "pebbles": ["卵石"], "volcanoes": ["火山"],
    "lightning": ["闪电"], "earthquakes": ["地震"], "hurricanes": ["飓风"],
    "wildfires": ["野火", "山火"], "oceans": ["海洋", "大海"], "fountains": ["喷泉"],
    "aquariums": ["水族馆", "水族箱"], "waterfalls": ["瀑布"], "lakes": ["湖泊"],
    "deserts": ["沙漠"], "dunes": ["沙丘"], "oases": ["绿洲"], "cacti": ["仙人掌"],
    "camels": ["骆驼"], "sugar": ["白糖", "砂糖"], "milk": ["牛奶"], "bread": ["面包"],
    "vegetables": ["蔬菜"], "cheese": ["奶酪", "芝士"], "rubber": ["橡胶"], "plastic": ["塑料"],
    "denim": ["牛仔布"], "leather": ["皮革"], "nylon": ["尼龙"], "treasures": ["宝藏", "珍宝"],
    "silver": ["白银"], "gold": ["黄金"], "coins": ["硬币"], "pearls": ["珍珠"],
    "sadness": ["悲伤"], "peace": ["和平"], "joy": ["喜悦", "快乐"], "fear": ["恐惧"],
    "grief": ["悲痛", "哀伤"], "memories": ["记忆", "回忆"], "secrecy": ["保密"],
    "dreams": ["梦境", "梦想"], "rumors": ["谣言", "传闻"], "lies": ["谎言"],
    "information": ["信息", "资讯"], "algorithms": ["算法"], "phones": ["手机", "电话"],
    "computers": ["电脑", "计算机"], "databases": ["数据库"], "dynasties": ["王朝", "朝代"],
    "empires": ["帝国"], "kingdoms": ["王国"], "emperors": ["皇帝"], "pharaohs": ["法老"],
    "amphitheaters": ["圆形剧场", "露天剧场"], "masquerades": ["化装舞会", "假面舞会"],
    "carnivals": ["狂欢节", "嘉年华"], "costumes": ["戏服"], "parades": ["游行"],
    "youths": ["青年"], "children": ["孩子", "儿童"], "teenagers": ["青少年"],
    "elders": ["长者", "老人"], "grandparents": ["祖父母"], "dust": ["灰尘", "尘土"],
    "ash": ["灰烬"], "soot": ["煤烟"], "pollen": ["花粉"], "crumbs": ["碎屑"],
    "blood": ["血液"], "bones": ["骨头", "骨骼"], "veins": ["静脉"], "muscles": ["肌肉"],
    "skin": ["皮肤"], "trees": ["树木"], "forests": ["森林"], "leaves": ["树叶", "叶子"],
    "branches": ["树枝"], "roots": ["树根"], "origami": ["折纸"], "scissors": ["剪刀"],
    "glue": ["胶水"], "stickers": ["贴纸"], "crayons": ["蜡笔"], "contraptions": [],
    "gadgets": ["小工具"], "machines": ["机器", "机械"], "gears": ["齿轮"],
    "robots": ["机器人"], "poetry": ["诗歌"], "sonnets": ["十四行诗"], "novels": ["小说"],
    "stories": ["故事"], "songs": ["歌曲"], "bags": ["包包"], "suitcases": ["行李箱"],
    "backpacks": ["背包", "双肩包"], "purses": ["手提包"], "wallets": ["钱包", "皮夹"],
}  # fmt: skip


def english_forms(word: str) -> list[str]:
    """Label + singular (+ irregulars / spelling variants); mass nouns keep the label."""
    out = [word]
    if word in VARIANTS:
        out += VARIANTS[word]
    elif word not in MASS and word.endswith("s"):
        out.append(word[:-1])
    return list(dict.fromkeys(out))


def equivalents(words: list[str]) -> dict[str, list[str]]:
    eq: dict[str, set[str]] = {w: set() for w in words}
    for cl in CLIQUES:
        for w in cl:
            eq[w] |= set(cl) - {w}
    for a, b in [*PAIRS_Q12, *PAIRS_PROPOSED]:
        eq[a].add(b)
        eq[b].add(a)
    return {w: sorted(v) for w, v in eq.items() if v}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(v1: dict) -> dict:
    b = copy.deepcopy(v1)
    words = [c["word"] for c in b["concepts"]]
    cluster = {c["word"]: c["cluster"] for c in b["concepts"]}
    row_of = {w: i for i, w in enumerate(words)}

    out: dict = {
        "family": "introspection",
        "version": 2,
        "frozen": FROZEN,
        "built_from": "items.json (frozen 2026-10-23) by scripts/introspection_build_v2.py",
        "plan": "plans/0045-wsb-bp-introspection.md",
    }
    for k, v in b.items():
        if k not in ("family", "frozen", "plan"):
            out[k] = v
    out["v1_plan"] = v1["plan"]
    # the pre-grid header keys are the source's; the grid of record is the README's
    out["spec"] = {
        k: v
        for k, v in b["spec"].items()
        if k not in ("read_layers", "primary_layer", "primary_cells", "chance")
    }
    out["spec"]["legacy_v1"] = {
        k: b["spec"][k] for k in ("read_layers", "primary_layer", "primary_cells", "chance")
    }

    out["equivalents"] = equivalents(words)
    for c in out["concepts"]:
        w = c["word"]
        c["surface_forms"] = english_forms(w) + ZH[w]
        c["extra_forms"] = list(EXTRA_FORMS.get(w, []))

    for key, r in out["renders"].items():
        grid = r["grid"]
        r["lite"] = [grid[-1]] if key.startswith("protocol:") else [grid[1]]

    gauss_ids = [it["id"] for it in out["items"] if it["kind"] == "gaussian"]
    gauss_row = {i: n for n, i in enumerate(gauss_ids)}
    by_id = {it["id"]: it for it in out["items"]}
    rot: dict[tuple[str, float], str] = {
        (it["concept"], float(it["beta"])): it["prompt_key"]
        for it in out["items"]
        if it["kind"] == "gaussian" and it["prompt_kind"] == "neutral"
    }
    b0_ids = {r["id"] for r in out["beta0_rows"]}
    for it in out["items"]:
        it["options"] = [*it["options"], {"label": mc.CANNOT, "source": "cannot"}]
        mc.options_with_cannot([o["label"] for o in it["options"][:-1]])  # refuses a duplicate
        if it["vector"]["type"] == "concept":
            it["vector"]["row"] = row_of[it["vector"]["word"]]
        elif it["vector"]["type"] == "gaussian":
            it["vector"]["row"] = gauss_row[it["id"]]
        if it["kind"] != "inject":
            continue
        c, beta, pk, key = it["concept"], float(it["beta"]), it["prompt_kind"], it["prompt_key"]
        tkey = key if pk == "protocol" else rot[(c, beta)]
        twins = {
            "gaussian": f"gaussian|{pk}:{tkey}|b{beta:g}|{c}",
            "cross": f"cross|{pk}:{tkey}|b{beta:g}|{c}",
            "beta0": f"beta0|{pk}:{key}|b0||{cluster[c]}",
        }
        assert twins["gaussian"] in by_id and twins["cross"] in by_id, twins
        assert f"beta0|{pk}:{key}|b0|" in b0_ids, twins
        it["twins"] = twins
    for r in out["beta0_rows"]:
        r["options_by_cluster"] = {
            cl: mc.options_with_cannot(list(labels))
            for cl, labels in r["options_by_cluster"].items()
        }

    cpath, gpath = REPO / VEC / "concept_vectors_L12.npy", REPO / VEC / "gaussian_vectors_L12.npy"
    d = int(out["spec"].get("d_model", 5120))
    out["vectors"] = {
        "concept": {
            "path": f"{VEC}/concept_vectors_L12.npy",
            "sha256": sha256(cpath),
            "dtype": "float32",
            "shape": [len(words), d],
            "order": "concepts",
            "normalised": False,
        },
        "gaussian": {
            "path": f"{VEC}/gaussian_vectors_L12.npy",
            "sha256": sha256(gpath),
            "dtype": "float32",
            "shape": [len(gauss_ids), d],
            "order": "gaussian items in bank order",
            "normalised": False,
        },
        "note": "RAW layer-12 vectors (un-normalised); the injection unit-normalises them: "
        "h <- h + beta * ||h|| * v / ||v||. Activations of Qwen3.6-27B (NOTICE.md).",
    }
    out["vector_recipe"] = {
        **out["vector_recipe"],
        "shipped": "vectors.concept / vectors.gaussian (items[].vector.row indexes them)",
    }
    return out


def main() -> None:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    v2 = build(v1)
    V2.write_text(json.dumps(v2, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_eq = sum(len(v) for v in v2["equivalents"].values()) // 2
    print(
        f"{V2.relative_to(REPO)}: {len(v2['items'])} items, {len(v2['beta0_rows'])} beta0 rows,"
        f" {len(v2['equivalents'])} concepts with equivalents ({n_eq} symmetric pairs)"
    )


if __name__ == "__main__":
    main()
