import argparse, json
import pandas as pd
from sqlalchemy.exc import IntegrityError
from ..db import SessionLocal
from ..models import Review
from ..utils import review_hash

# 예시 프리셋: 각자 컬럼명에 맞게 수정
PRESETS = {
    "smartstore": {"product_url":"상품URL","rating":"평점","body":"리뷰내용","review_date":"작성일"},
    "todayhouse": {"product_url":"product_url","rating":"rating","body":"content","review_date":"created_at"},
    "generic":    {"product_url":"product_url","rating":"rating","body":"body","review_date":"review_date"},
}

def ingest_csv(path: str, source: str, preset: str):
    m = PRESETS[preset]
    df = pd.read_csv(path)
    inserted, dup = 0, 0
    with SessionLocal() as s:
        for _, r in df.iterrows():
            product_url = r.get(m["product_url"])
            rating = r.get(m["rating"])
            try:
                rating = float(rating) if rating==rating else None  # NaN 체크
            except Exception:
                rating = None
            body = r.get(m["body"])
            review_date = str(r.get(m["review_date"]))

            h = review_hash(source, product_url, body, review_date)
            rv = Review(
                source=source, product_url=product_url, rating=rating,
                body=body, review_date=review_date, hash_id=h
            )
            try:
                s.add(rv); s.commit(); inserted += 1
            except IntegrityError:
                s.rollback(); dup += 1
    print(f"[OK] inserted={inserted}, duplicated={dup}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--source", required=True, help="예: smartstore/todayhouse/partner 등")
    ap.add_argument("--preset", choices=list(PRESETS.keys()), default="generic")
    args = ap.parse_args()
    ingest_csv(args.path, args.source, args.preset)

if __name__ == "__main__":
    main()