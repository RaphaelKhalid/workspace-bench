"""Build the basic_readout v2 bank (plan 0053): question-form prompts, frozen MC options, task
contexts, the v1 gold fixes, and the Qwen3.6-27B re-gate in the eval render.

    # 1. gate requests (100 v1 items + spares), one row per candidate, 10 draws at temp 0.7
    uv run python scripts/build_basic_readout_v2.py requests --out gate/br_v2.jsonl
    # 2. sample on Modal (1 GPU): scripts/qwen_sample_modal.py --requests ... --out ...
    # 3. grade + freeze: writes evals/basic_readout/items_v2.json and the gate report
    uv run python scripts/build_basic_readout_v2.py freeze --samples gate/br_v2.samples.jsonl

Everything here is deterministic given the samples file: the option draws are seeded by item id,
the implicit distractors prefer Qwen's own runner-up answers from the gate histogram, and an item
that fails its gate is replaced by a spare of its own slice (the spares are gated in the same
job). The v1 bank ``items.json`` is never touched.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from wsbench import mc

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/basic_readout/items.json"
V2 = REPO / "evals/basic_readout/items_v2.json"
REPORT = REPO / "evals/basic_readout/gate_v2.json"
PREFILL = "My one-word answer is:"
SUFFIX = " Answer in one word."
N_DRAWS, PASS_AT = 10, 8
PV_SEED = "br-mc-2026-10-30b"

# ---------------------------------------------------------------- per-slice templates

TEMPLATES = {
    "ath": "What sport does the athlete {x} play?",
    "cap": "{x} is the capital of which country?",
    "lmk": "In which country is {x}?",
    "mus": "Which instrument is the musician {x} famous for playing?",
    "arith": "What is {x}?",
    "dayafter": "What is the day after {x}?",
    "daybefore": "What is the day before {x}?",
    "monthafter": "What is the month after {x}?",
}
TASK_CONTEXT = {
    "ath": "the model was asked which sport a famous athlete plays, to answer with a single word",
    "cap": "the model was asked which country a capital city belongs to, to answer with a "
    "single word",
    "lmk": "the model was asked which country a famous landmark is in, to answer with a single "
    "word",
    "mus": "the model was asked which instrument a famous musician is known for playing, to "
    "answer with a single word",
    "arith": "the model was asked to compute a single-step arithmetic problem with small whole "
    "numbers, to answer with a single word",
    "dayafter": "the model was asked which day of the week comes right after a given day, to "
    "answer with a single word",
    "daybefore": "the model was asked which day of the week comes right before a given day, to "
    "answer with a single word",
    "monthafter": "the model was asked which month comes right after a given month, to answer "
    "with a single word",
}
SUBFAMILY = {
    "ath": "entity",
    "cap": "entity",
    "lmk": "entity",
    "mus": "entity",
    "arith": "processing",
    "dayafter": "processing",
    "daybefore": "processing",
    "monthafter": "processing",
    "implicit": "implicit",
}

# ---------------------------------------------------------------- forms (aliases) of every option
# Every option of an item carries the same form languages as its gold (a Chinese form for every
# option, or none for any; tests/test_basic_readout.py::test_option_forms_even), so a Chinese flat
# list is judged by the same bare-mention gate as an English one. A form that lies inside another
# option's form (一月 in 十一月, 十 in 十一, 香肠 in 意大利辣香肠) is resolved by the judge's masks
# (mcjudge_basic.Options.masks), not by leaving the form out.
FORMS: dict[str, list[str]] = {
    # sports
    "boxing": ["拳击"],
    "American football": ["football", "NFL", "gridiron", "美式足球", "美式橄榄球"],
    "tennis": ["网球"],
    "hockey": ["ice hockey", "冰球"],
    "basketball": ["NBA", "篮球"],
    "soccer": ["football", "association football", "足球"],
    "baseball": ["棒球"],
    "golf": ["高尔夫"],
    "cricket": ["板球"],
    "rugby": ["橄榄球", "英式橄榄球"],
    "volleyball": ["排球"],
    "swimming": ["swim", "游泳"],
    # countries
    "Greece": ["希腊"],
    "Germany": ["德国"],
    "Egypt": ["埃及"],
    "Spain": ["西班牙"],
    "Russia": ["俄罗斯"],
    "Kenya": ["肯尼亚"],
    "Canada": ["加拿大"],
    "France": ["法国"],
    "Italy": ["意大利"],
    "Japan": ["日本"],
    "England": ["United Kingdom", "UK", "Britain", "Great Britain", "英国", "英格兰"],
    "Brazil": ["巴西"],
    "Australia": ["澳大利亚", "澳洲"],
    "India": ["印度"],
    "China": ["中国"],
    "Mexico": ["墨西哥"],
    "Portugal": ["葡萄牙"],
    "Turkey": ["Türkiye", "土耳其"],
    "Argentina": ["阿根廷"],
    "Peru": ["秘鲁"],
    "United States": ["USA", "US", "U.S.", "America", "United States of America", "美国"],
    "Malaysia": ["马来西亚"],
    # instruments
    "trumpet": ["小号"],
    "piano": ["钢琴"],
    "guitar": ["吉他"],
    "cello": ["大提琴"],
    "saxophone": ["sax", "萨克斯"],
    "violin": ["fiddle", "小提琴"],
    "drums": ["drum", "drum kit", "架子鼓", "鼓"],
    "flute": ["长笛"],
    # days
    "Monday": ["星期一", "周一", "礼拜一"],
    "Tuesday": ["星期二", "周二", "礼拜二"],
    "Wednesday": ["星期三", "周三", "礼拜三"],
    "Thursday": ["星期四", "周四", "礼拜四"],
    "Friday": ["星期五", "周五", "礼拜五"],
    "Saturday": ["星期六", "周六", "礼拜六"],
    "Sunday": ["星期日", "星期天", "周日", "礼拜天"],
    # months
    "January": ["一月"],
    "February": ["二月"],
    "March": ["三月"],
    "April": ["四月"],
    "May": ["五月"],
    "June": ["六月"],
    "July": ["七月"],
    "August": ["八月"],
    "September": ["九月"],
    "October": ["十月"],
    "November": ["十一月"],
    "December": ["十二月"],
}
NUMBER_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]
# CJK numerals of every pool number (1 is never an option: arithmetic distractors exclude it);
# 二 / 十 inside 十二 / 十一 are resolved by the judge's masks
CJK_NUM = {0: ["零"], 2: ["二", "两"], 3: ["三"], 4: ["四"], 5: ["五"], 6: ["六"], 7: ["七"],
           8: ["八"], 9: ["九"], 10: ["十"], 11: ["十一"], 12: ["十二"]}  # fmt: skip
for _n in range(13):
    FORMS[str(_n)] = [NUMBER_WORDS[_n], *CJK_NUM.get(_n, [])]

# implicit items: per-item forms (one word names different things in different items: "Indian"
# ocean vs cuisine), added to the gold's aliases and to each distractor's FORMS entry. Items whose
# options are all Latin-script names in Chinese text too (programming languages, operating
# systems, databases, fonts, Muppets, the English-word item) carry no Chinese form for any option.
ITEM_FORMS: dict[str, dict[str, list[str]]] = {
    "br-imp-cartoonchara": {
        "Shinchan": ["Shin-chan", "蜡笔小新"],
        "Mickey Mouse": ["Mickey", "米老鼠", "米奇"],
        "Bugs Bunny": ["兔八哥", "宾尼兔"],
        "Homer Simpson": ["辛普森"],
        "Pikachu": ["皮卡丘"],
    },
    "br-imp-shape": {
        "circle": ["圆形"],
        "square": ["正方形", "方形"],
        "triangle": ["三角形"],
        "star": ["星形", "五角星"],
        "hexagon": ["六边形"],
    },
    "br-imp-color": {"green": ["绿色"], "red": ["红色"], "purple": ["紫色"], "black": ["黑色"]},
    "br-imp-constellatio": {
        "Ursa Major": ["大熊座"],
        "Cassiopeia": ["仙后座"],
        "Scorpius": ["Scorpio", "天蝎座"],
        "Andromeda": ["仙女座"],
    },
    "br-imp-flower": {
        "tulip": ["郁金香"],
        "sunflower": ["向日葵"],
        "lily": ["百合"],
        "orchid": ["兰花"],
    },
    "br-imp-holiday": {
        "Halloween": ["万圣节"],
        "Thanksgiving": ["感恩节"],
        "New Year": ["新年", "元旦"],
        "Easter": ["复活节"],
    },
    "br-imp-ocean": {
        "Pacific": ["太平洋"],
        "Atlantic": ["大西洋"],
        "Indian": ["印度洋"],
        "Arctic": ["北冰洋"],
        "Southern": ["南冰洋", "南大洋"],
    },
    "br-imp-kindofcookie": {
        "oatmeal raisin": ["燕麦葡萄干"],
        "peanut butter": ["花生酱"],
        "snickerdoodle": ["肉桂糖"],
        "sugar cookie": ["糖霜饼干", "糖饼干"],
    },
    "br-imp-bread": {
        "sourdough": ["酸面包", "酸种面包"],
        "baguette": ["法棍"],
        "rye": ["黑麦"],
        "ciabatta": ["恰巴塔"],
        "brioche": ["布里欧修"],
    },
    "br-imp-composer": {
        "Bach": ["巴赫"],
        "Mozart": ["莫扎特"],
        "Beethoven": ["贝多芬"],
        "Chopin": ["肖邦"],
        "Debussy": ["德彪西"],
    },
    "br-imp-moviegenre": {
        "action": ["动作"],
        "comedy": ["喜剧"],
        "horror": ["恐怖"],
        "drama": ["剧情"],
    },
    "br-imp-seacreature": {
        "dolphin": ["海豚"],
        "narwhal": ["独角鲸"],
        "whale": ["鲸"],
        "sea turtle": ["海龟"],
        "jellyfish": ["水母"],
    },
    "br-imp-tree": {
        "olive": ["橄榄"],
        "maple": ["枫树"],
        "pine": ["松树"],
        "willow": ["柳树"],
        "cherry": ["樱桃", "樱花"],
    },
    "br-imp-shakespeare": {
        "Hamlet": ["哈姆雷特"],
        "Macbeth": ["麦克白"],
        "Othello": ["奥赛罗"],
        "King Lear": ["李尔王"],
        "The Tempest": ["Tempest", "暴风雨"],
    },
    "br-imp-typeofmusic": {
        "classical": ["古典"],
        "rock": ["摇滚"],
        "pop": ["流行"],
        "hip-hop": ["hip hop", "嘻哈"],
    },
    "br-imp-ghibli": {
        "Totoro": ["龙猫"],
        "Ponyo": ["波妞", "悬崖上的金鱼"],
        "Mononoke": ["幽灵公主"],
        "Laputa": ["天空之城"],
    },
    "br-imp-kindofcandy": {
        "gummy bears": ["gummy bear", "小熊软糖", "软糖"],
        "lollipops": ["lollipop", "棒棒糖"],
        "licorice": ["甘草糖"],
        "caramel": ["焦糖"],
    },
    "br-imp-kindofpepper": {
        "jalapeño": ["墨西哥辣椒"],
        "habanero": ["哈瓦那辣椒"],
        "poblano": ["波布拉诺"],
        "chipotle": ["奇波雷"],
        "bell pepper": ["甜椒", "彩椒"],
    },
    "br-imp-pizzatopping": {
        "mushrooms": ["mushroom", "蘑菇"],
        "pineapple": ["菠萝"],
        "olives": ["olive", "橄榄"],
        "sausage": ["香肠"],
    },
    "br-imp-typeofdance": {
        "contemporary": ["现代舞", "当代舞"],
        "swing": ["摇摆舞"],
        "tango": ["探戈"],
        "ballet": ["芭蕾"],
        "waltz": ["华尔兹"],
        "hip-hop": ["hip hop", "嘻哈"],
    },
    "br-imp-typeofsoup": {
        "chicken noodle": ["鸡汤面", "鸡肉面"],
        "minestrone": ["意大利蔬菜汤"],
        "miso": ["味噌"],
        "French onion": ["洋葱汤"],
    },
    "br-imp-cloud": {
        "cumulus": ["积云"],
        "stratus": ["层云"],
        "nimbus": ["雨云"],
        "cirrus": ["卷云"],
        "cumulonimbus": ["积雨云"],
    },
    "br-imp-fruit": {
        "mango": ["芒果"],
        "banana": ["香蕉"],
        "strawberry": ["草莓"],
        "orange": ["橙子"],
    },
    "br-imp-grain": {
        "wheat": ["小麦"],
        "rice": ["大米", "稻米", "米饭"],
        "quinoa": ["藜麦"],
        "oats": ["oat", "燕麦"],
        "barley": ["大麦"],
    },
}


def option_aliases(item: str, option: str, listed: list[str] | None = None) -> list[str]:
    """An option's aliases: ``listed`` (the gold's own aliases) or its FORMS entry, plus the
    item's ITEM_FORMS, de-duplicated in order."""
    base = FORMS.get(option, []) if listed is None else listed
    out: list[str] = []
    for f in [*base, *ITEM_FORMS.get(item, {}).get(option, [])]:
        if f not in out and f != option:
            out.append(f)
    return out


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
SPORTS = [
    "boxing",
    "American football",
    "tennis",
    "hockey",
    "basketball",
    "soccer",
    "baseball",
    "golf",
    "cricket",
    "rugby",
    "volleyball",
    "swimming",
]
INSTRUMENTS = ["trumpet", "piano", "guitar", "cello", "saxophone", "violin", "drums", "flute"]
EXTRA_COUNTRIES = ["China", "Mexico", "Portugal", "Turkey", "Argentina"]

