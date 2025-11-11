# src/collectors/coupang_selenium.py
import os, re, time, random, argparse
from pathlib import Path
from typing import List, Dict
from urllib.parse import urlparse

from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import JavascriptException
from webdriver_manager.chrome import ChromeDriverManager

from sqlalchemy.exc import IntegrityError
from ..db import SessionLocal
from ..models import Review
from ..utils import review_hash


# ---------------------- 로그/파일 유틸 ----------------------
def _log(*args):
    print("[COUPANG]", *args, flush=True)

def _mkdir_storage():
    Path("storage").mkdir(parents=True, exist_ok=True)

def _snap(driver, name: str):
    _mkdir_storage()
    path = f"storage/{name}.png"
    try:
        driver.save_screenshot(path)
        _log(f"screenshot saved: {path}")
    except Exception as e:
        _log(f"screenshot failed: {e}")

def _dump_html(driver, name: str):
    _mkdir_storage()
    path = f"storage/{name}.html"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
        _log(f"html saved: {path}")
    except Exception as e:
        _log(f"html dump failed: {e}")


# ---------------------- Anti-bot 감지 ----------------------
def _is_bot_challenge(html: str) -> bool:
    # 네가 올린 loaded.html 패턴(차단 페이지) 탐지용
    if not html:
        return False
    signs = ["XMLHttpRequest.prototype.send", "location.reload(true)", "t="]
    return all(s in html for s in signs)


# ---------------------- 드라이버 생성 ----------------------
def _new_driver():
    """
    1) CHROME_DEBUGGING_ADDR 환경변수가 있으면 '실제 크롬(내 프로필)'에 attach
    2) 없으면 webdriver-manager로 새 크롬 구동
    3) 프록시는 CHROME_PROXY로 지정 가능(옵션)
    * 문제 야기했던 excludeSwitches/useAutomationExtension은 사용하지 않음
    """
    load_dotenv()
    addr = os.getenv("CHROME_DEBUGGING_ADDR", "").strip()
    proxy = os.getenv("CHROME_PROXY", "").strip()

    opts = webdriver.ChromeOptions()
    # 필요하면 다음 줄 주석 해제: opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--lang=ko-KR")
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    opts.add_argument(f"--user-agent={ua}")
    if proxy:
        opts.add_argument(f"--proxy-server={proxy}")

    if addr:
        # 내 크롬에 붙어 내 쿠키/지문 그대로 사용
        opts.add_experimental_option("debuggerAddress", addr)
        driver = webdriver.Chrome(options=opts)
    else:
        # 새 세션
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    # webdriver 흔적 최소화(CDP 가능할 때만)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        })
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": ua, "acceptLanguage": "ko-KR,ko;q=0.9", "platform": "macOS"
        })
    except Exception:
        pass

    driver.implicitly_wait(2)
    return driver


# ---------------------- 쿠키 주입(선택) ----------------------
def _parse_cookie_string(cookie_str: str) -> List[Dict]:
    out = []
    for part in (cookie_str or "").split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k:
            out.append({"name": k, "value": v})
    return out

def _apply_cookies_if_any(driver, url: str):
    """
    .env 의 COUPANG_COOKIES 를 name=value; name2=value2 형태로 주입.
    attach 모드에선 이미 내 브라우저 쿠키가 있으므로 보통 불필요.
    """
    cookie_str = os.getenv("COUPANG_COOKIES", "").strip()
    if not cookie_str:
        return False
    cookies = _parse_cookie_string(cookie_str)
    if not cookies:
        return False

    driver.get(url)
    time.sleep(1.0)
    domain = urlparse(url).hostname or "www.coupang.com"

    ok = 0
    for c in cookies:
        ck = {"name": c["name"], "value": c["value"], "domain": domain, "path": "/"}
        try:
            driver.add_cookie(ck)
            ok += 1
        except Exception:
            continue

    driver.get(url)  # 쿠키 반영 위해 재접속
    _log(f"applied cookies: {ok}")
    return ok > 0


# ---------------------- 스크롤/펼치기 ----------------------
def _deep_scroll(driver, loops=12):
    for _ in range(loops):
        try:
            driver.execute_script("window.scrollBy(0, Math.max(600, window.innerHeight*0.9));")
        except JavascriptException:
            pass
        time.sleep(random.uniform(0.35, 0.75))

