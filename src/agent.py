# import os
# from datetime import datetime
# from pathlib import Path
# import pandas as pd
# from dotenv import load_dotenv


# # 실행 위치와 관계없이 프로젝트 폴더를 기준으로 경로 설정
# BASE_DIR = Path(__file__).resolve().parent.parent
# DATA_DIR = BASE_DIR / "data"


# # .env 파일에서 API 키 불러오기
# load_dotenv(BASE_DIR / ".env")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# # CSV 파일 읽어오기
# inventory = pd.read_csv(DATA_DIR / "inventory.csv")
# recipes = pd.read_csv(DATA_DIR / "recipes.csv")
# daily_production = pd.read_csv(DATA_DIR / "daily_production.csv")
# # TODO: data/production_plan.csv 파일을 만든 뒤 주석 해제
# # production_plan = pd.read_csv(DATA_DIR / "production_plan.csv")


# # # 파일 리디 확인
# # print("=== 재고 현황 ===")
# # print(inventory)

# # print("\n=== 레시피 ===")
# # print(recipes)

# # print("\n=== 요일별 생산량 ===")
# # print(daily_production)


# # 오늘 요일의 생산량만 추출 (weekday(): 월=0 ~ 일=6)
# today = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]
# today_production = daily_production[daily_production["day"] == today]


# # 오늘 생산량 × 레시피 = 필요 재료량 계산
# needed = pd.merge(today_production, recipes, on="product")
# needed["total_needed"] = needed["quantity"] * needed["amount_per_unit"]


# # 같은 재료는 합산
# needed_summary = needed.groupby(["ingredient", "unit"])["total_needed"].sum().reset_index()


# # 출력 형식 정리
# pd.set_option("display.unicode.east_asian_width", True)  # 한글 폭 맞춤


# def fmt(value, unit=""):
#     """정수는 소수점 없이, 소수는 한 자리까지, 천 단위 쉼표를 붙여 표시"""
#     text = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
#     return f"{text} {unit}".strip()


# def print_section(title, table, empty_message):
#     print(f"\n=== {title} ===")
#     print(empty_message if table.empty else table.to_string(index=False))


# # 오늘 필요한 총 재료량
# needed_view = pd.DataFrame({
#     "재료": needed_summary["ingredient"],
#     "필요량": [fmt(v, u) for v, u in zip(needed_summary["total_needed"], needed_summary["unit"])],
# })
# print_section(f"오늘({today}요일) 필요한 총 재료량", needed_view, "생산 계획 없음")


# # 재고 vs 필요량 비교
# comparison = pd.merge(needed_summary, inventory, on="ingredient")
# comparison["shortage"] = comparison["total_needed"] - comparison["current_stock"]


# # 부족한 재료만 필터링
# shortage = comparison[comparison["shortage"] > 0]
# shortage_view = pd.DataFrame({
#     "재료": shortage["ingredient"],
#     "현재재고": [fmt(v, u) for v, u in zip(shortage["current_stock"], shortage["unit_x"])],
#     "필요량": [fmt(v, u) for v, u in zip(shortage["total_needed"], shortage["unit_x"])],
#     "부족량": [fmt(v, u) for v, u in zip(shortage["shortage"], shortage["unit_x"])],
# })
# print_section("⚠️ 발주 필요 재료", shortage_view, "부족한 재료 없음")


# # 유통기한 임박 경고 (3일 이내)
# def parse_expiry(expiry_str):
#     """'+7d', '+3m', '+1y' 형식을 남은 일수로 변환"""
#     number = int(expiry_str[1:-1])
#     return number * {"d": 1, "m": 30, "y": 365}[expiry_str[-1]]


# inventory["days_left"] = inventory["expiry"].apply(parse_expiry)

# expiring = inventory[inventory["days_left"] <= 3]
# expiry_view = pd.DataFrame({
#     "재료": expiring["ingredient"],
#     "남은일수": [f"{d}일" for d in expiring["days_left"]],
#     "현재재고": [fmt(v, u) for v, u in zip(expiring["current_stock"], expiring["unit"])],
# })
# print_section("🚨 유통기한 임박 (3일 이내)", expiry_view, "임박 재료 없음")


# print("=" * 45)
# print(f"  🍞 빵집 재고 분석 리포트 | {datetime.today().strftime('%Y-%m-%d %A')}")
# print("=" * 45)