# ---------------------------------------------------------------- entity / processing items
# name -> (slice, subject {x}, gold); the subject is the v1 entity / operand
ENTITY: dict[str, tuple[str, str, str]] = {
    "br-ent-ath-ali": ("ath", "Muhammad Ali", "boxing"),
    "br-ent-ath-brady": ("ath", "Tom Brady", "American football"),
    "br-ent-ath-federer": ("ath", "Roger Federer", "tennis"),
    "br-ent-ath-gretzky": ("ath", "Wayne Gretzky", "hockey"),
    "br-ent-ath-james": ("ath", "LeBron James", "basketball"),
    "br-ent-ath-jordan": ("ath", "Michael Jordan", "basketball"),
    "br-ent-ath-messi": ("ath", "Lionel Messi", "soccer"),
    "br-ent-ath-nadal": ("ath", "Rafael Nadal", "tennis"),
    "br-ent-ath-ronaldo": ("ath", "Cristiano Ronaldo", "soccer"),
    "br-ent-ath-ruth": ("ath", "Babe Ruth", "baseball"),
    "br-ent-ath-williams": ("ath", "Serena Williams", "tennis"),
    "br-ent-ath-woods": ("ath", "Tiger Woods", "golf"),
    "br-ent-cap-athens": ("cap", "Athens", "Greece"),
    "br-ent-cap-berlin": ("cap", "Berlin", "Germany"),
    "br-ent-cap-cairo": ("cap", "Cairo", "Egypt"),
    "br-ent-cap-madrid": ("cap", "Madrid", "Spain"),
    "br-ent-cap-moscow": ("cap", "Moscow", "Russia"),
    "br-ent-cap-nairobi": ("cap", "Nairobi", "Kenya"),
    "br-ent-cap-ottawa": ("cap", "Ottawa", "Canada"),
    "br-ent-cap-paris": ("cap", "Paris", "France"),
    "br-ent-cap-rome": ("cap", "Rome", "Italy"),
    "br-ent-cap-tokyo": ("cap", "Tokyo", "Japan"),
    "br-ent-lmk-big": ("lmk", "Big Ben", "England"),
    "br-ent-lmk-christ": ("lmk", "Christ the Redeemer", "Brazil"),
    "br-ent-lmk-colosseum": ("lmk", "the Colosseum", "Italy"),
    "br-ent-lmk-eiffel": ("lmk", "the Eiffel Tower", "France"),
    "br-ent-lmk-great": ("lmk", "the Great Pyramid of Giza", "Egypt"),
    "br-ent-lmk-sydney": ("lmk", "the Sydney Opera House", "Australia"),
    "br-ent-lmk-taj": ("lmk", "the Taj Mahal", "India"),
    "br-ent-mus-armstrong": ("mus", "Louis Armstrong", "trumpet"),
    "br-ent-mus-beethoven": ("mus", "Ludwig van Beethoven", "piano"),
    "br-ent-mus-davis": ("mus", "Miles Davis", "trumpet"),
    "br-ent-mus-hendrix": ("mus", "Jimi Hendrix", "guitar"),
    "br-ent-mus-john": ("mus", "Elton John", "piano"),
    "br-ent-mus-ma": ("mus", "Yo-Yo Ma", "cello"),
}
# spares: gated in the same job; a failing item is replaced by the first passing spare of its
# own slice group (ath/mus, cap/lmk, arith/day/month)
SPARE_ENTITY: dict[str, tuple[str, str, str]] = {
    "br-ent-ath-pele": ("ath", "Pelé", "soccer"),
    "br-ent-ath-phelps": ("ath", "Michael Phelps", "swimming"),
    "br-ent-ath-tendulkar": ("ath", "Sachin Tendulkar", "cricket"),
    "br-ent-ath-bryant": ("ath", "Kobe Bryant", "basketball"),
    "br-ent-ath-djokovic": ("ath", "Novak Djokovic", "tennis"),
    "br-ent-mus-perlman": ("mus", "Itzhak Perlman", "violin"),
    "br-ent-mus-starr": ("mus", "Ringo Starr", "drums"),
    "br-ent-mus-clapton": ("mus", "Eric Clapton", "guitar"),
    "br-ent-mus-parker": ("mus", "Charlie Parker", "saxophone"),
    "br-ent-mus-coltrane": ("mus", "John Coltrane", "saxophone"),
    "br-ent-cap-lima": ("cap", "Lima", "Peru"),
    "br-ent-cap-canberra": ("cap", "Canberra", "Australia"),
    "br-ent-cap-beijing": ("cap", "Beijing", "China"),
    "br-ent-cap-ankara": ("cap", "Ankara", "Turkey"),
    "br-ent-cap-lisbon": ("cap", "Lisbon", "Portugal"),
    "br-ent-lmk-liberty": ("lmk", "the Statue of Liberty", "United States"),
    "br-ent-lmk-machu": ("lmk", "Machu Picchu", "Peru"),
    "br-ent-lmk-pisa": ("lmk", "the Leaning Tower of Pisa", "Italy"),
    "br-ent-lmk-acropolis": ("lmk", "the Acropolis", "Greece"),
    "br-ent-lmk-petronas": ("lmk", "the Petronas Towers", "Malaysia"),
}
SPARE_PROC: dict[str, tuple[str, str, str]] = {
    "br-proc-monthafter-september": ("monthafter", "September", "October"),
    "br-proc-monthafter-october": ("monthafter", "October", "November"),
    "br-proc-monthafter-november": ("monthafter", "November", "December"),
    "br-proc-arith-3+5": ("arith", "3 + 5", "8"),
    "br-proc-arith-9-3": ("arith", "9 - 3", "6"),
    "br-proc-arith-3*3": ("arith", "3 * 3", "9"),
    "br-proc-arith-12/3": ("arith", "12 / 3", "4"),
    "br-proc-arith-2+5": ("arith", "2 + 5", "7"),
    "br-proc-arith-8-7": ("arith", "8 - 7", "1"),
    "br-proc-arith-11-4": ("arith", "11 - 4", "7"),
}
GROUP = {
    "ath": "ath/mus",
    "mus": "ath/mus",
    "cap": "cap/lmk",
    "lmk": "cap/lmk",
    "arith": "proc",
    "dayafter": "proc",
    "daybefore": "proc",
    "monthafter": "proc",
    "implicit": "implicit",
}
# the audit cases' competing answers, always shown (plan 0053 E2: mus-john's top token guitar,
# daybefore-monday's "the day before Sunday is Saturday", the J-lens fruit list's mango)
FORCE: dict[str, list[str]] = {
    "br-ent-mus-john": ["guitar"],
    "br-proc-daybefore-monday": ["Saturday"],
    "br-imp-fruit": ["mango"],
}
# per-item exclusions on top of the type rules (near-aliases of the gold)
EXCLUDE: dict[str, set[str]] = {
    "American football": {"soccer", "rugby"},
    "soccer": {"American football", "rugby"},
    "England": set(),
}

