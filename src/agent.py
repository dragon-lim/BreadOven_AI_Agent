import pandas as pd

# CSV 파일 읽어오기
inventory = pd.read_csv("data/inventory.csv")
recipes = pd.read_csv("data/recipes.csv")
daily_production = pd.read_csv("data/daily_production.csv")
production_plan = pd.read_csv("data/production_plan.csv")

# 파일 리디 확인
print("=== 재고 현황 ===")
print(inventory)

print("\n=== 레시피 ===")
print(recipes)

print("\n=== 요일별 생산량 ===")
print(daily_production)