# print("\n" + "=" * 45)
# print("  ✅ 분석 완료")
# print("=" * 45)





import os
from datetime import datetime
from pathlib import Path

import openai
import pandas as pd
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# 실행 위치와 관계없이 프로젝트 폴더를 기준으로 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# .env 파일에서 API 키와 모델 이름 불러오기
load_dotenv(BASE_DIR / ".env")
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-sol")

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def get_today():
    return WEEKDAYS[datetime.today().weekday()]


def get_tomorrow():
    return WEEKDAYS[(datetime.today().weekday() + 1) % 7]


# ── 도구 정의 ──────────────────────────────────────────

@tool
def get_tomorrow_production() -> str:
    """내일 요일에 맞는 생산 계획을 반환한다."""
    daily = pd.read_csv(DATA_DIR / "daily_production.csv")
    tomorrow = get_tomorrow()
    result = daily[daily["day"] == tomorrow][["product", "quantity"]]
    return f"내일({tomorrow}요일) 생산 계획:\n{result.to_string(index=False)}"


@tool
def calculate_shortage() -> str:
    """내일 생산에 필요한 재료량과 최소 재고를 합해 현재 재고와 비교하고, 부족한 재료와 주문 수량을 반환한다.
    발주 후 내일 생산을 마쳐도 최소 재고(min_stock) 이상이 남도록 계산한다."""
    import math
    daily = pd.read_csv(DATA_DIR / "daily_production.csv")
    recipes = pd.read_csv(DATA_DIR / "recipes.csv")
    inventory = pd.read_csv(DATA_DIR / "inventory.csv")
    order_units = pd.read_csv(DATA_DIR / "order_units.csv")

    tomorrow_prod = daily[daily["day"] == get_tomorrow()]
    needed = pd.merge(tomorrow_prod, recipes, on="product")
    needed["total_needed"] = needed["quantity"] * needed["amount_per_unit"]
    needed_summary = needed.groupby("ingredient")["total_needed"].sum().reset_index()

    # 내일 쓰지 않는 재료도 최소 재고 아래면 발주하도록 전체 재고 기준으로 합침
    comparison = pd.merge(inventory, needed_summary, on="ingredient", how="left")
    comparison["total_needed"] = comparison["total_needed"].fillna(0)

    # 부족량 = (내일 필요량 + 최소 재고) - 현재 재고
    comparison["shortage"] = comparison["total_needed"] + comparison["min_stock"] - comparison["current_stock"]
    shortage = comparison[comparison["shortage"] > 0].copy()

    if shortage.empty:
        return f"내일({get_tomorrow()}요일) 생산 기준 부족한 재료 없음"

    shortage = pd.merge(shortage, order_units[["ingredient", "order_unit", "order_size"]], on="ingredient")
    shortage["주문수량"] = shortage.apply(lambda r: math.ceil(r["shortage"] / r["order_size"]), axis=1)

    result = shortage[[
        "ingredient", "current_stock", "total_needed", "min_stock", "shortage", "주문수량", "order_unit", "unit",
    ]].copy()
    result.columns = ["재료", "현재재고", "내일필요량", "최소재고", "부족량", "주문수량", "주문단위", "단위"]
    return f"내일({get_tomorrow()}요일) 생산 기준 발주 필요 재료:\n{result.to_string(index=False)}"


def parse_expiry(s):
    """'+7d', '+3m', '+1y' 형식을 남은 일수로 변환"""
    return int(s[1:-1]) * {"d": 1, "m": 30, "y": 365}[s[-1]]


@tool
def check_expiry() -> str:
    """유통기한이 7일 이내로 임박한 재료를 반환한다."""
    inventory = pd.read_csv(DATA_DIR / "inventory.csv")

    inventory["days_left"] = inventory["expiry"].apply(parse_expiry)
    warning = inventory[inventory["days_left"] <= 7][["ingredient", "days_left", "current_stock", "unit"]]

    if warning.empty:
        return "유통기한 임박 재료 없음"
    return f"유통기한 임박 재료:\n{warning.to_string(index=False)}"