# ---------------------------------------------------------------- implicit items
# name -> (category for the task context, gold, extra gold aliases, curated distractors)
IMPLICIT: dict[str, tuple[str, str, list[str], list[str]]] = {
    "br-imp-cardgame": (
        "card game",
        "poker",
        ["扑克"],
        ["bridge", "blackjack", "solitaire", "rummy"],
    ),
    "br-imp-cartoonchara": (
        "cartoon character",
        "SpongeBob",
        ["SpongeBob SquarePants", "海绵宝宝"],
        ["Mickey Mouse", "Bugs Bunny", "Homer Simpson", "Pikachu"],
    ),
    "br-imp-chesspiece": ("chess piece", "queen", ["皇后"], ["knight", "king", "bishop", "rook"]),
    "br-imp-color": ("color", "blue", ["蓝色"], ["green", "red", "purple", "black"]),
    "br-imp-constellatio": (
        "constellation",
        "Orion",
        ["猎户座"],
        ["Ursa Major", "Cassiopeia", "Scorpius", "Andromeda"],
    ),
    "br-imp-dayoftheweek": (
        "day of the week",
        "Friday",
        ["星期五", "周五"],
        ["Saturday", "Sunday", "Monday", "Wednesday"],
    ),
    "br-imp-flower": ("flower", "rose", ["玫瑰"], ["tulip", "sunflower", "lily", "orchid"]),
    "br-imp-holiday": (
        "holiday",
        "Christmas",
        ["Xmas", "圣诞"],
        ["Halloween", "Thanksgiving", "New Year", "Easter"],
    ),
    "br-imp-icecreamflav": (
        "ice cream flavor",
        "chocolate",
        ["巧克力"],
        ["vanilla", "strawberry", "pistachio", "mint"],
    ),
    "br-imp-kindofcookie": (
        "kind of cookie",
        "chocolate",
        ["chocolate chip", "巧克力"],
        ["oatmeal raisin", "peanut butter", "snickerdoodle", "sugar cookie"],
    ),
    "br-imp-kindofshoe": (
        "kind of shoe",
        "sneakers",
        ["sneaker", "trainers", "运动鞋"],
        ["boots", "sandals", "loafers", "high heels"],
    ),
    "br-imp-kindofweathe": (
        "kind of weather",
        "sunny",
        ["sunshine", "晴天"],
        ["rainy", "snowy", "cloudy", "windy"],
    ),
    "br-imp-moviegenre": (
        "movie genre",
        "sci-fi",
        ["science fiction", "scifi", "科幻"],
        ["comedy", "horror", "drama", "action"],
    ),
    "br-imp-programmingl": (
        "programming language",
        "Python",
        [],
        ["JavaScript", "Rust", "C++", "Java"],
    ),
    "br-imp-seacreature": (
        "sea creature",
        "octopus",
        ["章鱼"],
        ["dolphin", "whale", "sea turtle", "jellyfish"],
    ),
    "br-imp-tree": ("tree", "oak", ["橡树"], ["maple", "pine", "willow", "cherry"]),
    "br-imp-typeofcuisin": (
        "type of cuisine",
        "Italian",
        ["意大利"],
        ["Japanese", "Mexican", "Indian", "French"],
    ),
    "br-imp-typeofmusic": (
        "type of music",
        "jazz",
        ["爵士"],
        ["classical", "rock", "pop", "hip-hop"],
    ),
    "br-imp-countrytovis": (
        "country to visit",
        "Japan",
        ["日本"],
        ["Italy", "France", "Iceland", "New Zealand"],
    ),
    "br-imp-kindofberry": (
        "kind of berry",
        "strawberry",
        ["草莓"],
        ["blueberry", "raspberry", "blackberry", "cranberry"],
    ),
    "br-imp-kindofcandy": (
        "kind of candy",
        "chocolate",
        ["巧克力"],
        ["gummy bears", "lollipops", "licorice", "caramel"],
    ),
    "br-imp-kindofpepper": (
        "kind of pepper",
        "bell pepper",
        ["bell", "甜椒"],
        ["jalapeño", "habanero", "poblano", "chipotle"],
    ),
    "br-imp-mythicalcrea": (
        "mythical creature",
        "dragon",
        ["龙"],
        ["phoenix", "unicorn", "griffin", "mermaid"],
    ),
    "br-imp-pet": ("pet", "dog", ["狗"], ["cat", "rabbit", "parrot", "hamster"]),
    "br-imp-pizzatopping": (
        "pizza topping",
        "pepperoni",
        ["意大利辣香肠"],
        ["mushrooms", "pineapple", "olives", "sausage"],
    ),
    "br-imp-typeofbird": (
        "type of bird",
        "owl",
        ["猫头鹰"],
        ["eagle", "hummingbird", "penguin", "parrot"],
    ),
    "br-imp-typeofdance": (
        "type of dance",
        "salsa",
        ["萨尔萨"],
        ["tango", "ballet", "waltz", "hip-hop"],
    ),
    "br-imp-typeofsoup": (
        "type of soup",
        "tomato",
        ["番茄", "西红柿"],
        ["chicken noodle", "minestrone", "miso", "French onion"],
    ),
    "br-imp-bookgenre": (
        "book genre",
        "science fiction",
        ["sci-fi", "scifi", "SF", "科幻"],
        ["fantasy", "mystery", "romance", "biography"],
    ),
    "br-imp-dessert": (
        "dessert",
        "chocolate",
        ["巧克力"],
        ["cheesecake", "ice cream", "tiramisu", "apple pie"],
    ),
    "br-imp-fruit": ("fruit", "apple", ["苹果"], ["mango", "banana", "strawberry", "orange"]),
    "br-imp-season": ("season", "autumn", ["fall", "秋天", "秋季"], ["spring", "summer", "winter"]),
}
# implicit spares: gold = Qwen's modal answer (>= 8/10), distractors curated; used only if a v1
# implicit item fails its re-gate
SPARE_IMPLICIT: dict[str, tuple[str, list[str]]] = {
    "br-imp-gemstone": ("gemstone", ["diamond", "ruby", "emerald", "sapphire", "amethyst"]),
    "br-imp-vegetable": ("vegetable", ["carrot", "broccoli", "spinach", "potato", "tomato"]),
    "br-imp-boardgame": ("board game", ["chess", "Monopoly", "Scrabble", "Catan", "checkers"]),
    "br-imp-instrument": (
        "musical instrument",
        ["piano", "guitar", "violin", "cello", "drums"],
    ),
    "br-imp-animal": ("animal", ["dog", "cat", "elephant", "dolphin", "lion"]),
    "br-imp-sport": ("sport", ["soccer", "basketball", "tennis", "swimming", "baseball"]),
    "br-imp-insect": ("insect", ["butterfly", "bee", "ladybug", "ant", "dragonfly"]),
    "br-imp-breakfast": ("breakfast food", ["pancakes", "eggs", "toast", "waffles", "oatmeal"]),
    # second batch (gated after 13 of the 32 v1 implicit items failed the v2 re-gate)
    "br-imp-shape": ("shape", ["circle", "square", "triangle", "star", "hexagon"]),
    "br-imp-metal": ("metal", ["gold", "silver", "copper", "iron", "titanium"]),
    "br-imp-ocean": ("ocean", ["Pacific", "Atlantic", "Indian", "Arctic", "Southern"]),
    "br-imp-continent": ("continent", ["Asia", "Europe", "Africa", "Antarctica", "Australia"]),
    "br-imp-drink": ("drink", ["water", "coffee", "tea", "juice", "milk"]),
    "br-imp-typeoftea": ("type of tea", ["green", "black", "oolong", "chamomile", "jasmine"]),
    "br-imp-cheese": ("cheese", ["cheddar", "brie", "gouda", "mozzarella", "parmesan"]),
    "br-imp-pasta": ("pasta shape", ["spaghetti", "penne", "lasagna", "fettuccine", "ravioli"]),
    "br-imp-nut": ("nut", ["almond", "cashew", "walnut", "pistachio", "peanut"]),
    "br-imp-herb": ("herb", ["basil", "mint", "rosemary", "thyme", "cilantro"]),
    "br-imp-spice": ("spice", ["cinnamon", "cumin", "turmeric", "paprika", "ginger"]),
    "br-imp-dinosaur": (
        "dinosaur",
        ["Tyrannosaurus", "Triceratops", "Velociraptor", "Stegosaurus", "Brachiosaurus"],
    ),
    "br-imp-superhero": (
        "superhero",
        ["Spider-Man", "Batman", "Superman", "Iron Man", "Wonder Woman"],
    ),
    "br-imp-greekgod": ("Greek god", ["Athena", "Zeus", "Apollo", "Hermes", "Poseidon"]),
    "br-imp-element": ("chemical element", ["carbon", "oxygen", "helium", "iron", "gold"]),
    "br-imp-bigcat": ("big cat", ["tiger", "lion", "leopard", "cheetah", "jaguar"]),
    "br-imp-bread": ("bread", ["sourdough", "baguette", "rye", "ciabatta", "brioche"]),
    "br-imp-carbrand": ("car brand", ["Tesla", "Toyota", "BMW", "Ferrari", "Porsche"]),
    "br-imp-painter": ("painter", ["Van Gogh", "Monet", "Picasso", "Rembrandt", "Vermeer"]),
    "br-imp-composer": ("composer", ["Bach", "Mozart", "Beethoven", "Chopin", "Debussy"]),
    "br-imp-scientist": ("scientist", ["Einstein", "Newton", "Curie", "Feynman", "Darwin"]),
    "br-imp-philosopher": (
        "philosopher",
        ["Socrates", "Plato", "Aristotle", "Kant", "Nietzsche"],
    ),
    "br-imp-shakespeare": (
        "Shakespeare play",
        ["Hamlet", "Macbeth", "Othello", "King Lear", "The Tempest"],
    ),
    "br-imp-videogame": ("video game", ["Minecraft", "Zelda", "Tetris", "Portal", "Mario"]),
    "br-imp-emotion": ("emotion", ["joy", "curiosity", "love", "calm", "gratitude"]),
    "br-imp-timeofday": ("time of day", ["morning", "evening", "night", "afternoon", "dawn"]),
    "br-imp-landscape": ("landscape", ["mountains", "ocean", "forest", "desert", "beach"]),
    "br-imp-citrus": ("citrus fruit", ["orange", "lemon", "lime", "grapefruit", "mandarin"]),
    "br-imp-fabric": ("fabric", ["cotton", "silk", "wool", "linen", "denim"]),
    "br-imp-dogbreed": (
        "dog breed",
        ["Golden Retriever", "Labrador", "Corgi", "Husky", "Beagle"],
    ),
    "br-imp-farmanimal": ("farm animal", ["cow", "pig", "horse", "sheep", "goat"]),
    "br-imp-reptile": ("reptile", ["turtle", "gecko", "chameleon", "snake", "iguana"]),
    "br-imp-starwars": (
        "Star Wars character",
        ["Yoda", "Luke Skywalker", "Darth Vader", "Han Solo", "Chewbacca"],
    ),
    "br-imp-coffee": ("coffee drink", ["espresso", "latte", "cappuccino", "americano", "mocha"]),
    "br-imp-punctuation": (
        "punctuation mark",
        ["semicolon", "comma", "period", "colon", "question mark"],
    ),
    "br-imp-condiment": ("condiment", ["ketchup", "mustard", "mayonnaise", "soy sauce", "relish"]),
    # third batch (12 of 44 implicit candidates passed after two batches)
    "br-imp-word": (
        "word",
        ["serendipity", "ephemeral", "petrichor", "luminous", "mellifluous", "eloquent"],
    ),
    "br-imp-smell": ("smell", ["petrichor", "rain", "coffee", "vanilla", "lavender", "cinnamon"]),
    "br-imp-beatlessong": (
        "Beatles song",
        ["Yesterday", "Help", "Something", "Blackbird", "Michelle"],
    ),
    "br-imp-beatle": ("Beatle", ["George", "John", "Paul", "Ringo"]),
    "br-imp-mathematician": (
        "mathematician",
        ["Euler", "Gauss", "Euclid", "Riemann", "Ramanujan", "Noether"],
    ),
    "br-imp-physicist": (
        "physicist",
        ["Feynman", "Einstein", "Newton", "Bohr", "Dirac", "Maxwell"],
    ),
    "br-imp-author": ("author", ["Tolkien", "Borges", "Orwell", "Austen", "Dickens", "Hemingway"]),
    "br-imp-poet": ("poet", ["Rumi", "Neruda", "Dickinson", "Keats", "Whitman", "Frost"]),
    "br-imp-novel": (
        "novel",
        ["Dune", "Frankenstein", "Middlemarch", "Ulysses", "Dracula", "Emma"],
    ),
    "br-imp-greekletter": ("Greek letter", ["lambda", "pi", "omega", "sigma", "alpha", "delta"]),
    "br-imp-pixar": ("Pixar movie", ["Up", "Ratatouille", "WALL-E", "Coco", "Cars", "Brave"]),
    "br-imp-ghibli": (
        "Studio Ghibli film",
        ["Totoro", "Ponyo", "Mononoke", "Laputa", "Kiki", "Porco"],
    ),
    "br-imp-pokemon": (
        "Pokémon",
        ["Pikachu", "Eevee", "Charizard", "Bulbasaur", "Mewtwo", "Snorlax"],
    ),
    "br-imp-muppet": ("Muppet", ["Kermit", "Gonzo", "Animal", "Fozzie", "Beaker", "Elmo"]),
    "br-imp-poohcharacter": (
        "Winnie the Pooh character",
        ["Eeyore", "Piglet", "Tigger", "Owl", "Rabbit"],
    ),
    "br-imp-hpcharacter": (
        "Harry Potter character",
        ["Hermione", "Dumbledore", "Snape", "Hagrid", "Luna", "Ron"],
    ),
    "br-imp-lotrcharacter": (
        "Lord of the Rings character",
        ["Gandalf", "Samwise", "Aragorn", "Frodo", "Legolas", "Gollum"],
    ),
    "br-imp-font": ("font", ["Helvetica", "Garamond", "Futura", "Baskerville", "Arial", "Georgia"]),
    "br-imp-os": (
        "operating system",
        ["Linux", "macOS", "Windows", "Ubuntu", "Debian", "FreeBSD", "Android"],
    ),
    "br-imp-editor": ("text editor", ["Vim", "Emacs", "VSCode", "Sublime", "Nano", "Atom"]),
    "br-imp-datastructure": ("data structure", ["tree", "graph", "array", "trie", "heap", "queue"]),
    "br-imp-sortalgo": (
        "sorting algorithm",
        ["quicksort", "mergesort", "heapsort", "bubblesort", "radix", "timsort"],
    ),
    "br-imp-database": (
        "database",
        ["PostgreSQL", "SQLite", "MySQL", "MongoDB", "Redis", "Oracle"],
    ),
    "br-imp-cloud": (
        "type of cloud",
        ["cumulus", "cirrus", "stratus", "nimbus", "cumulonimbus", "altostratus"],
    ),
    "br-imp-mineral": ("mineral", ["quartz", "amethyst", "obsidian", "feldspar", "pyrite", "mica"]),
    "br-imp-rock": (
        "type of rock",
        ["granite", "basalt", "obsidian", "marble", "limestone", "sandstone"],
    ),
    "br-imp-mushroom": (
        "mushroom",
        ["shiitake", "chanterelle", "portobello", "morel", "oyster", "truffle"],
    ),
    "br-imp-grain": ("grain", ["quinoa", "rice", "oats", "barley", "wheat", "farro"]),
    "br-imp-cocktail": (
        "cocktail",
        ["mojito", "martini", "negroni", "margarita", "daiquiri", "Manhattan"],
    ),
    "br-imp-pastry": ("pastry", ["croissant", "baklava", "eclair", "danish", "strudel", "macaron"]),
    "br-imp-pie": ("pie", ["apple", "pecan", "pumpkin", "cherry", "blueberry", "key lime"]),
    "br-imp-sandwich": ("sandwich", ["BLT", "Reuben", "club", "panini", "cubano", "banh mi"]),
    "br-imp-noodle": ("noodle", ["ramen", "udon", "soba", "pho", "spaghetti", "lo mein"]),
    "br-imp-sauce": (
        "sauce",
        ["pesto", "marinara", "hollandaise", "bechamel", "teriyaki", "salsa verde"],
    ),
    "br-imp-primate": (
        "primate",
        ["orangutan", "chimpanzee", "gorilla", "bonobo", "lemur", "gibbon"],
    ),
    "br-imp-bear": ("bear", ["panda", "polar bear", "grizzly", "sloth bear", "sun bear", "koala"]),
    "br-imp-shark": (
        "shark",
        ["hammerhead", "great white", "whale shark", "tiger shark", "mako", "nurse shark"],
    ),
    "br-imp-horsebreed": (
        "horse breed",
        ["Arabian", "Friesian", "Mustang", "Clydesdale", "Appaloosa", "Thoroughbred"],
    ),
    "br-imp-catbreed": (
        "cat breed",
        ["Maine Coon", "Siamese", "Persian", "Bengal", "Ragdoll", "Sphynx"],
    ),
    "br-imp-amphibian": (
        "amphibian",
        ["axolotl", "frog", "salamander", "newt", "toad", "caecilian"],
    ),
    "br-imp-mountain": (
        "mountain",
        ["Everest", "Fuji", "Kilimanjaro", "Matterhorn", "Denali", "K2"],
    ),
    "br-imp-river": ("river", ["Amazon", "Nile", "Danube", "Thames", "Mississippi", "Yangtze"]),
    "br-imp-desert": ("desert", ["Sahara", "Atacama", "Gobi", "Mojave", "Kalahari", "Namib"]),
    "br-imp-nationalpark": (
        "national park",
        ["Yosemite", "Yellowstone", "Zion", "Banff", "Acadia", "Denali"],
    ),
    "br-imp-city": ("city", ["Kyoto", "Paris", "Tokyo", "Lisbon", "Vienna", "Prague"]),
    "br-imp-humanlanguage": (
        "human language",
        ["Japanese", "Spanish", "French", "Italian", "Mandarin", "Arabic"],
    ),
    "br-imp-shadeofblue": (
        "shade of blue",
        ["cerulean", "teal", "navy", "azure", "cobalt", "indigo"],
    ),
    "br-imp-sound": ("sound", ["rain", "ocean waves", "birdsong", "laughter", "music", "thunder"]),
    "br-imp-month": ("month", ["October", "September", "May", "December", "April", "June"]),
    "br-imp-hobby": ("hobby", ["reading", "hiking", "painting", "gardening", "cooking", "chess"]),
    "br-imp-exercise": (
        "form of exercise",
        ["yoga", "running", "swimming", "cycling", "hiking", "dancing"],
    ),
    "br-imp-puzzle": (
        "kind of puzzle",
        ["sudoku", "crossword", "jigsaw", "riddle", "Rubik's cube", "logic"],
    ),
    "br-imp-schoolsubject": (
        "school subject",
        ["mathematics", "science", "history", "literature", "art", "music"],
    ),
    "br-imp-science": (
        "branch of science",
        ["physics", "astronomy", "biology", "chemistry", "neuroscience", "geology"],
    ),
    "br-imp-constant": ("mathematical constant", ["pi", "e", "phi", "tau", "gamma", "zeta"]),
    "br-imp-particle": (
        "subatomic particle",
        ["photon", "electron", "neutrino", "quark", "proton", "neutron"],
    ),
    "br-imp-artmovement": (
        "art movement",
        ["Impressionism", "Surrealism", "Cubism", "Baroque", "Renaissance", "Bauhaus"],
    ),
    "br-imp-archstyle": (
        "architectural style",
        ["Gothic", "Art Deco", "Baroque", "Brutalist", "Bauhaus", "Romanesque"],
    ),
    "br-imp-band": ("band", ["Beatles", "Queen", "Radiohead", "Coldplay", "Nirvana", "ABBA"]),
    "br-imp-texture": ("texture", ["velvet", "silk", "suede", "satin", "linen", "fleece"]),
    "br-imp-wonder": (
        "natural wonder",
        ["aurora", "Grand Canyon", "Everest", "rainbow", "waterfall", "reef"],
    ),
    "br-imp-invention": (
        "invention",
        ["printing press", "wheel", "internet", "telescope", "computer", "lightbulb"],
    ),
    "br-imp-superpower": (
        "superpower",
        ["teleportation", "flight", "invisibility", "telepathy", "time travel", "omniscience"],
    ),
    "br-imp-gemcolor": (
        "color of the rainbow",
        ["blue", "violet", "green", "red", "orange", "yellow"],
    ),
    "br-imp-fairytale": (
        "fairy tale",
        ["Cinderella", "Rapunzel", "Pinocchio", "Thumbelina", "Rumpelstiltskin", "Aladdin"],
    ),
    "br-imp-chessopening": (
        "chess opening",
        ["Sicilian", "Ruy Lopez", "Italian", "French", "Caro-Kann", "London"],
    ),
    "br-imp-wine": (
        "wine grape",
        ["Pinot Noir", "Merlot", "Riesling", "Cabernet", "Malbec", "Syrah"],
    ),
    "br-imp-flowercolor": (
        "kind of tree blossom",
        ["cherry", "magnolia", "apple", "almond", "plum", "dogwood"],
    ),
}