def _expand_more_in_reviews(driver):
    # 리뷰 본문 '더보기', '펼치기' 버튼 클릭
    for xp in [
        "//button[contains(.,'더보기')]",
        "//button[contains(.,'펼치기')]",
        "//a[contains(.,'더보기')]",
        "//a[contains(.,'펼치기')]",
    ]:
        btns = driver.find_elements(By.XPATH, xp)
        for b in btns[:20]:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                time.sleep(0.15)
                driver.execute_script("arguments[0].click();", b)
                time.sleep(0.2)
            except Exception:
                pass


# ---------------------- 컨테이너 감지 ----------------------
def _wait_review_area(driver, wait) -> bool:
    selectors = [
        "article.sdp-review__article__list",
        "[class*='sdp-review__article__list']",
        "[class*='sdp-review__article__']",
        "section[id*='review'] article",
        "div[id*='review'] article",
        "#btfTab ~ section article",
        "#btfTab ~ div article",
        "[data-component-id*='review'] article",
        "div[class*='review'], li[class*='review']",
    ]
    for sel in selectors:
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            _log("review area detected via:", sel)
            return True
        except Exception:
            continue
    return False


# ---------------------- 카드 파싱 헬퍼 ----------------------
def _best_text_from_card(card):
    """
    카드 내부에서 '본문' 후보 중 가장 자연어스러운 긴 텍스트를 선택.
    이미지/버튼/배지/메타성 요소는 제외.
    """
    ban_words = [
        "seller", "option", "writer", "author", "nickname",
        "image", "photo", "thumb", "btn", "badge", "star", "rating",
        "score", "reg-date", "date", "meta", "name", "title"
    ]
    nodes = card.find_elements(By.XPATH, ".//p|.//div|.//span")
    best = ""
    for n in nodes:
        try:
            cls = (n.get_attribute("class") or "").lower()
            aria = (n.get_attribute("aria-hidden") or "").lower()
            style = (n.get_attribute("style") or "").lower()
            if aria in ("true", "1"):
                continue
            if "display:none" in style:
                continue
            if any(b in cls for b in ban_words):
                continue
            txt = (n.text or "").strip()
            if 8 <= len(txt) <= 600:
                if len(txt) > len(best):
                    best = txt
        except Exception:
            continue
    if not best:
        # 폴백: 카드 전체 텍스트에서 가장 긴 줄
        lines = [(line.strip(), len(line.strip())) for line in (card.text or "").splitlines()]
        lines = [t for t in lines if 8 <= t[1] <= 600]
        if lines:
            best = max(lines, key=lambda t: t[1])[0]
    return best

def _parse_rating_from_card(card):
    """
    별점 파싱 우선순위:
    1) aria-label의 '점' 숫자
    2) style width% -> 100% = 5.0
    3) 텍스트 '평점/점' 패턴
    4) '★' 개수
    """
    # 1) aria-label
    els = card.find_elements(By.XPATH, ".//*[@aria-label]")
    for el in els:
        label = el.get_attribute("aria-label") or ""
        if "점" in label:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", label)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    pass

    # 2) style width
    stars = card.find_elements(By.XPATH, ".//*[contains(@style,'width')]")
    for s in stars:
        st = s.get_attribute("style") or ""
        m = re.search(r"width:\s*([0-9.]+)%", st)
        if m:
            pct = float(m.group(1))
            return round(pct / 20.0, 1)  # 100% = 5.0

    # 3) 텍스트 패턴
    txt = (card.text or "")
    m = re.search(r"평점\s*([0-9]+(?:\.[0-9]+)?)", txt)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*점", txt)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass

    # 4) 별 문자
    if "★" in txt:
        cnt = txt.count("★")
        if 1 <= cnt <= 5:
            return float(cnt)

    return None

def _parse_date_from_card(card):
    """
    날짜 파싱:
    - time 태그 / class에 date, reg 포함
    - 텍스트 정규식: YYYY.MM.DD / YYYY-MM-DD / '일 전', '개월 전', '년 전'
    """
    for sel in [
        ".//time",
        ".//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'date')]",
        ".//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reg')]",
    ]:
        es = card.find_elements(By.XPATH, sel)
        if es:
            txt = (es[0].text or "").strip()
            if txt:
                return txt

    txt = (card.text or "")
    # YYYY.MM.DD or YYYY-MM-DD
    m = re.search(r"(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})", txt)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 상대 시점
    m = re.search(r"(\d+)\s*(일|개월|년)\s*전", txt)
    if m:
        return f"{m.group(1)}{m.group(2)} 전"
    return ""