@tool
def recommend_products() -> str:
    """유통기한 임박 재료(7일 이내)를 가장 많은 종류로 사용하는 제품 1개와, 현재 임박 재료 재고로 만들 수 있는 생산 수량을 추천한다."""
    import math
    recipes = pd.read_csv(DATA_DIR / "recipes.csv")
    inventory = pd.read_csv(DATA_DIR / "inventory.csv")

    inventory["days_left"] = inventory["expiry"].apply(parse_expiry)
    expiring = inventory[inventory["days_left"] <= 7]
    if expiring.empty:
        return "유통기한 임박 재료가 없어 추천할 제품 없음"
    expiring_stock = expiring.set_index("ingredient")["current_stock"]

    # 제품별 임박 재료 사용 현황
    rows = []
    for product, recipe in recipes.groupby("product"):
        used = recipe[recipe["ingredient"].isin(expiring_stock.index)]
        if used.empty:
            continue
        # 현재 임박 재료 재고만으로 만들 수 있는 수량 (가장 먼저 떨어지는 임박 재료 기준)
        qty = min(math.floor(expiring_stock[r.ingredient] / r.amount_per_unit) for r in used.itertuples())
        rows.append({
            "제품": product,
            "추천 수량": qty,
            "사용하는 임박 재료": ", ".join(used["ingredient"]),
            "종류 수": len(used),
            "총 사용량": qty * used["amount_per_unit"].sum(),
        })

    # 임박 재료를 가장 많은 종류로 쓰는 제품 우선, 같으면 임박 재료 총 사용량이 많은 제품
    best = pd.DataFrame(rows).sort_values(["종류 수", "총 사용량"], ascending=False).iloc[0]
    if best["추천 수량"] == 0:
        return f"추천할 제품 없음 ({best['제품']}을(를) 1개 만들 만큼의 임박 재료 재고가 없음)"

    # 추천 수량만큼 생산했을 때 임박 재료별 사용량과 남는 양
    recipe = recipes[(recipes["product"] == best["제품"]) & recipes["ingredient"].isin(expiring_stock.index)]
    usage = pd.DataFrame({
        "재료": recipe["ingredient"],
        "남은일수": recipe["ingredient"].map(expiring.set_index("ingredient")["days_left"]),
        "현재재고": recipe["ingredient"].map(expiring_stock),
        "사용량": recipe["amount_per_unit"] * best["추천 수량"],
        "단위": recipe["unit"],
    })
    usage["사용후남는양"] = usage["현재재고"] - usage["사용량"]

    return (
        f"추천 제품: {best['제품']} {best['추천 수량']}개 (임박 재료 {best['종류 수']}종 사용: {best['사용하는 임박 재료']})\n"
        f"임박 재료별 사용량:\n{usage.to_string(index=False)}"
    )


@tool
def get_recipes() -> str:
    """모든 제품의 레시피(제품별 재료와 제품 1개당 재료 사용량)를 계산 없이 그대로 반환한다."""
    recipes = pd.read_csv(DATA_DIR / "recipes.csv")
    return f"레시피 (제품 1개당 사용량):\n{recipes.to_string(index=False)}"


# ── Agent 구성 ──────────────────────────────────────────

# 추천 생산 제품을 정하는 방식
#   "rule": recommend_products 도구가 파이썬으로 계산해 답을 줌
#   "llm" : 도구는 레시피 원본만 주고, 모델이 지침만 보고 직접 판단·계산함
RECOMMEND_MODE = os.getenv("RECOMMEND_MODE", "llm")

RECOMMEND_RULES = {
    "rule": """(표 바로 아래에 위 두 줄을 그대로 쓰고, {제품}과 {수량}은 recommend_products 도구 결과로 채우기)
(추천할 제품이 없으면 "추천 물량: 없음"이라고 쓰기)""",
    "llm": """(표 바로 아래에 위 두 줄을 그대로 쓰기)
{제품}과 {수량}은 get_recipes 도구의 레시피와 check_expiry 도구의 임박 재료 재고를 보고 당신이 직접 정하세요.
- 제품 선택: 유통기한 임박 재료를 가장 많은 종류로 사용하는 제품 1개를 고르기.
  종류 수가 같으면 임박 재료를 더 많이 소진하는 제품을 고르기.
- 수량: 고른 제품에 들어가는 임박 재료마다 (현재 재고 ÷ 제품 1개당 사용량)을 계산해 소수점은 버리고,
  그중 가장 작은 값을 추천 수량으로 하기. 임박 재료가 아닌 재료와 내일 생산 계획은 고려하지 않기.
(추천할 제품이 없으면 "추천 물량: 없음"이라고 쓰기)""",
}[RECOMMEND_MODE]