def implicit_prompt(category: str) -> str:
    return f"What is your favorite {category}?{SUFFIX}"


def implicit_context(category: str) -> str:
    return f"the model was asked to name its own favourite {category}, with a single word"


# ---------------------------------------------------------------- grading


def answer_of(text: str) -> str:
    """The model's answer after the prefill: first line, markdown and trailing punctuation off."""
    t = (text or "").strip().split("\n")[0]
    t = re.sub(r"[*_`\"“”]", "", t).strip()
    return t.rstrip(" .!,;:").strip()


def norm(s: str) -> str:
    return " ".join(mc.fold(s).replace("-", " ").split())


def forms_of(option: str) -> list[str]:
    return [option, *FORMS.get(option, [])]


def correct(answer: str, forms: list[str]) -> bool:
    """Pass rule (v1's): the normalised answer matches the gold or an alias (word-bounded)."""
    a = answer.replace("-", " ")
    return mc.form_in(a, [f.replace("-", " ") for f in forms])


# ---------------------------------------------------------------- distractors


_HAN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def _part_of(x: str, ys: list[str]) -> bool:
    """x is a word-bounded part of one of ys; a Chinese form only when it equals one (a Chinese
    form inside a longer one, 十 in 十一, is resolved by the judge's masks)."""
    if _HAN.search(x):
        return any(mc.fold(x) == mc.fold(y) for y in ys)
    return mc.form_in(x, [y for y in ys if not _HAN.search(y)]) or any(
        mc.form_in(y, [x]) for y in ys if not _HAN.search(y)
    )