# ---------------------- 리뷰 추출 본체 ----------------------
def _extract_reviews_on_page(driver) -> List[Dict]:
    # 1) 컨테이너 수집
    containers = []
    for sel in [
        "[class*='sdp-review__article__list']",
        "section[id*='review']",
        "div[id*='review']",
        "[data-component-id*='review']",
    ]:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        _log("try container:", sel, "=>", len(found))
        containers.extend(found)
    containers = list(dict.fromkeys(containers))

    if not containers:
        _log("no review containers")
        return []

    # 2) 컨테이너 → 카드(아이템) 수집 (폭넓게)
    cards = []
    item_css = [
        ".sdp-review__article__list__review",
        "li[class*='review__item']",
        "article[class*='review']",
        "div[class*='review__item']",
        "li", "article", "div"  # 최후 폴백
    ]
    for c in containers:
        got = []
        for sel in item_css:
            found = c.find_elements(By.CSS_SELECTOR, sel)
            if found:
                got.extend(found)
        if got:
            cards.extend(got)

    # 중복 제거 & 너무 짧은 카드 제거
    uniq = []
    seen = set()
    for el in cards:
        try:
            oid = el.id
            if oid not in seen:
                seen.add(oid)
                if len((el.text or "").strip()) >= 5:
                    uniq.append(el)
        except Exception:
            continue
    cards = uniq
    _log("cards raw:", len(cards))
    if not cards:
        _log("cards found: 0")
        return []

    # 3) 펼치기/더보기
    _expand_more_in_reviews(driver)

    # 4) 필드 파싱
    results = []
    for idx, card in enumerate(cards):
        try:
            rating = _parse_rating_from_card(card)
            body   = _best_text_from_card(card)
            date   = _parse_date_from_card(card)

            # 디버그: 처음 2개 카드 저장
            if idx < 2:
                try:
                    html = card.get_attribute("outerHTML") or ""
                    Path("storage").mkdir(parents=True, exist_ok=True)
                    with open(f"storage/review_card_{idx}.html", "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass

            if (body and len(body) >= 8) or (rating is not None):
                results.append({"rating": rating, "body": body, "review_date": date})
        except Exception:
            continue

    _log("extracted:", len(results))
    return results


# ---------------------- 수집 플로우 ----------------------
def scrape_coupang(product_url: str, max_pages: int = 1) -> int:
    load_dotenv()  # .env 로드
    driver = _new_driver()
    wait = WebDriverWait(driver, 16)
    count = 0

    try:
        # attach 모드가 아니면 쿠키 주입 시도
        if not os.getenv("CHROME_DEBUGGING_ADDR"):
            _apply_cookies_if_any(driver, product_url)

        driver.get(product_url)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        _snap(driver, "loaded")
        _dump_html(driver, "loaded")

        # anti-bot 감지 시 1회 리프레시(크래시 없이 진행)
        html0 = driver.page_source or ""
        if _is_bot_challenge(html0):
            _log("BOT CHALLENGE detected (passive). retry once after sleep.")
            time.sleep(2.0)
            driver.refresh()
            time.sleep(2.0)
            _dump_html(driver, "after_refresh")

        # 리뷰 영역 노출 유도 + 감지
        _deep_scroll(driver, loops=14)
        try:
            wait.until(EC.presence_of_element_located((By.ID, "btfTab")))
            _log("btfTab detected")
        except Exception:
            _log("btfTab not detected (continue)")

        items = _extract_reviews_on_page(driver)

        # DB 저장
        with SessionLocal() as s:
            for it in items:
                h = review_hash("coupang", product_url, it["body"], it["review_date"])
                rv = Review(
                    source="coupang",
                    product_url=product_url,
                    rating=it["rating"],
                    body=it["body"],
                    review_date=it["review_date"],
                    hash_id=h,
                )
                try:
                    s.add(rv); s.commit(); count += 1
                except IntegrityError:
                    s.rollback()

    finally:
        driver.quit()

    _log("inserted:", count)
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", required=True)
    ap.add_argument("--pages", type=int, default=1)  # 현재는 의미 없음(보존)
    args = ap.parse_args()

    total = 0
    for u in args.url:
        clean = u.split("?")[0]  # 트래킹 파라미터 제거
        total += scrape_coupang(clean, max_pages=args.pages)
        time.sleep(random.uniform(1.2, 2.0))

    print(f"[OK] inserted: {total}", flush=True)


if __name__ == "__main__":
    main()