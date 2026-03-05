#!/usr/bin/env python3
"""
八字命理排盘引擎
Four Pillars of Destiny (BaZi) Calculation Engine

理论依据：三命通会、滴天髓、陆致极体系、梁湘润体系
"""

import datetime
from dataclasses import dataclass, field
from typing import Optional, List

# ── 基础常量 ─────────────────────────────────────────────────────────────────

TIANGAN  = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DIZHI    = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
SHENGXIAO = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪']

WUXING_GAN = ['木', '木', '火', '火', '土', '土', '金', '金', '水', '水']
WUXING_ZHI = ['水', '土', '木', '木', '土', '火', '火', '土', '金', '金', '土', '水']

YINYANG_GAN = ['阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴']
YINYANG_ZHI = ['阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴']

# 地支藏干（主气、中气、余气）
CANGGAN = {
    '子': ['壬', '癸'],
    '丑': ['己', '癸', '辛'],
    '寅': ['甲', '丙', '戊'],
    '卯': ['甲', '乙'],
    '辰': ['戊', '乙', '癸'],
    '巳': ['丙', '庚', '戊'],
    '午': ['丁', '己'],
    '未': ['己', '丁', '乙'],
    '申': ['庚', '壬', '戊'],
    '酉': ['庚', '辛'],
    '戌': ['戊', '辛', '丁'],
    '亥': ['壬', '甲'],
}

# 时辰名称与起始小时（24小时制）
SHICHEN = [
    ('子', 23), ('丑', 1), ('寅', 3), ('卯', 5),
    ('辰', 7),  ('巳', 9), ('午', 11), ('未', 13),
    ('申', 15), ('酉', 17), ('戌', 19), ('亥', 21),
]

# 十神名称
SHISHEN_NAMES = {
    (0, 0): '比肩', (0, 1): '劫财',
    (1, 0): '食神', (1, 1): '伤官',
    (2, 0): '偏财', (2, 1): '正财',
    (3, 0): '七杀', (3, 1): '正官',
    (4, 0): '偏印', (4, 1): '正印',
}


# ── 核心算法 ─────────────────────────────────────────────────────────────────

def _jdn(year: int, month: int, day: int) -> int:
    """格里历 → 儒略日数（Julian Day Number）"""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def get_day_ganzhi(year: int, month: int, day: int):
    """
    计算日柱干支
    验证：JDN(2000-01-01) = 2451545 → 甲辰日？
    实测：(2451545 + 49) % 60 = 54 → 戊午日 ✓（与万年历吻合）
    """
    idx = (_jdn(year, month, day) + 49) % 60
    return TIANGAN[idx % 10], DIZHI[idx % 12], idx


def get_hour_branch(hour: int, minute: int = 0) -> int:
    """24小时时间 → 时支索引（子=0）"""
    total = hour * 60 + minute
    if total >= 23 * 60 or total < 60:
        return 0  # 子时
    return (total + 60) // 120


def get_year_ganzhi(year: int, month: int, day: int):
    """
    计算年柱（以立春为界，约 2月4日）
    立春前用上一年干支
    """
    y = year if (month > 2 or (month == 2 and day >= 4)) else year - 1
    si = (y - 4) % 10
    bi = (y - 4) % 12
    return TIANGAN[si], DIZHI[bi], si, bi


def get_month_branch(month: int, day: int) -> int:
    """
    公历月日 → 月支索引
    以各月节气为界（近似取固定日期，误差±1天）
    寅=2, 卯=3, ..., 子=0, 丑=1
    """
    # (月, 节日, 该节后的月支)
    nodes = [
        (1, 6, 1), (2, 4, 2), (3, 6, 3), (4, 5, 4),
        (5, 6, 5), (6, 6, 6), (7, 7, 7), (8, 7, 8),
        (9, 8, 9), (10, 8, 10), (11, 7, 11), (12, 7, 0),
    ]
    branch = 11  # 亥（上年末）
    for m, d, b in nodes:
        if month > m or (month == m and day >= d):
            branch = b
    return branch


