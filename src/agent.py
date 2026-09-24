from datetime import datetime
from pathlib import Path

import pandas as pd

# 실행 위치와 관계없이 프로젝트의 data 폴더를 가리키도록 설정
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# CSV 파일 읽어오기
inventory = pd.read_csv(DATA_DIR / "inventory.csv")
recipes = pd.read_csv(DATA_DIR / "recipes.csv")
daily_production = pd.read_csv(DATA_DIR / "daily_production.csv")
# TODO: data/production_plan.csv 파일을 만든 뒤 주석 해제
# production_plan = pd.read_csv(DATA_DIR / "production_plan.csv")

# # 파일 리디 확인
# print("=== 재고 현황 ===")
# print(inventory)

# print("\n=== 레시피 ===")
# print(recipes)

# print("\n=== 요일별 생산량 ===")
# print(daily_production)


# 오늘 요일의 생산량만 추출 (weekday(): 월=0 ~ 일=6)
today = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]
today_production = daily_production[daily_production["day"] == today]

# 오늘 생산량 × 레시피 = 필요 재료량 계산
needed = pd.merge(today_production, recipes, on="product")
needed["total_needed"] = needed["quantity"] * needed["amount_per_unit"]

# 같은 재료는 합산
needed_summary = needed.groupby(["ingredient", "unit"])["total_needed"].sum().reset_index()

# 출력 형식 정리
pd.set_option("display.unicode.east_asian_width", True)  # 한글 폭 맞춤


def fmt(value, unit=""):
    """정수는 소수점 없이, 소수는 한 자리까지, 천 단위 쉼표를 붙여 표시"""
    text = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
    return f"{text} {unit}".strip()


def print_section(title, table, empty_message):
    print(f"\n=== {title} ===")
    print(empty_message if table.empty else table.to_string(index=False))


# 오늘 필요한 총 재료량
needed_view = pd.DataFrame({
    "재료": needed_summary["ingredient"],
    "필요량": [fmt(v, u) for v, u in zip(needed_summary["total_needed"], needed_summary["unit"])],
})
print_section(f"오늘({today}요일) 필요한 총 재료량", needed_view, "생산 계획 없음")

# 재고 vs 필요량 비교
comparison = pd.merge(needed_summary, inventory, on="ingredient")
comparison["shortage"] = comparison["total_needed"] - comparison["current_stock"]

# 부족한 재료만 필터링
shortage = comparison[comparison["shortage"] > 0]
shortage_view = pd.DataFrame({
    "재료": shortage["ingredient"],
    "현재재고": [fmt(v, u) for v, u in zip(shortage["current_stock"], shortage["unit_x"])],
    "필요량": [fmt(v, u) for v, u in zip(shortage["total_needed"], shortage["unit_x"])],
    "부족량": [fmt(v, u) for v, u in zip(shortage["shortage"], shortage["unit_x"])],
})
print_section("⚠️ 발주 필요 재료", shortage_view, "부족한 재료 없음")


# 유통기한 임박 경고 (3일 이내)
def parse_expiry(expiry_str):
    """'+7d', '+3m', '+1y' 형식을 남은 일수로 변환"""
    number = int(expiry_str[1:-1])
    return number * {"d": 1, "m": 30, "y": 365}[expiry_str[-1]]


inventory["days_left"] = inventory["expiry"].apply(parse_expiry)

expiring = inventory[inventory["days_left"] <= 3]
expiry_view = pd.DataFrame({
    "재료": expiring["ingredient"],
    "남은일수": [f"{d}일" for d in expiring["days_left"]],
    "현재재고": [fmt(v, u) for v, u in zip(expiring["current_stock"], expiring["unit"])],
})
print_section("🚨 유통기한 임박 (3일 이내)", expiry_view, "임박 재료 없음")


print("=" * 45)
print(f"  🍞 빵집 재고 분석 리포트 | {datetime.today().strftime('%Y-%m-%d %A')}")
print("=" * 45)

print("\n" + "=" * 45)
print("  ✅ 분석 완료")
print("=" * 45)
