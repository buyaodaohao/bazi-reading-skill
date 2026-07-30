#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字命盘排盘引擎 v2.0
基于 sxtwl 天文历法库，支持公历/农历输入
自动推算四柱、十神、藏干、纳音、大运、流年
"""

import json
import sys
import math
from datetime import datetime, date
from lunardate import LunarDate
import sxtwl


# ============================
# 基础数据
# ============================

TIAN_GAN = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
DI_ZHI   = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]

CANG_GAN = {
    "子": ["癸"],
    "丑": ["己","癸","辛"],
    "寅": ["甲","丙","戊"],
    "卯": ["乙"],
    "辰": ["戊","乙","癸"],
    "巳": ["丙","庚","戊"],
    "午": ["丁","己"],
    "未": ["己","丁","乙"],
    "申": ["庚","壬","戊"],
    "酉": ["辛"],
    "戌": ["戊","辛","丁"],
    "亥": ["壬","甲"],
}

WUXING_GAN = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
WUXING_ZHI = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}

# 六十纳音（每两组干支共用一个纳音，共30组）
NAYIN_LIST = [
    "海中金","炉中火","大林木","路旁土","剑锋金","山头火",
    "涧下水","城头土","白蜡金","杨柳木","泉中水","屋上土",
    "霹雳火","松柏木","长流水","砂石金","山下火","平地木",
    "壁上土","金箔金","覆灯火","天河水","大驿土","钗钏金",
    "桑柘木","大溪水","沙中土","天上火","石榴木","大海水",
]

KONG_WANG = {
    "子":("戌","亥"),"丑":("戌","亥"),
    "寅":("子","丑"),"卯":("子","丑"),
    "辰":("寅","卯"),"巳":("寅","卯"),
    "午":("辰","巳"),"未":("辰","巳"),
    "申":("午","未"),"酉":("午","未"),
    "戌":("申","酉"),"亥":("申","酉"),
}

# 节气名称（24节气）
JIE_QI_NAMES = [
    "冬至","小寒","大寒","立春","雨水","惊蛰","春分","清明","谷雨",
    "立夏","小满","芒种","夏至","小暑","大暑","立秋","处暑","白露",
    "秋分","寒露","霜降","立冬","小雪","大雪"
]

# ============================
# 工具函数
# ============================

def get_nayin(gan, zhi):
    """根据天干地支计算纳音（60甲子序数 ÷ 2 = 纳音组索引）"""
    gi = TIAN_GAN.index(gan)
    zi = DI_ZHI.index(zhi)
    seq = (gi * 6 - zi * 5) % 60  # 60甲子序数（0-based）
    return NAYIN_LIST[seq // 2]


def get_shishen(day_gan, other_gan):
    """计算十神（日干 vs 其他天干）"""
    if other_gan == day_gan:
        return "比肩" if day_gan in ("甲","丙","戊","庚","壬") else "比肩"
    wx_day = WUXING_GAN[day_gan]
    wx_oth = WUXING_GAN[other_gan]
    day_yin = day_gan in ("乙","丁","己","辛","癸")
    oth_yin = other_gan in ("乙","丁","己","辛","癸")
    same_yin = (day_yin == oth_yin)

    # 生克关系字典: (日主五行, 其他五行) -> (阴阳相同, 阴阳不同)
    rel = {
        ("金","金"):("比肩","劫财"), ("木","木"):("比肩","劫财"),
        ("水","水"):("比肩","劫财"), ("火","火"):("比肩","劫财"),
        ("土","土"):("比肩","劫财"),
        ("金","木"):("偏财","正财"), ("木","土"):("偏财","正财"),
        ("土","水"):("偏财","正财"), ("水","火"):("偏财","正财"),
        ("火","金"):("偏财","正财"),
        ("金","土"):("偏印","正印"), ("木","水"):("偏印","正印"),
        ("水","金"):("偏印","正印"), ("火","木"):("偏印","正印"),
        ("土","火"):("偏印","正印"),
        ("金","火"):("七杀","正官"), ("木","金"):("七杀","正官"),
        ("水","土"):("七杀","正官"), ("火","水"):("七杀","正官"),
        ("土","木"):("七杀","正官"),
        ("金","水"):("食神","伤官"), ("木","火"):("食神","伤官"),
        ("水","木"):("食神","伤官"), ("火","土"):("食神","伤官"),
        ("土","金"):("食神","伤官"),
    }
    pair = (wx_day, wx_oth)
    if pair in rel:
        yang, yin = rel[pair]
        return yang if same_yin else yin
    return ""


def get_ganzhi_str(gz_obj):
    """将 sxtwl 的 GanZhi 对象转为字符串"""
    return TIAN_GAN[gz_obj.tg] + DI_ZHI[gz_obj.dz]


def get_gan(gz_obj):
    return TIAN_GAN[gz_obj.tg]


def get_zhi(gz_obj):
    return DI_ZHI[gz_obj.dz]


def get_dayun_shishen(day_gan, dayun_gan):
    """大运天干的十神（与日干的关系）"""
    return get_shishen(day_gan, dayun_gan)


# ============================
# 主排盘函数
# ============================

def get_jie_date(year, jie_index):
    """获取指定年份节气（节）的儒略日并转为日期对象
    jie_index: 0=冬至, 1=小寒, ..., 23=大雪
    只处理"节"（立春/惊蛰/清明/立夏/芒种/小暑/立秋/白露/寒露/立冬/大雪/小寒）
    """
    # sxtwl 中 getJieQiJD 可能不存在，改用 fromSolar 的 hasJieQi
    # 改为顺着日子找节气
    jie_map = []
    for y in range(year-1, year+2):
        for m in range(1, 13):
            max_d = 31 if m in (1,3,5,7,8,10,12) else 30 if m in (4,6,9,11) else 28
            for d in range(1, max_d+1):
                try:
                    day = sxtwl.fromSolar(y, m, d)
                    if day.hasJieQi():
                        jq = day.getJieQi()
                        if jq == jie_index:
                            jie_map.append((y, m, d, jq))
                except:
                    pass
    # 找出最近的那个
    target = None
    for y, m, d, jq in jie_map:
        if y == year or (jie_index in (1, 23) and m == 1 and y == year) or \
           (jie_index in (21, 23) and m == 12 and y == year-1) or \
           (jie_index == 1 and y == year+1):
            if jq == jie_index:
                if target is None or abs(y - year) < abs(target[0] - year):
                    target = (y, m, d)
    if target:
        return date(target[0], target[1], target[2])
    return None


def get_yearly_jie_table(year):
    """获取指定年份的各个月节（从立春开始的小寒结束）
    返回: [(月支索引, 节气日期), ...]
    月支索引：2=寅(立春), 3=卯(惊蛰), ..., 1=丑(小寒)
    """
    # 节索引(0=冬至, 2=大寒, 4=立春, 6=雨水, 8=惊蛰...)
    # 月节：立春(4), 惊蛰(8), 清明(12), 立夏(16), 芒种(20),
    #       小暑(24→0), 立秋(4), 白露(8), 寒露(12), 立冬(16), 大雪(20), 小寒(24→0)
    # 在24节气中，月节索引为: 4, 8, 12, 16, 20, 0(24), 4, 8, 12, 16, 20, 0(24)
    # 但实际上需要跨年处理
    
    # 使用更直接的方法：对每个月检查节气
    jie_indices = [4, 8, 12, 16, 20, 0, 4, 8, 12, 16, 20, 0]  # 立春到小寒
    zhi_indices = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1]     # 寅卯辰巳午未申酉戌亥子丑
    
    result = []
    for i, jq_idx in enumerate(jie_indices):
        jd = get_jie_date(year, jq_idx)
        if jd:
            result.append((zhi_indices[i], jd))
    return result


def get_jie_table_fast(year):
    """快速获取一年十二个月节日期（不依赖逐日扫描）"""
    # 对每个月，取该月节气的日期
    # sxtwl 的 Day 对象有 getJieQi() 方法，返回节气索引
    # 节气索引: 0=冬至, 1=小寒, 2=大寒, 3=立春, 4=雨水, 5=惊蛰, 6=春分, 7=清明,
    #          8=谷雨, 9=立夏, 10=小满, 11=芒种, 12=夏至, 13=小暑, 14=大暑,
    #          15=立秋, 16=处暑, 17=白露, 18=秋分, 19=寒露, 20=霜降, 21=立冬, 22=小雪, 23=大雪
    
    # "节"为: 立春(3), 惊蛰(5), 清明(7), 立夏(9), 芒种(11),
    #        小暑(13), 立秋(15), 白露(17), 寒露(19), 立冬(21), 大雪(23), 小寒(1)
    jie_indices = [3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 1]
    zhi_indices = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1]  # 寅~丑
    
    result = []
    # 需要跨年扫描
    scan_years = set()
    scan_years.add(year - 1)
    scan_years.add(year)
    scan_years.add(year + 1)
    
    jie_found = {idx: None for idx in jie_indices}
    
    for sy in scan_years:
        for m in range(1, 13):
            max_d = 31 if m in (1,3,5,7,8,10,12) else 30 if m in (4,6,9,11) else 28
            # 小寒在1月，大雪在12月，需要精确到日
            for d in range(1, max_d+1):
                day = sxtwl.fromSolar(sy, m, d)
                if day.hasJieQi():
                    jq = day.getJieQi()
                    if jq in jie_indices and jie_found[jq] is None:
                        jie_found[jq] = date(sy, m, d)
    
    for i, jq_idx in enumerate(jie_indices):
        jd = jie_found[jq_idx]
        if jd:
            result.append((zhi_indices[i], jd))
    
    # 按日期排序
    result.sort(key=lambda x: (x[1].year * 400 + x[1].month * 32 + x[1].day))
    return result


def get_month_zhi_idx(birth_date, jie_table):
    """根据出生日期和节气表，确定月支索引"""
    for i in range(len(jie_table)):
        zhi_idx, jie_date = jie_table[i]
        next_zhi_idx, next_jie_date = jie_table[(i + 1) % len(jie_table)]
        
        # 处理跨年
        if i == len(jie_table) - 1:  # 最后一个节气（小寒），跨到下一个日历年
            # 如果出生日期 >= 小寒 或 < 立春
            if birth_date >= jie_date:
                return zhi_idx
            # 在立春之前
            if birth_date < jie_table[0][1]:
                return zhi_idx
            return jie_table[0][0]
        else:
            if jie_date <= birth_date < next_jie_date:
                return zhi_idx
    
    # 默认
    return jie_table[0][0]


def calc_qiyun(birth_date, year_gan, gender, jie_table):
    """计算起运岁数
    阳男阴女顺排：从生日顺数到下一个节气的天数÷3
    阴男阳女逆排：从生日逆数到上一个节气的天数÷3
    """
    is_yang = year_gan in ("甲","丙","戊","庚","壬")
    is_male = (gender == "男")
    forward = (is_yang and is_male) or (not is_yang and not is_male)
    
    if forward:
        # 顺排：找出生后的下一个节气
        for zhi_idx, jie_date in jie_table:
            if jie_date >= birth_date:
                target = jie_date
                break
        else:
            # 都跨到下一年了
            target = jie_table[0][1].replace(year=jie_table[0][1].year + 1)
        days = (target - birth_date).days
    else:
        # 逆排：找出生前上一个节气
        prev = None
        for zhi_idx, jie_date in reversed(jie_table):
            if jie_date <= birth_date:
                prev = jie_date
                break
        if prev is None:
            prev = jie_table[-1][1].replace(year=jie_table[-1][1].year - 1)
        days = (birth_date - prev).days
    
    years = days // 3
    months = (days % 3) * 4  # 余1天=4个月，余2天=8个月
    return years, months, days


def get_city_longitude(city):
    city_map = {
        "北京":116.4,"上海":121.4,"广州":113.2,"深圳":114.0,
        "天津":117.2,"重庆":106.5,"成都":104.0,"武汉":114.3,
        "南京":118.7,"杭州":120.1,"西安":108.9,"郑州":113.6,
        "沈阳":123.4,"济南":117.0,"哈尔滨":126.6,"昆明":102.7,
        "贵阳":106.7,"南宁":108.3,"福州":119.3,"厦门":118.1,
        "长沙":112.9,"合肥":117.2,"南昌":115.8,"太原":112.5,
        "石家庄":114.5,"呼和浩特":111.7,"乌鲁木齐":87.6,"拉萨":91.1,
        "西宁":101.7,"兰州":103.8,"银川":106.2,"海口":110.3,
        "宝丰":113.0,"安阳":114.3,"洛阳":112.4,"开封":114.3,"平顶山":113.2,
    }
    for k, v in city_map.items():
        if k in city:
            return v
    return 120.0


def bazi_paipan(birth_year, birth_month, birth_day, hour, minute,
                city="北京", gender="男", is_lunar=False):
    """
    八字主排盘函数
    返回完整的命盘字典
    """
    # Step 1: 公历/农历转换
    if is_lunar:
        lunar = LunarDate(birth_year, birth_month, birth_day)
        solar = lunar.toSolarDate()
        solar_year, solar_month, solar_day = solar.year, solar.month, solar.day
        lunar_str = f"{birth_year}年{birth_month}月{birth_day}日"
    else:
        solar_year, solar_month, solar_day = birth_year, birth_month, birth_day
        lunar = LunarDate.from_solar_date(solar_year, solar_month, solar_day)
        lunar_str = f"{lunar.year}年{lunar.month}月{lunar.day}日"

    # Step 2: 真太阳时校正
    longitude = get_city_longitude(city)
    delta_min = (120 - longitude) * 4
    total_min = hour * 60 + minute - delta_min
    if total_min < 0:
        total_min += 1440
    true_h = int(total_min // 60)
    true_m = int(total_min % 60)

    # Step 3: 用 sxtwl 计算四柱
    sol_day = sxtwl.fromSolar(solar_year, solar_month, solar_day)
    ygz = sol_day.getYearGZ()
    mgz = sol_day.getMonthGZ()
    dgz = sol_day.getDayGZ()
    hgz = sol_day.getHourGZ(true_h)

    year_gan, year_zhi = get_gan(ygz), get_zhi(ygz)
    month_gan, month_zhi = get_gan(mgz), get_zhi(mgz)
    day_gan, day_zhi = get_gan(dgz), get_zhi(dgz)
    hour_gan, hour_zhi = get_gan(hgz), get_zhi(hgz)

    # Step 4: 纳音
    nayin_list = [
        get_nayin(year_gan, year_zhi),
        get_nayin(month_gan, month_zhi),
        get_nayin(day_gan, day_zhi),
        get_nayin(hour_gan, hour_zhi),
    ]

    # Step 5: 十神
    shishen_list = [
        get_shishen(day_gan, year_gan),
        get_shishen(day_gan, month_gan),
        "元男" if gender == "男" else "元女",
        get_shishen(day_gan, hour_gan),
    ]

    # Step 6: 藏干及十神
    pillars_zhi = [year_zhi, month_zhi, day_zhi, hour_zhi]
    canggan_data = []
    for zhi in pillars_zhi:
        gans = CANG_GAN[zhi]
        canggan_data.append([(g, get_shishen(day_gan, g)) for g in gans])

    # Step 7: 空亡
    kongwang = KONG_WANG.get(day_zhi, ("",""))

    # Step 8: 五行统计
    all_gans = [year_gan, month_gan, day_gan, hour_gan]
    all_zhiz = [year_zhi, month_zhi, day_zhi, hour_zhi]
    wx_count = {"金":0,"木":0,"水":0,"火":0,"土":0}
    for g in all_gans:
        wx_count[WUXING_GAN[g]] += 1
    for z in all_zhiz:
        wx_count[WUXING_ZHI[z]] += 1

    # Step 9: 大运（用60甲子序数计算）
    is_yang = year_gan in ("甲","丙","戊","庚","壬")
    is_male = (gender == "男")
    forward = (is_yang and is_male) or (not is_yang and not is_male)
    
    month_gi = TIAN_GAN.index(month_gan)
    month_zi = DI_ZHI.index(month_zhi)
    month_seq = (month_gi * 6 - month_zi * 5) % 60  # 60甲子序数（0-based）
    
    dayun_list = []
    for step in range(8):
        if forward:
            new_seq = (month_seq + (step + 1)) % 60
        else:
            new_seq = (month_seq - (step + 1)) % 60
        dy_gan = TIAN_GAN[new_seq % 10]
        dy_zhi = DI_ZHI[new_seq % 12]
        dayun_list.append(f"{dy_gan}{dy_zhi}")

    # Step 10: 起运
    jie_table = get_jie_table_fast(solar_year)
    qiyun_years, qiyun_months, days_diff = calc_qiyun(
        date(solar_year, solar_month, solar_day), year_gan, gender, jie_table
    )
    qiyun_calendar_year = solar_year + qiyun_years

    # Step 11: 大运详细
    dayun_detail = []
    for i, dy in enumerate(dayun_list):
        start_year = qiyun_calendar_year + i * 10
        end_year = start_year + 9
        start_age = qiyun_years + i * 10
        end_age = start_age + 9
        dy_gan = dy[0]
        dayun_detail.append({
            "ganzhi": dy,
            "shishen": get_shishen(day_gan, dy_gan),
            "start_age": start_age + 1,  # 虚岁
            "end_age": end_age + 1,
            "start_year": start_year,
            "end_year": end_year,
        })

    # Step 12: 当前年龄和大运
    today = date.today()
    current_year = today.year
    age = current_year - solar_year  # 周岁
    xusui = age + 1  # 虚岁

    current_dayun = None
    for dy in dayun_detail:
        if dy["start_age"] <= xusui <= dy["end_age"]:
            current_dayun = dy
            break

    # Step 13: 流年（以立春为界跨年）
    # 用2月15日这个一定在立春之后的日子来获取当前年份的年柱
    if current_year >= 2023:
        # 直接取立春后某一天的年干支
        liunian_day = sxtwl.fromSolar(current_year, 2, 15)
    else:
        liunian_day = sxtwl.fromSolar(current_year, 6, 1)
    l_gz = liunian_day.getYearGZ()
    l_gan = get_gan(l_gz)
    l_zhi = get_zhi(l_gz)

    return {
        "solar": f"{solar_year}年{solar_month}月{solar_day}日",
        "lunar": lunar_str,
        "city": city,
        "longitude": longitude,
        "original_time": f"{hour:02d}:{minute:02d}",
        "corrected_time": f"{true_h:02d}:{true_m:02d}",
        "time_diff_minutes": round(delta_min, 1),
        "gender": gender,
        "age": age,
        "xusui": xusui,
        "current_year": current_year,
        "pillars": {
            "year": {"gan": year_gan, "zhi": year_zhi, "nayin": nayin_list[0]},
            "month": {"gan": month_gan, "zhi": month_zhi, "nayin": nayin_list[1]},
            "day": {"gan": day_gan, "zhi": day_zhi, "nayin": nayin_list[2]},
            "hour": {"gan": hour_gan, "zhi": hour_zhi, "nayin": nayin_list[3]},
        },
        "shishen": {
            "year": shishen_list[0], "month": shishen_list[1],
            "day": shishen_list[2], "hour": shishen_list[3],
        },
        "canggan": {
            "year": canggan_data[0], "month": canggan_data[1],
            "day": canggan_data[2], "hour": canggan_data[3],
        },
        "kongwang": kongwang,
        "wuxing": wx_count,
        "dayun": dayun_detail,
        "current_dayun": current_dayun,
        "qiyun": {
            "years": qiyun_years + 1,  # 虚岁
            "calendar_year": qiyun_calendar_year,
        },
        "liunian": {
            "gan": l_gan,
            "zhi": l_zhi,
            "shishen": get_shishen(day_gan, l_gan),
        },
    }


# ============================
# 命令行入口
# ============================

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(json.dumps({"error": "参数不足。用法: python bazi.py <年> <月> <日> <时> <分> [地点] [性别] [is_lunar]"}))
        sys.exit(1)
    
    year = int(sys.argv[1])
    month = int(sys.argv[2])
    day = int(sys.argv[3])
    hour = int(sys.argv[4])
    minute = int(sys.argv[5])
    city = sys.argv[6] if len(sys.argv) > 6 else "北京"
    gender = sys.argv[7] if len(sys.argv) > 7 else "男"
    is_lunar = sys.argv[8].lower() in ("true","1","yes") if len(sys.argv) > 8 else False

    data = bazi_paipan(year, month, day, hour, minute, city, gender, is_lunar)
    print(json.dumps(data, ensure_ascii=False, indent=2))