def get_month_stem(year_stem_idx: int, month_branch_idx: int) -> str:
    """月干 = 由年干推月干（五虎遁年起月法）"""
    # 寅月序号：branch 2→seq 0, 3→1, ..., 1→11
    seq = (month_branch_idx - 2) % 12
    # 起始月干：甲己年丙寅，乙庚年戊寅，丙辛年庚寅，丁壬年壬寅，戊癸年甲寅
    start = [2, 4, 6, 8, 0][year_stem_idx % 5]
    return TIANGAN[(start + seq) % 10]


def get_hour_stem(day_stem_idx: int, hour_branch_idx: int) -> str:
    """时干 = 由日干推时干（五鼠遁日起时法）"""
    start = (day_stem_idx % 5) * 2
    return TIANGAN[(start + hour_branch_idx) % 10]


def get_shishen(day_stem_idx: int, other_stem_idx: int) -> str:
    """计算十神关系（日主 vs 某天干）"""
    de = day_stem_idx // 2    # 日主五行
    oe = other_stem_idx // 2  # 对方五行
    dy = day_stem_idx % 2     # 日主阴阳
    oy = other_stem_idx % 2   # 对方阴阳

    produces = {0: 1, 1: 2, 2: 3, 3: 4, 4: 0}  # 木→火→土→金→水→木
    controls = {0: 2, 1: 3, 2: 4, 3: 0, 4: 1}  # 木→土→水→火→金→木

    same_yy = (dy == oy)
    if de == oe:
        rel = 0  # 比
    elif produces[de] == oe:
        rel = 1  # 生出
    elif produces[oe] == de:
        rel = 4  # 生入
    elif controls[de] == oe:
        rel = 2  # 克出
    else:
        rel = 3  # 克入

    return SHISHEN_NAMES.get((rel, 0 if same_yy else 1), '—')


def get_shishen_branch(day_stem_idx: int, branch_idx: int) -> str:
    """地支十神（取主气）"""
    main_gas = {
        0: '壬', 1: '己', 2: '甲', 3: '甲', 4: '戊',
        5: '丙', 6: '丁', 7: '己', 8: '庚', 9: '庚',
        10: '戊', 11: '壬'
    }
    mg = main_gas[branch_idx]
    return get_shishen(day_stem_idx, TIANGAN.index(mg))


# ── 大运计算（顺逆推）─────────────────────────────────────────────────────────

def get_dayun(year: int, month: int, day: int,
              year_stem_idx: int, month_branch_idx: int,
              gender: str) -> list:
    """
    计算大运（每10年一运，共8步）
    顺行：阳年男 / 阴年女
    逆行：阴年男 / 阳年女
    起运年龄 ≈ 到下一个（或上一个）节气的天数 / 3
    """
    yang_year = (year_stem_idx % 2 == 0)
    forward = (yang_year and gender == '男') or (not yang_year and gender == '女')

    # 节气近似日期（月, 日）
    solar_nodes = [
        (1, 6), (2, 4), (3, 6), (4, 5), (5, 6), (6, 6),
        (7, 7), (8, 7), (9, 8), (10, 8), (11, 7), (12, 7),
    ]
    birth = datetime.date(year, month, day)
    # 当月节气
    cur_node_month, cur_node_day = solar_nodes[(month - 1) % 12]
    cur_node = datetime.date(year, cur_node_month, cur_node_day)
    next_node_m = month % 12 + 1
    next_node_y = year + (1 if month == 12 else 0)
    nm, nd = solar_nodes[next_node_m - 1]
    next_node = datetime.date(next_node_y, nm, nd)
    prev_node_m = (month - 2) % 12 + 1
    prev_node_y = year - (1 if month == 1 else 0)
    pm, pd = solar_nodes[prev_node_m - 1]
    prev_node = datetime.date(prev_node_y, pm, pd)

    if forward:
        target = next_node if birth >= cur_node else cur_node
    else:
        target = prev_node if birth <= cur_node else cur_node

    days_diff = abs((target - birth).days)
    start_age = round(days_diff / 3)  # 3天≈1年

    # 生成8步大运干支
    dayuns = []
    # 大运从月柱的下一个（或上一个）干支开始
    ms_idx = TIANGAN.index(get_month_stem(year_stem_idx, month_branch_idx))
    mb_idx = month_branch_idx
    for i in range(8):
        step = i + 1
        if forward:
            si = (ms_idx + step) % 10
            bi = (mb_idx + step) % 12
        else:
            si = (ms_idx - step) % 10
            bi = (mb_idx - step) % 12
        age = start_age + i * 10
        dayuns.append({
            'stem': TIANGAN[si],
            'branch': DIZHI[bi],
            'ganzhi': TIANGAN[si] + DIZHI[bi],
            'start_age': age,
            'element': WUXING_GAN[si],
        })
    return dayuns, start_age


