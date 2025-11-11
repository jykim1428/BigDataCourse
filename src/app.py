# src/app.py
from flask import Flask, request, jsonify
from sqlalchemy import select, desc
from hashlib import sha256

from .db import SessionLocal
from .models import Review
from .insights import compute_insights

app = Flask(__name__)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/reviews")
def list_reviews():
    limit = int(request.args.get("limit", 20))
    source = request.args.get("source")
    with SessionLocal() as s:
        stmt = select(Review).order_by(desc(Review.id)).limit(limit)
        if source:
            stmt = select(Review).where(Review.source == source).order_by(desc(Review.id)).limit(limit)
        rows = s.execute(stmt).scalars().all()
    return jsonify([
        {"id": r.id, "source": r.source, "rating": r.rating, "body": r.body,
         "review_date": r.review_date, "product_url": r.product_url}
        for r in rows
    ])

@app.post("/api/reviews")
def create_review():
    d = request.get_json(force=True) or {}
    h = d.get("hash_id") or sha256((str(d.get("body","")) + str(d.get("review_date",""))).encode()).hexdigest()
    rv = Review(
        source=d.get("source","partner"),
        product_url=d.get("product_url"),
        rating=d.get("rating"),
        body=d.get("body"),
        review_date=d.get("review_date"),
        hash_id=h,
    )
    with SessionLocal() as s:
        s.add(rv); s.commit(); s.refresh(rv)
        return {"id": rv.id}, 201

@app.get("/api/insights")
def api_insights():
    limit  = int(request.args.get("limit", 1000))
    source = request.args.get("source")  # e.g. "coupang"
    topk   = int(request.args.get("topk", 15))
    min_df = int(request.args.get("min_df", 2))
    data = compute_insights(limit=limit, source=source, topk=topk, min_df=min_df)
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)