recommend_tool = recommend_products if RECOMMEND_MODE == "rule" else get_recipes
tools = [get_tomorrow_production, calculate_shortage, check_expiry, recommend_tool]

llm = ChatOpenAI(model=MODEL)

SYSTEM_PROMPT = f"""당신은 빵집 재고 관리 AI Agent입니다.
발주는 매일 퇴근 전 진행 됩니다.
당신이 계산해야 하는건 오늘의 발주 상황이 아니라 내일을 위한 발주 상황입니다.
퇴근하기 전, 직원 발주하기 전 당신에게 현재 재고 상황과 내일 생산량을 비교해 주문해야하는 발주량을 물어봅니다, 책임감을 가지고 안내하십쇼
주어진 도구를 사용해 현재 재고와 내일 생산 계획을 비교하고, 아래 형식의 마크다운으로 한국어로 간결하게 보고하세요.

## 발주 필요 재료
제품 - | 재료 | 현재 재고 - 내일 필요량 (부족한 수량) | 추천 주문 수량 |
(주문 수량은 "2포대"처럼 도구가 준 주문수량과 주문단위를 붙여 쓰기)
(부족한 재료가 없으면 "없음"이라고 쓰기)

## 유통기한 임박 재료
| 재료 | 남은 일수 | 현재 재고 |
(임박 재료가 없으면 "없음"이라고 쓰기)

**추천 물량: {{제품}} (약 {{수량}}개) 추천**
※ 유통기한 임박 물량은 생산 전 다른 재료의 수량을 확인하세요
{RECOMMEND_RULES}

제품 이름과 재료 이름은 도구 결과(recipes.csv에 등록된 이름)를 글자 그대로 쓰고, 줄이거나 바꿔 부르지 마세요.
위 형식 외에 요약, 확인 사항, 주의 문구, 계산 방식 설명 등 다른 문장은 쓰지 마세요.
수량에는 천 단위 쉼표와 단위를 붙이세요."""

agent = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

# 도구 이름을 화면에 보여줄 한국어 이름
TOOL_LABELS = {
    "get_tomorrow_production": "내일 생산 계획 조회",
    "calculate_shortage": "재료 부족량 계산",
    "check_expiry": "유통기한 확인",
    "recommend_products": "추천 생산 제품 계산",
    "get_recipes": "레시피 조회",
}

# OpenAI 오류를 짧은 안내 문구로 변환
API_ERROR_MESSAGES = {
    openai.AuthenticationError: "API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY를 확인해 주세요.",
    openai.RateLimitError: "API 크레딧이 부족하거나 요청 한도를 넘었습니다. OpenAI 결제 페이지를 확인해 주세요.",
    openai.NotFoundError: f"모델 '{MODEL}'을(를) 찾을 수 없습니다. .env의 OPENAI_MODEL을 확인해 주세요.",
    openai.APIConnectionError: "OpenAI 서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.",
}

# ── 실행 ──────────────────────────────────────────────

console = Console()
console.print(Panel(
    f"[bold]🍞 빵집 재고 관리 AI Agent[/bold]\n{datetime.today().strftime('%Y-%m-%d')} ({get_today()}요일) · 발주 기준: 내일({get_tomorrow()}요일) · 모델: {MODEL}",
    expand=False,
))

try:
    with console.status("재고를 분석하는 중..."):
        result = agent.invoke({
            "messages": [{"role": "user", "content": f"오늘은 {get_today()}요일이야. 현재 재고와 내일({get_tomorrow()}요일) 생산량을 비교해서 발주가 필요한 재료와 유통기한 임박 재료를 알려줘."}]
        })
except openai.APIError as e:
    message = next((m for cls, m in API_ERROR_MESSAGES.items() if isinstance(e, cls)), str(e))
    console.print(f"[bold red]❌ 오류:[/bold red] {message}")
    raise SystemExit(1)

# Agent가 사용한 도구 목록
used_tools = [call["name"] for msg in result["messages"] for call in getattr(msg, "tool_calls", [])]
for name in used_tools:
    console.print(f"[dim]  ✔ {TOOL_LABELS.get(name, name)}[/dim]")

console.print()
console.print(Panel(Markdown(result["messages"][-1].text), title=f"📋 내일({get_tomorrow()}요일) 발주 리포트", border_style="cyan"))