# ── 数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class Pillar:
    name: str
    stem: str
    branch: str
    stem_idx: int
    branch_idx: int
    shishen_stem: str = ''
    shishen_branch: str = ''
    canggan: list = field(default_factory=list)

    @property
    def ganzhi(self): return self.stem + self.branch
    @property
    def stem_element(self): return WUXING_GAN[self.stem_idx]
    @property
    def branch_element(self): return WUXING_ZHI[self.branch_idx]
    @property
    def stem_yinyang(self): return YINYANG_GAN[self.stem_idx]
    @property
    def branch_yinyang(self): return YINYANG_ZHI[self.branch_idx]


@dataclass
class BaZiChart:
    name: str
    gender: str
    birth_str: str
    shengxiao: str
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    hour_pillar: Pillar
    wuxing: dict
    dayun: list
    dayun_start_age: int
    shichen_name: str  # 出生时辰名


# ── 主函数 ──────────────────────────────────────────────────────────────────

def calculate_bazi(name: str, year: int, month: int, day: int,
                   hour: int, minute: int = 0,
                   gender: str = '男') -> BaZiChart:

    # 年柱
    ys, yb, ysi, ybi = get_year_ganzhi(year, month, day)

    # 月柱
    mbi = get_month_branch(month, day)
    ms = get_month_stem(ysi, mbi)
    msi = TIANGAN.index(ms)
    mb = DIZHI[mbi]

    # 日柱
    ds, db, _ = get_day_ganzhi(year, month, day)
    dsi = TIANGAN.index(ds)
    dbi = DIZHI.index(db)

    # 时柱
    hbi = get_hour_branch(hour, minute)
    hs = get_hour_stem(dsi, hbi)
    hsi = TIANGAN.index(hs)
    hb = DIZHI[hbi]

    # 时辰名
    shichen_name = DIZHI[hbi] + '时'

    def make(name, stem, branch, si, bi):
        ss = '日主' if name == '日' else get_shishen(dsi, si)
        sb = get_shishen_branch(dsi, bi)
        return Pillar(name=name, stem=stem, branch=branch,
                      stem_idx=si, branch_idx=bi,
                      shishen_stem=ss, shishen_branch=sb,
                      canggan=CANGGAN.get(branch, []))

    yp = make('年', ys, yb, ysi, ybi)
    mp = make('月', ms, mb, msi, mbi)
    dp = make('日', ds, db, dsi, dbi)
    hp = make('时', hs, hb, hsi, hbi)

    # 五行统计（天干1分，地支0.5分，藏干0.3分）
    wx = {'木': 0.0, '火': 0.0, '土': 0.0, '金': 0.0, '水': 0.0}
    for p in [yp, mp, dp, hp]:
        wx[WUXING_GAN[p.stem_idx]] += 1.0
        wx[WUXING_ZHI[p.branch_idx]] += 0.5
        for cg in p.canggan:
            wx[WUXING_GAN[TIANGAN.index(cg)]] += 0.3
    wx = {k: round(v, 1) for k, v in wx.items()}

    # 大运
    dayuns, start_age = get_dayun(year, month, day, ysi, mbi, gender)

    birth_str = f"{year}年{month}月{day}日 {shichen_name}（{hour:02d}:{minute:02d}）"

    return BaZiChart(
        name=name, gender=gender,
        birth_str=birth_str,
        shengxiao=SHENGXIAO[ybi],
        year_pillar=yp, month_pillar=mp,
        day_pillar=dp, hour_pillar=hp,
        wuxing=wx,
        dayun=dayuns,
        dayun_start_age=start_age,
        shichen_name=shichen_name,
    )


