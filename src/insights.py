# src/insights.py
import re
from typing import List, Dict
from sqlalchemy import select, desc
from sklearn.feature_extraction.text import CountVectorizer

from .db import SessionLocal
from .models import Review

# 한국어/일반 리뷰에서 자주 등장하는 의미 없는 단어들(필요시 계속 추가)
STOPWORDS = {
    "그리고","하지만","해서","해서요","정말","진짜","너무","조금","약간","그냥","아주","매우","많이",
    "제품","상품","구매","사용","리뷰","후기","평가","배송","포장","판매자","구매자","가격","사진",
    "같아요","같습니다","듯","부분","정도","이번","이것","저것","그것","거","것","때","보고","보고싶",
    "좋아요","괜찮아요","추천","비추","만족","불만","최고","최악","문의","답변","설명","상세",
}

PAIN_KEYWORDS = {
    "가격":        ["가격","가성비","비싸","비용","할인","쿠폰"],
    "배송/포장":   ["배송","포장","파손","늦","지연","빠르","택배"],
    "색상/이미지": ["색상","색깔","컬러","사진","이미지","화면","실물","색감"],
    "사이즈/규격": ["사이즈","크기","규격","높이","폭","길이","두께","맞지"],
    "내구성/품질": ["내구","튼튼","약함","헐겁","부러","스크래치","하자","불량","휘어","찍힘"],
    "설치/조립":   ["설치","조립","설명서","드라이버","피스","구멍","수평","볼트","나사"],
    "냄새/소음":   ["냄새","향","소음","삐걱","삑","소리"],
    "착석감/사용감":["편하","불편","앉았","쿠션","등받이","허리","딱딱","푹신"],
}

TOKEN_PATTERN = r"(?u)[가-힣A-Za-z]{2,}"  # 한글/영문 2자 이상 토큰

def _normalize(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\n"," ").strip()
    t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t

def _fetch_texts(limit: int = 1000, source: str | None = None) -> List[str]:
    with SessionLocal() as s:
        stmt = select(Review.body).where(Review.body.is_not(None))
        if source:
            stmt = stmt.where(Review.source == source)
        stmt = stmt.order_by(desc(Review.id)).limit(limit)
        rows = s.execute(stmt).all()
    return [r[0] for r in rows if r and r[0]]

def _top_ngrams(texts: List[str], ngram=(1,1), topk=15, min_df=2):
    if not texts:
        return []
    docs = [_normalize(t) for t in texts]
    vec = CountVectorizer(
        token_pattern=TOKEN_PATTERN,
        stop_words=STOPWORDS,
        min_df=min_df,
        ngram_range=ngram
    )
    X = vec.fit_transform(docs)
    vocab = vec.get_feature_names_out()
    counts = X.sum(axis=0).A1
    order = counts.argsort()[::-1][:topk]
    return [{"term": vocab[i], "freq": int(counts[i])} for i in order]

def _pain_point_counts(texts: List[str]):
    out = []
    for label, kws in PAIN_KEYWORDS.items():
        pat = re.compile("|".join([re.escape(k) for k in kws]))
        c = sum(1 for t in texts if t and pat.search(t))
        if c > 0:
            out.append({"label": label, "count": c})
    out.sort(key=lambda x: x["count"], reverse=True)
    return out

def compute_insights(limit=1000, source: str | None = None, topk=15, min_df=2) -> Dict:
    texts = _fetch_texts(limit=limit, source=source)
    if not texts:
        return {"total": 0, "top_terms": [], "top_bigrams": [], "pain_points": []}

    top_terms   = _top_ngrams(texts, ngram=(1,1), topk=topk, min_df=min_df)
    top_bigrams = _top_ngrams(texts, ngram=(2,2), topk=topk, min_df=min_df)
    pains       = _pain_point_counts(texts)

    return {
        "total": len(texts),
        "top_terms": top_terms,
        "top_bigrams": top_bigrams,
        "pain_points": pains,
    }