def _related(a: str, b: str) -> bool:
    """a and b are the same option, or one's form is a word-bounded part of the other's."""
    fa, fb = forms_of(a), forms_of(b)
    return any(_part_of(x, fb) for x in fa) or any(_part_of(y, fa) for y in fb)


def draw(pool: list[str], gold: str, iid: str, k: int, exclude: set[str]) -> list[str]:
    """k seeded distractors, none sharing a form with the gold or with each other (a readout
    saying "football" must not match both soccer and American football)."""
    cands = [p for p in pool if p != gold and p not in exclude and not _related(p, gold)]
    out: list[str] = []
    for p in mc.seeded_shuffle(cands, f"{iid}|draw"):
        if len(out) < k and not any(_related(p, q) for q in out):
            out.append(p)
    return out


def numbers_in_prompt(subject: str) -> set[str]:
    return set(re.findall(r"\d+", subject))


def entity_distractors(iid: str, slc: str, subject: str, gold: str, golds: set[str]) -> list[str]:
    prompt = TEMPLATES[slc].format(x=subject) + SUFFIX
    out = _entity_distractors(iid, slc, subject, gold, golds, prompt)
    return out


def _in_prompt(pool: list[str], prompt: str) -> set[str]:
    """Options whose forms appear in the item's prompt (C8c: the operands, the prompt's day or
    month, and "one" of "Answer in one word" for the number 1)."""
    return {p for p in pool if mc.form_in(prompt, forms_of(p))}