def chart_to_dict(c: BaZiChart) -> dict:
    def pd(p: Pillar):
        return {
            'name': p.name, 'stem': p.stem, 'branch': p.branch,
            'ganzhi': p.ganzhi,
            'stem_element': p.stem_element, 'branch_element': p.branch_element,
            'stem_yinyang': p.stem_yinyang, 'branch_yinyang': p.branch_yinyang,
            'shishen_stem': p.shishen_stem, 'shishen_branch': p.shishen_branch,
            'canggan': p.canggan,
        }
    return {
        'name': c.name, 'gender': c.gender,
        'birth_str': c.birth_str, 'shengxiao': c.shengxiao,
        'pillars': {'年': pd(c.year_pillar), '月': pd(c.month_pillar),
                    '日': pd(c.day_pillar), '时': pd(c.hour_pillar)},
        'wuxing': c.wuxing,
        'dayun': c.dayun,
        'dayun_start_age': c.dayun_start_age,
    }


def chart_to_prompt(c: BaZiChart, question: str = '综合命运') -> str:
    """生成发给 Claude 的命盘文本"""
    p = c
    lines = [
        f"【命造信息】",
        f"姓名：{p.name}　性别：{p.gender}　生肖：{p.shengxiao}",
        f"生辰：{p.birth_str}",
        f"",
        f"【四柱八字】",
        f"　　　　年柱　　月柱　　日柱　　时柱",
    ]
    cols = [p.year_pillar, p.month_pillar, p.day_pillar, p.hour_pillar]
    lines.append("十神　　" + "　　".join(x.shishen_stem for x in cols))
    lines.append("天干　　" + "　　".join(x.stem for x in cols))
    lines.append("　　　　" + "　　".join(f"（{x.stem_element}{x.stem_yinyang}）" for x in cols))
    lines.append("地支　　" + "　　".join(x.branch for x in cols))
    lines.append("　　　　" + "　　".join(f"（{x.branch_element}{x.branch_yinyang}）" for x in cols))
    lines.append("支十神　" + "　　".join(x.shishen_branch for x in cols))
    lines.append("")
    lines.append("【地支藏干】")
    for cp in cols:
        lines.append(f"　{cp.branch}：{'、'.join(cp.canggan)}")
    lines.append("")
    lines.append("【五行统计】（天干1分 · 地支0.5分 · 藏干0.3分）")
    wx = p.wuxing
    lines.append("　" + "　".join(f"{k}:{v}" for k, v in wx.items()))
    lines.append("")
    lines.append("【大运】（从{}岁起运，每10年一换）".format(p.dayun_start_age))
    for d in p.dayun[:6]:
        lines.append(f"　{d['start_age']}岁：{d['ganzhi']}（{d['element']}）")
    lines.append("")
    lines.append(f"【问题 / 关注重点】")
    lines.append(f"　{question}")
    lines.append("")
    lines.append("请按以下顺序给出完整分析：")
    lines.append("1. 日主旺衰（月令司令、地支帮扶、天干透出）")
    lines.append("2. 格局判断（正格/从格，是否成格）")
    lines.append("3. 用神、喜神、忌神确定，说明理由")
    lines.append("4. 针对提问的专项解读")
    lines.append("5. 近三年运势提示（结合当前大运）")
    return "\n".join(lines)