def _entity_distractors(
    iid: str, slc: str, subject: str, gold: str, golds: set[str], prompt: str
) -> list[str]:
    if slc == "ath":
        return draw(SPORTS, gold, iid, 4, EXCLUDE.get(gold, set()) | _in_prompt(SPORTS, prompt))
    if slc in ("cap", "lmk"):
        pool = sorted(golds | set(EXTRA_COUNTRIES))
        # never a country named in the prompt (C8c)
        return draw(pool, gold, iid, 4, _in_prompt(pool, prompt))
    if slc == "mus":
        return draw(INSTRUMENTS, gold, iid, 4, _in_prompt(INSTRUMENTS, prompt))
    if slc == "arith":
        pool = [str(n) for n in range(13)]
        return draw(pool, gold, iid, 4, numbers_in_prompt(subject) | _in_prompt(pool, prompt))
    if slc in ("dayafter", "daybefore"):
        return draw(DAYS, gold, iid, 4, {subject} | _in_prompt(DAYS, prompt))
    if slc == "monthafter":
        return draw(MONTHS, gold, iid, 4, {subject} | _in_prompt(MONTHS, prompt))
    raise ValueError(slc)


# ---------------------------------------------------------------- stages


def candidates() -> list[dict[str, Any]]:
    """Every gate candidate (v1 items in bank order, then spares)."""
    out: list[dict[str, Any]] = []
    v1_items = json.loads(V1.read_text(encoding="utf-8"))["items"]
    proc = {it["name"]: it for it in v1_items if it["subfamily"] == "processing"}
    for it in v1_items:
        name = it["name"]
        if name in ENTITY:
            slc, subj, gold = ENTITY[name]
        elif name in proc:
            slc = name.split("-")[2]
            subj = _proc_subject(it["prompt"], slc)
            gold = it["target"]
        else:
            cat = IMPLICIT[name][0]
            out.append(
                {"name": name, "slice": "implicit", "subject": cat, "v1": it, "spare": False}
            )
            continue
        out.append(
            {"name": name, "slice": slc, "subject": subj, "gold": gold, "v1": it, "spare": False}
        )
    for name, (slc, subj, gold) in {**SPARE_ENTITY, **SPARE_PROC}.items():
        out.append({"name": name, "slice": slc, "subject": subj, "gold": gold, "spare": True})
    for name, (cat, _d) in SPARE_IMPLICIT.items():
        out.append({"name": name, "slice": "implicit", "subject": cat, "spare": True})
    return out


def _proc_subject(prompt: str, slc: str) -> str:
    if slc == "arith":
        return prompt.rstrip(" =").strip()
    m = re.fullmatch(r"The (?:day|month) (?:after|before) (\w+) is", prompt)
    if not m:
        raise ValueError(prompt)
    return m.group(1)


def prompt_of(c: dict[str, Any]) -> str:
    if c["slice"] == "implicit":
        return implicit_prompt(c["subject"])
    return TEMPLATES[c["slice"]].format(x=c["subject"]) + SUFFIX


def cmd_requests(out: Path, skip: list[Path]) -> None:
    done = set(_load_samples(skip)) if skip else set()
    rows = []
    for c in candidates():
        if c["name"] in done:
            continue
        rows.append(
            {
                "key": c["name"],
                "family": "basic_readout",
                "messages": [{"role": "user", "content": prompt_of(c)}],
                "prefill": PREFILL,
                "n": N_DRAWS,
                "temperature": 0.7,
                "top_p": 1.0,
                "top_k": -1,
                "max_tokens": 8,
                "enable_thinking": False,
                "greedy": False,
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"wrote {out} ({len(rows)} rows, {len(rows) * N_DRAWS} samples)")


def _hist(samples: list[dict[str, Any]]) -> Counter[str]:
    return Counter(norm(answer_of(s["text"])) for s in samples if not s.get("greedy"))


def _display(h: Counter[str], raw: list[dict[str, Any]], key: str = "") -> dict[str, int]:
    """Histogram keyed by the first raw spelling of each normalised answer."""
    spell: dict[str, str] = {}
    for s in raw:
        a = answer_of(s["text"])
        spell.setdefault(norm(a), a)
    if key:
        SPELLING[key] = spell
    return {spell.get(k, k): v for k, v in h.most_common()}


def _load_samples(paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_key.setdefault(r["key"], []).append(r)
    return by_key


def cmd_freeze(samples_paths: list[Path]) -> None:
    by_key = _load_samples(samples_paths)
    cands = candidates()
    missing = [c["name"] for c in cands if len(by_key.get(c["name"], [])) < N_DRAWS]
    if missing:
        sys.exit(f"samples missing for {len(missing)} candidates: {missing[:5]}")
    graded: dict[str, dict[str, Any]] = {}
    for c in cands:
        raw = [s for s in by_key[c["name"]] if not s.get("greedy")][:N_DRAWS]
        h = _hist(raw)
        _display(h, raw, c["name"])
        if c["slice"] == "implicit":
            gold, aliases, _d = _implicit_gold(c, h)
            aliases = option_aliases(c["name"], gold, aliases if aliases else None)
        else:
            gold, aliases = c["gold"], option_aliases(c["name"], c["gold"])
        forms = [gold, *aliases]
        n_ok = sum(1 for s in raw if correct(answer_of(s["text"]), forms))
        # a candidate whose gold is named by its own prompt is never eligible (a leak)
        leak = bool(gold) and mc.form_in(prompt_of(c), forms)
        graded[c["name"]] = {
            "gold": gold,
            "aliases": aliases,
            "n": len(raw),
            "correct": n_ok,
            "answers": _display(h, raw),
            "pass": n_ok >= PASS_AT and not leak,
            **({"leak": "gold named in the prompt"} if leak else {}),
        }
    # replacements: a failing base item takes the first passing unused spare of its group
    used: set[str] = set()
    final: list[tuple[dict[str, Any], str | None]] = []
    drops: list[dict[str, Any]] = []
    for c in cands:
        if c["spare"]:
            continue
        g = graded[c["name"]]
        if g["pass"]:
            final.append((c, None))
            continue
        rep = next(
            (
                s
                for s in cands
                if s["spare"]
                and s["name"] not in used
                and GROUP[s["slice"]] == GROUP[c["slice"]]
                and graded[s["name"]]["pass"]
                and (c["slice"] != "implicit" or s["slice"] == "implicit")
            ),
            None,
        )
        drops.append(
            {
                "name": c["name"],
                "reason": f"gate {g['correct']}/{g['n']} < {PASS_AT}",
                "answers": g["answers"],
                "replaced_by": rep["name"] if rep else None,
            }
        )
        if rep is None:
            print(f"WARNING: {c['name']} failed and no spare of its group passed", file=sys.stderr)
            continue
        used.add(rep["name"])
        final.append((rep, c["name"]))
    golds = {graded[c["name"]]["gold"] for c, _r in final if c["slice"] in ("cap", "lmk")}
    items = [_item(c, graded[c["name"]], golds, replaces) for c, replaces in final]
    by_name = {c["name"]: c for c in cands}
    # the dropped items as they would have been frozen (audit; plan 0053 E2 re-judges cached v1
    # readouts of a dropped item under these options, labelled "judge test, not a headline")
    dropped_items = [_item(by_name[d["name"]], graded[d["name"]], golds, None) for d in drops]
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    counts = Counter(it["subfamily"] for it in items)
    header = {
        "family": "basic-readout",
        "version": 2,
        "supersedes": "items.json",
        "changes": [
            "question form: every entity / processing prompt is a chat question ending "
            "'? Answer in one word.' (plan 0039 C2b)",
            "all items render chat_prefill with 'My one-word answer is:'; read from the first "
            "question token through the prefill (question_through_end); lite = final token",
            "br-proc-arith-10-1 / br-proc-arith-7+2: targets ['9','nine'] (v1 listed 'ten')",
            "br-imp-bookgenre: gold 'science fiction' (v1: 'science'), then dropped by the "
            "re-gate (1/10); br-imp-kindofpepper: gold 'jalapeño' (v1: 'bell'; Qwen's modal "
            "answer, 9/10 in the re-gate), 'bell pepper' kept as a distractor",
            "athlete distractors never share a form with each other (soccer and American "
            "football are mutually exclusive: both carry the alias 'football')",
            "br-ent-ath-brady: gold 'American football' (alias football); every item carries "
            "frozen MC options (mc), a task_context and its v2 gate block",
            "option forms are even (review of PR #166): every option of an item carries a "
            "Chinese form when any does (zh numerals 零 二 十 十一 十二, months 一月 二月 十月, "
            "rugby, drums, every implicit option), so a Chinese flat list meets the same "
            "bare-mention gate as an English one; judge stamp br-mc-2026-10-30b",
        ],
        "gate": {
            "model": "Qwen/Qwen3.6-27B",
            "render": "chat template, enable_thinking=False, user turn = prompt, assistant "
            f"prefill {PREFILL!r} (the eval render)",
            "sampling": {"n": N_DRAWS, "temperature": 0.7, "top_p": 1.0, "top_k": -1},
            "max_tokens": 8,
            "rule": f">= {PASS_AT}/{N_DRAWS} answers match gold or an alias after normalising "
            "case and punctuation; implicit gold = Qwen's modal answer",
            "replacement": "a failing item is replaced by the first passing spare of its slice "
            "group (ath/mus, cap/lmk, arith/day/month, implicit)",
            "drops": drops,
            "v1_sha256": _sha(V1),
        },
        "counts": dict(counts),
        "contract": v1.get("contract", {}),
    }
    if not header["contract"]:
        header.pop("contract")
    V2.write_text(
        json.dumps({**header, "items": items}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(
        json.dumps(
            {
                "candidates": graded,
                "drops": drops,
                "counts": dict(counts),
                "dropped_items": dropped_items,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {V2} ({len(items)} items: {dict(counts)}; {len(drops)} replaced)")


def _sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest()


def _implicit_gold(c: dict[str, Any], h: Counter[str]) -> tuple[str, list[str], list[str]]:
    """(gold, aliases, curated distractors) of an implicit candidate: the v1 gold (with v2's
    fixes) when Qwen's modal answer is it, else the modal answer (graded >= 8/10 later)."""
    if c["name"] in IMPLICIT:
        _cat, gold, aliases, dis = IMPLICIT[c["name"]]
        top = _modal(c, h)
        # a changed favourite becomes the gold only if it is itself >= PASS_AT (else the item
        # keeps its curated gold, fails the gate and is replaced)
        if not top or correct(top, [gold, *aliases]) or h.most_common(1)[0][1] < PASS_AT:
            return gold, aliases, dis
        return top, [], [*dis, gold]
    _cat, dis = SPARE_IMPLICIT[c["name"]]
    top = _modal(c, h)
    if c["name"] in GOLD_FIX and h and correct(top, list(GOLD_FIX[c["name"]])):
        gold, *aliases = GOLD_FIX[c["name"]]
        return gold, aliases, [d for d in dis if not correct(d, [gold, *aliases])]
    return top, [], [d for d in dis if norm(d) != norm(top)]


# a spare's modal one-word answer that is a truncated or lower-cased name: (gold, *aliases)
GOLD_FIX: dict[str, tuple[str, ...]] = {
    "br-imp-ghibli": ("Spirited Away", "Spirited", "千与千寻"),
    "br-imp-poohcharacter": ("Pooh", "Winnie the Pooh", "Winnie-the-Pooh"),
}
# runner-ups that are a hyponym / hypernym of the gold or not an option of the category
IMPLICIT_EXCLUDE: dict[str, set[str]] = {
    "br-imp-os": {"ubuntu", "debian"},  # Linux distributions: hyponyms of the gold
    "br-imp-database": {"sql", "relational"},  # a query language / a class, not a database
    "br-imp-kindofpepper": {"banana"},  # "banana" alone names the fruit, not banana pepper
}


SPELLING: dict[str, dict[str, str]] = {}  # candidate -> {normalised answer: first raw spelling}


def _modal(c: dict[str, Any], h: Counter[str]) -> str:
    """Qwen's modal answer in its own first spelling, lower-cased unless it is a proper name
    (the curated option list's casing wins when it names the same thing)."""
    if not h:
        return ""
    top = h.most_common(1)[0][0]
    raw = SPELLING.get(c["name"], {}).get(top, top)
    curated = SPARE_IMPLICIT.get(c["name"], ("", []))[1]
    for o in curated:
        if norm(o) == top:
            return o
    return raw[:1].lower() + raw[1:] if raw[:1].isupper() and raw[1:].islower() else raw


def _item(
    c: dict[str, Any], g: dict[str, Any], golds: set[str], replaces: str | None
) -> dict[str, Any]:
    name, slc = c["name"], c["slice"]
    gold, aliases = g["gold"], g["aliases"]
    if slc == "implicit":
        _g, _a, curated = _implicit_gold(c, Counter())
        if name in IMPLICIT and norm(gold) != norm(IMPLICIT[name][1]):
            curated = [*IMPLICIT[name][3], IMPLICIT[name][1]]
        elif name in SPARE_IMPLICIT:
            curated = [d for d in SPARE_IMPLICIT[name][1] if norm(d) != norm(gold)]
        distractors = _implicit_distractors(name, gold, aliases, g["answers"], curated)
        context = implicit_context(c["subject"])
    else:
        distractors = entity_distractors(name, slc, c["subject"], gold, golds)
        context = TASK_CONTEXT[slc]
    for f in FORCE.get(name, []):  # the audit's confusable answer is always an option
        if f not in distractors:
            distractors = [f, *distractors[:-1]]
    if name == "br-imp-season":
        distractors = distractors[:3]
    forms = [gold, *aliases]
    item: dict[str, Any] = {
        "name": name,
        "subfamily": SUBFAMILY[slc],
        "slice": slc,
        "subject": c["subject"],
        "prompt": prompt_of(c),
        "target": gold,
        "intermediates": forms,
        "units": [{"role": "readout", "lang": "en", "headline": True, "match": forms}],
        "consistency": g["correct"] / g["n"],
        "source": "br-v2",
        "gate_variant": "chat_prefill",
        "eval_render": "chat",
        "readout": {"kind": "question_through_end", "lite": {"kind": "final_token"}},
        "mc": {
            "gold": gold,
            "aliases": aliases,
            "distractors": distractors,
            "distractor_aliases": {d: option_aliases(name, d) for d in distractors},
        },
        "task_context": context,
        "gate": {"n": g["n"], "correct": g["correct"], "answers": g["answers"]},
    }
    if "v1" in c:
        item["v1_prompt"] = c["v1"]["prompt"]
        if norm(c["v1"]["target"]) != norm(gold):
            item["v1_target"] = c["v1"]["target"]
    if replaces:
        item["replaces"] = replaces
    return item


# runner-up "answers" that are not options of the category (refusals, hedges, fragments)
NON_ANSWERS = frozenset(
    {"none", "diverse", "variety", "eclectic", "my", "impossible", "curious", "comfortable",
     "sports", "electric", "settlers", "i", "all", "it", "depends", "n a", "", "subjective",
     "undecided", "me", "thoughtful", "ever"}
)  # fmt: skip


def _implicit_distractors(
    iid: str, gold: str, aliases: list[str], answers: dict[str, int], curated: list[str]
) -> list[str]:
    """Qwen's own runner-up answers first (clean, not related to the gold), then the curated
    list, 4 in all (season: 3)."""
    forms = [gold, *aliases]
    out: list[str] = []
    runner_ups = []
    for a in answers:
        a = a.strip()
        if norm(a) in NON_ANSWERS or norm(a) in IMPLICIT_EXCLUDE.get(iid, set()):
            continue
        # a truncated runner-up ("Ursa") takes the curated option it is part of ("Ursa Major")
        full = next((o for o in curated if norm(a) != norm(o) and mc.form_in(o, [a])), None)
        runner_ups.append(full or a)
    for a in [*runner_ups, *curated]:
        a = a.strip()
        if not a or len(a.split()) > 3 or not re.fullmatch(r"[\w' +-]+", a):
            continue
        if correct(a, forms) or any(mc.form_in(f, [a]) for f in forms):
            continue
        if norm(a) in IMPLICIT_EXCLUDE.get(iid, set()):
            continue
        if any(norm(a) == norm(o) or mc.form_in(a, [o]) or mc.form_in(o, [a]) for o in out):
            continue
        lower = all(o[:1].islower() for o in curated if o[:1].isalpha())
        out.append(a if a in curated or not lower else a.lower())
        if len(out) == 4:
            break
    if len(out) < 4 and iid != "br-imp-season":
        raise SystemExit(f"{iid}: only {len(out)} distractors")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("requests")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--skip", type=Path, nargs="*", default=[], help="samples already gated")
    f = sub.add_parser("freeze")
    f.add_argument("--samples", type=Path, nargs="+", required=True)
    a = ap.parse_args()
    if a.cmd == "requests":
        cmd_requests(a.out, a.skip)
    else:
        cmd_freeze(a.samples)


if __name__ == "__main__":
    main()
