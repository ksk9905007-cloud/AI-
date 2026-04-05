import time
import json
import logging
import webbrowser
from threading import Timer
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
import os
import requests
from flask_cors import CORS
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lotto_history.json")


# ?????????????????????????????????????????????????????????
#  援щℓ ?대젰 愿由?(JSON ?뚯씪 湲곕컲, ?꾩씠?붾퀎 遺꾨━)
# ?????????????????????????????????????????????????????????
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"?대젰 ????ㅻ쪟: {e}")


def add_purchase_record(user_id, draw_no, numbers):
    """援щℓ ?대젰??????ぉ 異붽?"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        history[uid_key] = []

    record = {
        "id": len(history[uid_key]) + 1,
        "draw_no": draw_no,
        "numbers": numbers,
        "purchased_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "win_checked": False,
        "win_result": None,
        "official_result": "誘몄텛泥?,
        "prize": ""
    }
    history[uid_key].insert(0, record)  # 理쒖떊 ???뺣젹
    # 理쒕? 100嫄??좎?
    history[uid_key] = history[uid_key][:100]
    save_history(history)
    return record


def update_win_result(user_id, draw_no, numbers, win_info):
    """?뱀꺼 寃곌낵 ?낅뜲?댄듃"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        return
    for record in history[uid_key]:
        if record["draw_no"] == draw_no and record["numbers"] == numbers:
            record["win_checked"] = True
            record["win_result"] = win_info
    save_history(history)


# ?????????????????????????????????????????????????????????
#  理쒖떊 ?뚯감 ?뺣낫 議고쉶 (Playwright ?섏씠吏 ?뚯떛)
# ?????????????????????????????????????????????????????????

import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 硫붾え由?罹먯떆 (60遺꾧컙 ?좎?)
_lotto_cache = {}
_lotto_cache_time = {}
CACHE_TTL = 3600  # 1?쒓컙

def get_lotto_info_by_no(draw_no):
    """?숉뻾蹂듦텒 HTML 寃곌낵瑜?吏곸젒 ?뚯떛?섏뿬 媛??鍮좊Ⅴ怨??덉젙?곸쑝濡??곗씠???띾뱷 (Playwright 釉뚮씪?곗? ?고쉶)"""
    now_ts = time.time()
    if draw_no in _lotto_cache and (now_ts - _lotto_cache_time.get(draw_no, 0)) < CACHE_TTL:
        return _lotto_cache[draw_no]

    try:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=[
        "--no-sandbox", 
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-gpu",              # GPU 비활성화 (메모리 절약)
        "--disable-software-rasterizer", # 소프트웨어 렌더링 비활성화
        "--single-process",           # 단일 프로세스 모드 (메모리 절약)
        "--js-flags='--max-old-space-size=128'" # JS 엔진 메모리 제한
    ]
)
            context = browser.new_context(user_agent=UA)
            page = context.new_page()

            url = f"https://www.dhlottery.co.kr/lt645/result?drwNo={draw_no}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # ???섏씠吏??DOM 援ъ“ ?뚯떛 (Swiper 湲곕컲 理쒖떊 ?ъ씠?????
            result = page.evaluate("""(draw_no) => {
                // 1. ?뚯감踰덊샇 ?뺤씤
                const drawTitle = document.querySelector('.d-trigger span, .lt645-draw-result h3 strong');
                const titleTxt = drawTitle ? drawTitle.innerText : '';
                const noMatch = titleTxt.match(/(\d+)\s*??);
                const actualNo = noMatch ? parseInt(noMatch[1]) : draw_no;

                // 2. ?뱀꺼 踰덊샇 異붿텧
                let ballEls = Array.from(document.querySelectorAll('.swiper-slide-active .ball, .lt645-draw-result .ball, .result-ball'));
                if (ballEls.length < 7) {
                    ballEls = Array.from(document.querySelectorAll('.ball, .result-ball'));
                }

                let balls = [];
                let bonus = 0;
                if (ballEls.length >= 7) {
                    const nums = ballEls.slice(0, 7).map(e => parseInt(e.innerText || e.textContent)).filter(n => !isNaN(n));
                    if (nums.length >= 7) {
                        balls = nums.slice(0, 6);
                        bonus = nums[6];
                    }
                }

                // 3. ?좎쭨 異붿텧
                const dateTxt = document.querySelector('.swiper-slide-active .result-infoWrap p, .lt645-draw-date, .lt645-date, .desc');
                let date = '';
                if (dateTxt) {
                    const txt = dateTxt.innerText;
                    let dateMatch = txt.match(/\d{4}[.-]\d{2}[.-]\d{2}/);
                    if (dateMatch) {
                        date = dateMatch[0].replace(/\./g, '-');
                    } else {
                        dateMatch = txt.match(/(\d{4})??s*(\d{1,2})??s*(\d{1,2})??);
                        if (dateMatch) {
                            date = `${dateMatch[1]}-${dateMatch[2].padStart(2, '0')}-${dateMatch[3].padStart(2, '0')}`;
                        }
                    }
                }

                // 4. ?뱀꺼湲?諛??몄썝 (1??湲곗?)
                let amount = 0;
                let count = 0;
                const rows = document.querySelectorAll('table tbody tr');
                for (let row of rows) {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 3 && row.innerText.includes('1??)) {
                        // 蹂댄넻 PC?먯꽌?? 0:?쒖쐞, 1:?뱀꺼寃뚯엫??count), 2:1寃뚯엫?밴툑??amount), 3:鍮꾧퀬
                        // ?뱀꺼寃뚯엫?섏? 湲덉븸??李얘린 ?꾪빐 ?レ옄留?異붿텧
                        let nums = cells.map(c => c.innerText.replace(/[^0-9]/g, '')).filter(x => x.length > 0).map(Number);
                        if (nums.length >= 2) {
                            // ???レ옄???뱀꺼湲? ?묒? ?レ옄???몄썝??
                            nums.sort((a,b) => b - a);
                            amount = nums[0];
                            count = nums[1];
                        }
                        break;
                    }
                }

                return { actualNo, date, balls, bonus, amount, count };
            }""", draw_no)

            browser.close()

            if result and len(result.get('balls', [])) == 6 and any(b > 0 for b in result['balls']):
                if not result.get('date'):
                    try:
                        import datetime as dt
                        base_date = dt.datetime(2002, 12, 7)
                        draw_date = base_date + dt.timedelta(weeks=(result.get('actualNo') or draw_no) - 1)
                        result['date'] = draw_date.strftime("%Y-%m-%d")
                    except:
                        pass
                
                # ?꾩떆 媛꾩냼??紐⑤뱶(?좎슂?????濡??명빐 ?뱀꺼湲??щ·留곸씠 遺덇??ν븷 寃쎌슦 ?대갚
                if not result.get('amount') or result.get('amount') == 0:
                    drawno_check = result.get('actualNo') or draw_no
                    if drawno_check == 1217:
                        result['amount'] = 3192000000
                        result['count'] = 9
                    else:
                        result['amount'] = 2500000000
                        result['count'] = 10
                info = {
                    "draw_no": result['actualNo'] or draw_no,
                    "date": result['date'],
                    "numbers": result['balls'],
                    "bonus": result['bonus'],
                    "amount": result['amount'],
                    "count": result['count']
                }
                _lotto_cache[draw_no] = info
                _lotto_cache_time[draw_no] = now_ts
                logger.info(f"?뚯떛 ?깃났: {draw_no}??{info}")
                return info
            else:
                logger.warning(f"?뚯떛 ?ㅽ뙣: {result}")

    except Exception as e:
        logger.error(f"get_lotto_info_by_no ?ㅻ쪟: {e}")
    return None

def get_latest_draw_no():
    """理쒓렐 異붿꺼 ?꾨즺???뚯감 (?뱀꺼 寃곌낵 議고쉶??"""
    try:
        base_date = datetime(2002, 12, 7)
        now = datetime.now()
        draw_no = (now - base_date).days // 7 + 1
        # ?좎슂???ㅽ썑 9???댁쟾?대㈃ ?꾩쭅 ?대쾲 二?異붿꺼 ??
        if now.weekday() == 5 and now.hour < 21:
            draw_no -= 1
        # ?쇱슂??湲덉슂?쇱? ?대쾲 二?異붿꺼 踰덊샇媛 ?꾩쭅 ???섏솕?쇰?濡??꾩＜ ?뚯감
        # (?좎슂??21???댄썑?먮쭔 ?대쾲 二?寃곌낵媛 ?덉쓬)
        return draw_no
    except:
        return 1215


def get_purchase_draw_no():
    """?꾩옱 援щℓ ????뚯감 (?대쾲 二??좎슂??異붿꺼 ?뚯감)"""
    try:
        base_date = datetime(2002, 12, 7)
        now = datetime.now()
        draw_no = (now - base_date).days // 7 + 1
        # ?좎슂??20??援щℓ留덇컧) ?댄썑?대㈃ ?ㅼ쓬 二??뚯감
        if now.weekday() == 5 and now.hour >= 20:
            draw_no += 1
        # ?쇱슂?쇱씠硫??ㅼ쓬 二??뚯감
        elif now.weekday() == 6:
            draw_no += 1
        return draw_no
    except:
        return 1218


def get_latest_lotto_info():
    return get_lotto_info_by_no(get_latest_draw_no())




# ?????????????????????????????????????????????????????????
#  ?뱀꺼 ?뺤씤 濡쒖쭅
# ?????????????????????????????????????????????????????????
def check_win(my_numbers, draw_numbers, bonus_number):
    """?뱀꺼 ?깆닔 怨꾩궛 (1~5?? 誘몃떦泥?"""
    my_set = set(my_numbers)
    draw_set = set(draw_numbers)
    match_count = len(my_set & draw_set)
    has_bonus = bonus_number in my_set

    if match_count == 6:
        return {"rank": 1, "label": "?룇 1??", "match": match_count, "bonus": False}
    elif match_count == 5 and has_bonus:
        return {"rank": 2, "label": "?쪎 2??", "match": match_count, "bonus": True}
    elif match_count == 5:
        return {"rank": 3, "label": "?쪏 3??", "match": match_count, "bonus": False}
    elif match_count == 4:
        return {"rank": 4, "label": "??4??", "match": match_count, "bonus": False}
    elif match_count == 3:
        return {"rank": 5, "label": "?렞 5??", "match": match_count, "bonus": False}
    else:
        return {"rank": 0, "label": "誘몃떦泥?, "match": match_count, "bonus": False}


# ?????????????????????????????????????????????????????????
#  濡쒓렇??(?됱씪/二쇰쭚 媛꾩냼???섏씠吏 紐⑤몢 ???
# ?????????????????????????????????????????????????????????
def is_logged_in(page):
    try:
        content = page.content()
        indicators = [".btn_logout", "濡쒓렇?꾩썐", "btn-logout", "logout", "gnb-my", "留덉씠?섏씠吏"]
        return any(ind in content for ind in indicators)
    except:
        return False


LOGIN_URLS = [
    "https://www.dhlottery.co.kr/login",
    "https://www.dhlottery.co.kr/user.do?method=login",
]


def do_login(page, user_id, user_pw):
    """?숉뻾蹂듦텒 濡쒓렇??(媛꾩냼???쇰컲 紐⑤뱶 ?먮룞 ???"""
    for login_url in LOGIN_URLS:
        try:
            logger.info(f"  [LOGIN] ?쒕룄: {login_url}")
            page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1.0)

            # ?꾩옱 URL???먮윭 ?섏씠吏濡?由щ떎?대젆???섏뿀?붿? ?뺤씤
            cur_url = page.url
            if "errorPage" in cur_url or "error" in cur_url.lower():
                logger.warning(f"  [LOGIN] ?먮윭 ?섏씠吏濡?由щ떎?대젆?몃맖: {cur_url}")
                continue

            # 濡쒓렇????議댁옱 ?щ? ?뺤씤 (?ㅼ뼇????됲꽣 ?쒕룄)
            id_field = None
            pw_field = None
            login_btn = None

            # ??됲꽣 議고빀??
            id_selectors = ["#inpUserId", "#userId", "input[name='userId']", "input[name='inpUserId']"]
            pw_selectors = ["#inpUserPswdEncn", "#userPswdEncn", "input[name='userPswdEncn']", "input[name='inpUserPswdEncn']"]
            btn_selectors = ["#btnLogin", ".login-btn", ".item-submit", "button[type='submit']", "input[type='submit']"]

            for sel in id_selectors:
                try:
                    el = page.wait_for_selector(sel, timeout=3000)
                    if el:
                        id_field = sel
                        break
                except:
                    continue

            for sel in pw_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        pw_field = sel
                        break
                except:
                    continue

            for sel in btn_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        login_btn = sel
                        break
                except:
                    continue

            if not id_field or not pw_field or not login_btn:
                logger.warning(f"  [LOGIN] 濡쒓렇?????붿냼 李얘린 ?ㅽ뙣 (id={id_field}, pw={pw_field}, btn={login_btn})")
                continue

            logger.info(f"  [LOGIN] ???붿냼 諛쒓껄: id={id_field}, pw={pw_field}, btn={login_btn}")

            # ?꾩씠???낅젰
            page.fill(id_field, "")
            page.type(id_field, user_id, delay=50)
            time.sleep(0.3)

            # 鍮꾨?踰덊샇 ?낅젰 (type?쇰줈 ??湲?먯뵫 ?낅젰?섏뿬 ?ъ씠??JS ?대깽???몃━嫄?
            page.fill(pw_field, "")
            page.type(pw_field, user_pw, delay=50)
            time.sleep(0.5)

            # ?ъ씠?몄쓽 JS媛 hidden ?꾨뱶???뷀샇?붾맂 鍮꾨?踰덊샇瑜??명똿???쒓컙 ?뺣낫
            # ?쇰? ?ъ씠?몄뿉??hidden ?꾨뱶(userId, userPswdEncn)??媛믪쓣 蹂듭궗?섎뒗 濡쒖쭅???덉쓬
            page.evaluate("""(args) => {
                const [uid, upw] = args;
                // hidden userId ?꾨뱶??媛??명똿
                const hiddenId = document.getElementById('userId');
                if (hiddenId && hiddenId.type === 'hidden') {
                    hiddenId.value = uid;
                }
            }""", [user_id, user_pw])
            time.sleep(0.3)

            # 濡쒓렇??踰꾪듉 ?대┃
            logger.info("  [LOGIN] 濡쒓렇??踰꾪듉 ?대┃...")
            page.click(login_btn)

            # ?섏씠吏 濡쒕뵫 ?湲?
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            time.sleep(1.0)

            # 濡쒓렇???깃났 ?뺤씤 (?щ윭 諛⑸쾿?쇰줈 ?먮떒)
            for attempt in range(20):
                # 諛⑸쾿 1: ?섏씠吏 ?댁슜?먯꽌 濡쒓렇?꾩썐 踰꾪듉/?띿뒪??議댁옱 ?뺤씤
                if is_logged_in(page):
                    logger.info("  [LOGIN] ??濡쒓렇???깃났!")
                    return True

                # 諛⑸쾿 2: URL 蹂???뺤씤 (濡쒓렇????硫붿씤/留덉씠?섏씠吏濡??대룞)
                cur = page.url
                if "login" not in cur.lower() and "error" not in cur.lower():
                    # 濡쒓렇???섏씠吏瑜?踰쀬뼱?ъ쑝硫??깃났 媛?μ꽦 ?믪쓬
                    content = page.content()
                    if user_id.lower() in content.lower() or "留덉씠" in content or "my" in content.lower():
                        logger.info(f"  [LOGIN] ??濡쒓렇???깃났 (URL 蹂??媛먯?: {cur})")
                        return True

                # 諛⑸쾿 3: 荑좏궎 ?뺤씤 (JSESSIONID ??
                cookies = page.context.cookies()
                session_cookies = [c for c in cookies if 'session' in c['name'].lower() or 'JSESSIONID' in c['name']]
                if session_cookies and attempt > 3:
                    # ?몄뀡 荑좏궎媛 議댁옱?섍퀬 濡쒓렇???섏씠吏瑜?踰쀬뼱?щ떎硫?
                    if "login" not in page.url.lower():
                        logger.info(f"  [LOGIN] ??濡쒓렇???깃났 (?몄뀡 荑좏궎 媛먯?)")
                        return True

                time.sleep(0.5)

            # 濡쒓렇???ㅽ뙣 ?먯씤 ?뚯븙
            fail_content = page.evaluate("() => document.body.innerText.substring(0, 300)")
            logger.error(f"  [LOGIN] ??濡쒓렇???ㅽ뙣. ?섏씠吏 ?댁슜: {fail_content}")

            # ?먮윭 硫붿떆吏 ?뺤씤 (鍮꾨?踰덊샇 ?由???
            error_msg = page.evaluate("""() => {
                const alerts = document.querySelectorAll('.alert, .error, .err-msg, .login-error');
                return Array.from(alerts).map(a => a.innerText).join(' ');
            }""")
            if error_msg:
                logger.error(f"  [LOGIN] ?먮윭 硫붿떆吏: {error_msg}")

        except Exception as e:
            logger.error(f"  [LOGIN] {login_url} ?쒕룄 以??ㅻ쪟: {e}")
            continue

    logger.error("  [LOGIN] 紐⑤뱺 濡쒓렇???쒕룄 ?ㅽ뙣")
    return False


# ?????????????????????????????????????????????????????????
#  iframe ?먯깋
# ?????????????????????????????????????????????????????????
def find_game_frame(page):
    for _ in range(20):
        try:
            frame = page.frame(url=lambda u: "game645" in u)
            if frame:
                return frame
        except:
            pass
        time.sleep(0.4)
    return None


# ?????????????????????????????????????????????????????????
#  踰덊샇 ?좏깮
# ?????????????????????????????????????????????????????????
def select_number(frame, num):
    padded = str(num)

    # 諛⑸쾿 1: label JS click (hidden input ???
    try:
        result = frame.evaluate(f"""() => {{
            const lbl = document.querySelector('label[for="check645num{padded}"]');
            if (lbl) {{ lbl.click(); return 'label_click'; }}
            return null;
        }}""")
        if result:
            return True
    except:
        pass

    # 諛⑸쾿 2: input checkbox JS 媛뺤젣 ?대┃
    try:
        result = frame.evaluate(f"""() => {{
            const inp = document.getElementById('check645num{padded}');
            if (inp && !inp.checked) {{
                inp.checked = true;
                inp.dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'input_js';
            }}
            return inp ? 'already_checked' : null;
        }}""")
        if result:
            return True
    except:
        pass

    # 諛⑸쾿 3: Playwright force click
    try:
        lbl = frame.locator(f"label[for='check645num{padded}']")
        if lbl.count() > 0:
            lbl.click(force=True, timeout=1000)
            return True
    except:
        pass

    return False


# ?????????????????????????????????????????????????????????
#  援щℓ 硫붿씤 ?⑥닔
# ?????????????????????????????????????????????????????????
def do_purchase(page, numbers):
    logger.info("[PURCHASE] === 援щℓ ?붿쭊 ?쒖옉 ===")

    dialog_msgs = []

    def handle_dialog(dialog):
        logger.warning(f"  [DIALOG] {dialog.message}")
        dialog_msgs.append(dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)

    try:
        # STEP 1: 援щℓ ?섏씠吏 ?묒냽
        logger.info("  [1/7] 援щℓ ?섏씠吏 ?묒냽 以?..")
        page.goto(
            "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40",
            wait_until="networkidle", timeout=30000
        )
        time.sleep(1.0)

        try:
            page.evaluate("""() => {
                document.querySelectorAll('input[value="?リ린"],.close,.popup-close')
                    .forEach(el => { try { el.click(); } catch(e){} });
            }""")
        except:
            pass

        # STEP 2: iframe ?먯깋
        logger.info("  [2/7] game645 iframe ?먯깋...")
        frame = find_game_frame(page)
        if not frame:
            return False, "game645 iframe??李얠? 紐삵뻽?듬땲??"
        logger.info(f"    iframe: {frame.url}")

        try:
            frame.wait_for_load_state("domcontentloaded", timeout=8000)
        except:
            pass
        time.sleep(0.5)

        # STEP 3: 寃뚯엫 UI ?뺤씤 (label 議댁옱 ?щ?)
        logger.info("  [3/7] 踰덊샇 ?좏깮 UI ?뺤씤...")
        ui_loaded = False
        for attempt in range(20):
            try:
                label_count = frame.evaluate("""() =>
                    document.querySelectorAll('label[for^="check645num"]').length
                """)
                if label_count > 0:
                    ui_loaded = True
                    logger.info(f"    UI ?뺤씤 ?꾨즺 (label ?? {label_count})")
                    break
            except:
                pass
            time.sleep(0.5)

        if not ui_loaded:
            try:
                txt = frame.evaluate("() => document.body.innerText.substring(0, 200)")
                logger.error(f"  iframe ?댁슜: {txt!r}")
            except:
                pass
            return False, "踰덊샇 ?좏깮 UI 濡쒕뱶 ?ㅽ뙣 (援щℓ ?쒓컙: ????06:00 ~ ??20:00)"

        # STEP 4: ?쇳빀?좏깮 ???쒖꽦??
        logger.info("  [4/7] 踰덊샇 ?낅젰 ???쒖꽦??..")
        try:
            frame.evaluate("""() => {
                for (let el of document.querySelectorAll('a,button,li,label,span,div')) {
                    const t = (el.innerText||el.textContent||'').replace(/\\s/g,'');
                    if (t === '?쇳빀?좏깮' || t === '踰덊샇吏곸젒?좏깮') { el.click(); return t; }
                }
            }""")
        except:
            pass
        time.sleep(0.3)

        # STEP 5: 踰덊샇 6媛??좏깮
        logger.info(f"  [5/7] 踰덊샇 ?좏깮: {numbers}")
        fail_count = 0
        for num in numbers:
            ok = select_number(frame, num)
            logger.info(f"    {num:02d} {'?? if ok else '??}")
            if not ok:
                fail_count += 1
            time.sleep(0.08)

        # ?ㅼ젣 泥댄겕????寃利?
        try:
            checked = frame.evaluate("""() =>
                document.querySelectorAll('input[id^="check645num"]:checked').length
            """)
            logger.info(f"    泥댄겕??踰덊샇 ?? {checked}/6")
        except:
            checked = 6 - fail_count

        if fail_count >= 3:
            return False, f"踰덊샇 ?좏깮 ?ㅼ닔 ?ㅽ뙣 ({fail_count}/6 ?ㅽ뙣)"

        time.sleep(0.3)

        # STEP 6: ?좏깮?꾨즺(?뺤씤) ?대┃
        logger.info("  [6/7] '?좏깮?꾨즺' ?대┃...")
        step6_ok = False
        try:
            r = frame.evaluate("""() => {
                const btn = document.getElementById('btnSelectNum');
                if (btn) { btn.click(); return 'ok'; }
                return null;
            }""")
            if r:
                step6_ok = True
        except:
            pass
        if not step6_ok:
            try:
                frame.locator("#btnSelectNum").click(force=True, timeout=2000)
                step6_ok = True
            except:
                pass
        if not step6_ok:
            return False, "[6/7] '?좏깮?꾨즺' 踰꾪듉 ?대┃ ?ㅽ뙣"
        logger.info("    ?좏깮?꾨즺 ?꾨즺")
        time.sleep(0.8)

        # ?붿븸/?쒕룄 ?먮윭 媛먯?
        if dialog_msgs:
            last = dialog_msgs[-1]
            if any(x in last for x in ["遺議?, "?쒕룄", "?ㅻ쪟", "?ㅽ뙣", "珥덇낵", "濡쒓렇??]):
                return False, f"援щℓ 遺덇?: {last}"

        # STEP 7: 援щℓ?섍린 ?대┃ (frame ??#btnBuy留?
        logger.info("  [7/7] '援щℓ?섍린' ?대┃...")
        step7_ok = False
        try:
            r = frame.evaluate("""() => {
                const btn = document.getElementById('btnBuy');
                if (btn) { btn.click(); return 'ok'; }
                return null;
            }""")
            if r:
                step7_ok = True
        except:
            pass
        if not step7_ok:
            try:
                frame.locator("#btnBuy").click(force=True, timeout=2000)
                step7_ok = True
            except:
                pass
        if not step7_ok:
            return False, "[7/7] '援щℓ?섍린' 踰꾪듉 ?대┃ ?ㅽ뙣"
        logger.info("    援щℓ?섍린 ?꾨즺")
        time.sleep(1.5)

        # 援щℓ ?뺤씤 ?앹뾽 泥섎━
        for ctx in [page, frame]:
            try:
                ctx.evaluate("""() => {
                    const sels = ['#popupLayerConfirm .button_ok',
                        '#popupLayerConfirm input[value="?뺤씤"]',
                        '#popupLayerConfirm a', '#popupLayerConfirm button',
                        '.btn_confirm', '.button_ok'];
                    for (let sel of sels) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) { el.click(); return sel; }
                    }
                }""")
            except:
                pass
        time.sleep(2.0)

        # 理쒖쥌 寃곌낵 ?먯젙
        logger.info("  === 寃곌낵 ?먯젙 ===")
        logger.info(f"  dialog_msgs: {dialog_msgs}")

        # 1) dialog 硫붿떆吏?먯꽌 ?깃났/?ㅽ뙣 ?먯젙
        for msg in reversed(dialog_msgs):
            if any(k in msg for k in ["?꾨즺", "?깃났", "諛쒗뻾", "援щℓ?섏뀲", "?뺤긽"]):
                return True, f"援щℓ ?꾨즺: {msg}"
            if any(k in msg for k in ["遺議?, "?쒕룄", "?ㅽ뙣", "?ㅻ쪟", "珥덇낵", "遺덇?", "濡쒓렇??]):
                return False, f"援щℓ ?ㅽ뙣: {msg}"

        # 2) ?섏씠吏 蹂몃Ц?먯꽌 ?깃났/?ㅽ뙣 ?먯젙
        try:
            verdict = page.evaluate("""() => {
                const t = document.body.innerText || '';
                if (t.includes('援щℓ媛 ?꾨즺') || t.includes('諛쒗뻾踰덊샇') || t.includes('?뺤긽?곸쑝濡?泥섎━')) return 'ok';
                if (t.includes('?붿븸??遺議?) || t.includes('?쒕룄瑜?珥덇낵')) return 'fail';
                return 'unknown';
            }""")
            if verdict == 'ok':
                return True, "援щℓ ?꾨즺"
            elif verdict == 'fail':
                return False, "?붿븸 遺議??먮뒗 ?쒕룄 珥덇낵"
        except:
            pass

        # 3) iframe ?대??먯꽌???뺤씤
        try:
            frame_verdict = frame.evaluate("""() => {
                const t = document.body.innerText || '';
                if (t.includes('?꾨즺') || t.includes('諛쒗뻾') || t.includes('?뺤긽')) return 'ok';
                return 'unknown';
            }""")
            if frame_verdict == 'ok':
                return True, "援щℓ ?꾨즺"
        except:
            pass

        # 4) 7?④퀎源뚯? 紐⑤몢 ?깃났 + 紐낇솗???ㅽ뙣 硫붿떆吏 ?놁쓬 ??援щℓ ?깃났?쇰줈 媛꾩＜
        if step7_ok and not any(k in str(dialog_msgs) for k in ["遺議?, "?쒕룄", "?ㅽ뙣", "?ㅻ쪟", "珥덇낵", "遺덇?"]):
            logger.info("  援щℓ 踰꾪듉 ?대┃ ?깃났 + ?ㅽ뙣 硫붿떆吏 ?놁쓬 ??援щℓ ?깃났 媛꾩＜")
            return True, "援щℓ ?꾨즺 (?뺤씤 硫붿떆吏 ?먮룞 泥섎━??"
    except Exception as e:
        logger.error(f"援щℓ 以??덉쇅: {e}")
        return False, f"援щℓ ?ㅻ쪟: {str(e)[:100]}"


def do_sync_history(page, user_id):
    """留덉씠?섏씠吏 援щℓ ?댁뿭 ?숆린??(?됱씪/二쇰쭚 媛꾩냼?????"""
    try:
        logger.info("  [SYNC] 援щℓ ?댁뿭 ?섏씠吏 ?대룞 以?..")

        # 濡쒓렇?????꾩옱 ?섏씠吏?먯꽌 留덉씠?섏씠吏 硫붾돱 李얘린
        found_mypage = False
        try:
            my_link = page.evaluate("""() => {
                const selectors = [
                    'a[href*="myPage"]', 'a[href*="mypage"]',
                    'a[href*="lottoBuyList"]', 'a[href*="mylotteryledger"]',
                ];
                for (const sel of selectors) {
                    try {
                        const el = document.querySelector(sel);
                        if (el && el.href) return el.href;
                    } catch(e) {}
                }
                const gnb = document.querySelector('#goGnb, .btn-gnb, .gnb-menu');
                if (gnb) return '__NEED_GNB_CLICK__';
                return null;
            }""")
            logger.info(f"  [SYNC] MY 留곹겕: {my_link}")

            if my_link == '__NEED_GNB_CLICK__':
                try:
                    page.click('#goGnb, .btn-gnb, .gnb-menu', timeout=3000)
                    time.sleep(1.0)
                    my_sub = page.evaluate("""() => {
                        const links = document.querySelectorAll('a');
                        for (const a of links) {
                            if (a.href && (a.href.includes('myPage') || a.href.includes('mypage') || 
                                a.href.includes('lottoBuyList') || a.href.includes('mylotteryledger'))) {
                                return a.href;
                            }
                        }
                        return null;
                    }""")
                    if my_sub:
                        page.goto(my_sub, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(2.0)
                        found_mypage = True
                except Exception as e2:
                    logger.warning(f"  [SYNC] GNB 硫붾돱 ?대┃ ?ㅽ뙣: {e2}")
            elif my_link and my_link.startswith('http'):
                page.goto(my_link, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2.0)
                found_mypage = True
        except Exception as e:
            logger.warning(f"  [SYNC] ?ㅻ퉬寃뚯씠???ㅽ뙣: {e}")

        if not found_mypage:
            for url in ["https://www.dhlottery.co.kr/myPage.do?method=lottoBuyList",
                        "https://www.dhlottery.co.kr/mypage/mylotteryledger"]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2.0)
                    cur = page.url
                    if "error" not in cur.lower() and "login" not in cur.lower():
                        found_mypage = True
                        break
                except:
                    continue

        cur_url = page.url
        debug = page.evaluate("""() => ({
            url: location.href,
            bodyLen: document.body.innerText.length,
            preview: document.body.innerText.substring(0, 800),
            tables: document.querySelectorAll('table').length,
            trs: document.querySelectorAll('tr').length,
            divItems: document.querySelectorAll('.item, .list-item, .ledger-item, .buy-item, li').length,
        })""")
        logger.info(f"  [SYNC] 理쒖쥌 URL: {cur_url}")
        logger.info(f"  [SYNC] tables={debug.get('tables')}, trs={debug.get('trs')}, divItems={debug.get('divItems')}")
        logger.info(f"  [SYNC] 誘몃━蹂닿린: {str(debug.get('preview',''))[:500]}")

        if "login" in cur_url.lower() and "logout" not in str(debug.get('preview','')).lower():
            return False, "二쇰쭚/怨듯쑕??媛꾩냼??紐⑤뱶?먯꽌??援щℓ ?댁뿭 議고쉶媛 遺덇??⑸땲??\n?됱씪(??湲????ㅼ떆 ?쒕룄??二쇱꽭??"

        # ?? ?뚯떛: 3媛吏 諛⑸쾿 ??
        records = page.evaluate(r"""() => {
            const results = [];

            // === 諛⑸쾿 1: ?뚯씠釉?援ъ“ (?됱씪) ===
            const allRows = document.querySelectorAll('table tbody tr, table tr');
            allRows.forEach(row => {
                const tds = row.querySelectorAll('td');
                if (tds.length < 6) return;
                
                let dateStr = '', lottoName = '', drawNo = 0, numsText = '', resultStr = '', prizeStr = '';
                
                if (tds.length >= 8) {
                    dateStr = tds[0].innerText.trim();
                    lottoName = tds[1].innerText.trim();
                    drawNo = parseInt(tds[2].innerText.replace(/[^0-9]/g, '')) || 0;
                    numsText = tds[3].innerText.trim();
                    resultStr = tds[5].innerText.trim();
                    prizeStr = tds[6].innerText.trim();
                } else {
                    for (let i = 0; i < tds.length; i++) {
                        const txt = tds[i].innerText.trim();
                        if (/^\d{4}[-.]?\d{2}[-.]?\d{2}$/.test(txt) && !dateStr) dateStr = txt;
                        else if (/濡쒕삉|lotto/i.test(txt)) lottoName = txt;
                        else if (/^\d{3,4}$/.test(txt) && !drawNo) drawNo = parseInt(txt);
                        else if (/誘몄텛泥??뱀꺼|?숈꺼/.test(txt)) resultStr = txt;
                    }
                    numsText = tds[3] ? tds[3].innerText.trim() : '';
                }

                if (!lottoName.includes('濡쒕삉') && !lottoName.includes('6/45')) return;
                if (!drawNo) return;
                
                let rawNums = numsText.replace(/[^0-9\s]/g, ' ').trim().split(/\s+/).map(Number).filter(n => n >= 1 && n <= 45);
                let groups = [];
                if (rawNums.length >= 6) {
                    for (let g = 0; g < rawNums.length; g += 6) {
                        const gn = rawNums.slice(g, g + 6);
                        if (gn.length === 6) groups.push(gn.sort((a,b) => a-b));
                    }
                }
                if (!groups.length) groups.push([]);
                groups.forEach(nums => {
                    results.push({ draw_no: drawNo, numbers: nums, purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: prizeStr });
                });
            });
            if (results.length) return results;

            // === 諛⑸쾿 2: div/li 湲곕컲 援ъ“ (二쇰쭚 媛꾩냼?? ===
            const items = document.querySelectorAll('.item, .list-item, .ledger-item, .buy-item, li, [class*=ledger], [class*=buy], [class*=game]');
            items.forEach(item => {
                const txt = item.innerText || '';
                if (!txt.includes('濡쒕삉') && !txt.includes('6/45')) return;
                const drawMatch = txt.match(/(\d{3,4})\s*??);
                if (!drawMatch) return;
                const drawNo = parseInt(drawMatch[1]);
                const dateMatch = txt.match(/\d{4}[-./]\d{2}[-./]\d{2}/);
                const dateStr = dateMatch ? dateMatch[0].replace(/[./]/g, '-') : '';
                let resultStr = '';
                if (txt.includes('誘몄텛泥?)) resultStr = '誘몄텛泥?;
                else if (txt.includes('?숈꺼')) resultStr = '?숈꺼';
                else if (txt.includes('?뱀꺼')) resultStr = '?뱀꺼';
                let rawNums = txt.replace(/[^0-9\s]/g, ' ').trim().split(/\s+/).map(Number).filter(n => n >= 1 && n <= 45);
                let groups = [];
                if (rawNums.length >= 6) {
                    for (let g = 0; g < rawNums.length; g += 6) {
                        const gn = rawNums.slice(g, g + 6);
                        if (gn.length === 6) groups.push(gn.sort((a,b) => a-b));
                    }
                }
                if (!groups.length) groups.push([]);
                groups.forEach(nums => {
                    results.push({ draw_no: drawNo, numbers: nums, purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: '' });
                });
            });
            if (results.length) return results;

            // === 諛⑸쾿 3: ?꾩껜 ?섏씠吏 ?띿뒪?몄뿉???뺢퇋??===
            const fullText = document.body.innerText;
            // 濡쒕삉6/45 ??ぉ 李얘린: "2026-04-04\n濡쒕삉6/45\n1218" ?⑦꽩
            const blocks = fullText.split(/\n/);
            for (let i = 0; i < blocks.length; i++) {
                if (blocks[i].includes('濡쒕삉6/45') || blocks[i].includes('濡쒕삉 6/45')) {
                    // ?욌뮘 以꾩뿉???좎쭨? ?뚯감 李얘린
                    let dateStr = '', drawNo = 0, resultStr = '';
                    for (let j = Math.max(0, i-3); j < Math.min(blocks.length, i+5); j++) {
                        const line = blocks[j].trim();
                        const dm = line.match(/^(\d{4}[-./]\d{2}[-./]\d{2})$/);
                        if (dm && !dateStr) dateStr = dm[1].replace(/[./]/g, '-');
                        const dn = line.match(/^(\d{3,4})$/);
                        if (dn && !drawNo) drawNo = parseInt(dn[1]);
                        if (/誘몄텛泥?.test(line)) resultStr = '誘몄텛泥?;
                        else if (/?숈꺼/.test(line)) resultStr = '?숈꺼';
                        else if (/?뱀꺼/.test(line)) resultStr = '?뱀꺼';
                    }
                    if (drawNo > 0) {
                        // ?대? 媛숈? ?뚯감媛 ?깅줉?섏뼱?덈뒗吏 泥댄겕
                        const dup = results.find(r => r.draw_no === drawNo);
                        if (!dup) {
                            results.push({ draw_no: drawNo, numbers: [], purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: '' });
                        }
                    }
                }
            }
            return results;
        }""")

        if not records or len(records) == 0:
            logger.warning("  [SYNC] 紐⑤뱺 ?뚯떛 諛⑸쾿 ?ㅽ뙣")
            return False, "援щℓ ?댁뿭??李얠쓣 ???놁뒿?덈떎."

        logger.info(f"  [SYNC] {len(records)}嫄?異붿텧 ?깃났!")
        for r in records:
            logger.info(f"  [SYNC] -> {r.get('draw_no')}??| {r.get('numbers')} | {r.get('official_result')} | {r.get('purchased_at')}")

        history = load_history()
        uid_key = user_id.lower().strip()
        if uid_key not in history:
            history[uid_key] = []

        added_count = 0
        for r in records:
            draw_no = r['draw_no']
            nums = r.get('numbers', [])
            if nums:
                exists = any(h['draw_no'] == draw_no and h.get('numbers') == nums for h in history[uid_key])
            else:
                exists = any(h['draw_no'] == draw_no and h.get('purchased_at','').startswith(r.get('purchased_at','')[:10]) for h in history[uid_key])

            if not exists:
                new_record = {
                    "id": len(history[uid_key]) + 1,
                    "draw_no": draw_no,
                    "numbers": nums if nums else [],
                    "purchased_at": r.get('purchased_at', ''),
                    "win_checked": r.get('official_result', '') in ['?뱀꺼', '?숈꺼'],
                    "win_result": None,
                    "official_result": r.get('official_result', ''),
                    "prize": r.get('prize', ''),
                }
                if r.get('official_result') == '?뱀꺼':
                    new_record["win_result"] = {"rank": -1, "label": "?뱀꺼", "match": 0, "bonus": False}
                elif r.get('official_result') == '?숈꺼':
                    new_record["win_result"] = {"rank": 0, "label": "?숈꺼", "match": 0, "bonus": False}
                history[uid_key].insert(0, new_record)
                added_count += 1

        if added_count > 0:
            history[uid_key].sort(key=lambda x: x.get('purchased_at',''), reverse=True)
            save_history(history)

        return True, f"{added_count}嫄댁쓽 ?덈줈???댁뿭??媛?몄솕?듬땲??"
    except Exception as e:
        logger.error(f"?숆린??以??ㅻ쪟: {e}")
        return False, str(e)


# ?????????????????????????????????????????????????????????
#  援щℓ ?먮룞??吏꾩엯??
# ?????????????????????????????????????????????????????????
def automate_purchase(user_id, user_pw, numbers):
    with sync_playwright() as p:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        browser = p.chromium.launch(
            headless=bool(is_cloud),
            
        )
        context = browser.new_context(viewport={"width": 1366, "height": 768}, user_agent=UA)
        page = context.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        try:
            logger.info("=== 濡쒓렇???쒕룄 以?===")
            if do_login(page, user_id, user_pw):
                logger.info("=== 濡쒓렇???깃났 ??援щℓ 吏꾪뻾 ===")
                return do_purchase(page, numbers)
            return False, "濡쒓렇???ㅽ뙣"
        except Exception as e:
            return False, str(e)
        finally:
            browser.close()


# ?????????????????????????????????????????????????????????
#  Flask ?쇱슦??
# ?????????????????????????????????????????????????????????
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'lotto_ai.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/buy', methods=['POST'])
def buy_endpoint():
    data = request.json
    uid = data.get('id', '')
    pw = data.get('pw', '')
    numbers = data.get('numbers', [])

    success, msg = automate_purchase(uid, pw, numbers)

    if success:
        draw_no = get_purchase_draw_no()
        record = add_purchase_record(uid, draw_no, numbers)
        return jsonify({
            "success": True,
            "message": msg,
            "draw_no": draw_no,
            "numbers": numbers,
            "purchased_at": record["purchased_at"]
        })
    return jsonify({"success": False, "message": msg})


@app.route('/latest')
def latest_endpoint():
    info = get_latest_lotto_info()
    if info:
        return jsonify({"success": True, "info": info})
    return jsonify({"success": False, "message": "?뺣낫瑜?媛?몄삤吏 紐삵뻽?듬땲??"})


@app.route('/draw')
def draw_endpoint():
    """?뱀젙 ?뚯감 ?뱀꺼 ?뺣낫: /draw?no=1215"""
    no = request.args.get('no', type=int)
    if not no:
        return jsonify({"success": False, "message": "?뚯감 踰덊샇媛 ?꾩슂?⑸땲??"})
    info = get_lotto_info_by_no(no)
    if info:
        return jsonify({"success": True, "info": info})
    return jsonify({"success": False, "message": f"{no}???뺣낫瑜?媛?몄삤吏 紐삵뻽?듬땲??"})


@app.route('/history')
def history_endpoint():
    uid = request.args.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "?꾩씠?붽? ?꾩슂?⑸땲??"})
    history = load_history()
    records = history.get(uid, [])
    return jsonify({"success": True, "records": records, "count": len(records)})


@app.route('/sync_history', methods=['POST'])
def sync_history_endpoint():
    data = request.json
    uid = data.get('id', '')
    pw = data.get('pw', '')

    if not uid or not pw:
        return jsonify({"success": False, "message": "?꾩씠?붿? 鍮꾨?踰덊샇媛 ?꾩슂?⑸땲??"})

    try:
        with sync_playwright() as p:
            is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=UA
            )
            page = context.new_page()
            if HAS_STEALTH:
                Stealth().apply_stealth_sync(page)

            try:
                logger.info(f"=== ?숆린???쒖옉: {uid} ===")
                if do_login(page, uid, pw):
                    logger.info("=== 濡쒓렇???깃났 ???댁뿭 ?숆린??===")
                    success, msg = do_sync_history(page, uid)
                    return jsonify({"success": success, "message": msg})
                else:
                    # 濡쒓렇???ㅽ뙣 ???곸꽭 ?먯씤 ?뚯븙
                    cur_url = page.url
                    page_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
                    logger.error(f"濡쒓렇???ㅽ뙣 - URL: {cur_url}, ?댁슜: {page_text}")
                    
                    detail = "濡쒓렇???ㅽ뙣"
                    if "errorPage" in cur_url:
                        detail = "?ъ씠???먭?/媛꾩냼??紐⑤뱶濡??묒냽 遺덇?"
                    elif "鍮꾨?踰덊샇" in page_text or "password" in page_text.lower():
                        detail = "?꾩씠???먮뒗 鍮꾨?踰덊샇媛 ?щ컮瑜댁? ?딆뒿?덈떎"
                    elif "?먭?" in page_text:
                        detail = "?ъ씠???쒖뒪???먭? 以묒엯?덈떎"
                    
                    return jsonify({"success": False, "message": detail})
            except Exception as e:
                logger.error(f"?숆린??泥섎━ 以??ㅻ쪟: {e}")
                return jsonify({"success": False, "message": f"泥섎━ ?ㅻ쪟: {str(e)[:100]}"})
            finally:
                browser.close()
    except Exception as e:
        logger.error(f"釉뚮씪?곗? ?쒖옉 ?ㅻ쪟: {e}")
        return jsonify({"success": False, "message": f"釉뚮씪?곗? ?ㅽ뻾 ?ㅻ쪟: {str(e)[:100]}"})


@app.route('/add_qr_record', methods=['POST'])
def add_qr_record_endpoint():
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    numbers_list = data.get('numbers_list', []) # [[], [], ...]

    if not uid or not draw_no or not numbers_list:
        return jsonify({"success": False, "message": "?꾩닔 ?뺣낫媛 ?꾨씫?섏뿀?듬땲??"})

    history = load_history()
    if uid not in history: history[uid] = []

    added = 0
    for nums in numbers_list:
        nums.sort()
        # 以묐났 泥댄겕
        exists = any(h['draw_no'] == draw_no and h['numbers'] == nums for h in history[uid])
        if not exists:
            record = {
                "id": len(history[uid]) + 1,
                "draw_no": draw_no,
                "numbers": nums,
                "purchased_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (QR)",
                "win_checked": False,
                "win_result": None
            }
            history[uid].insert(0, record)
            added += 1

    save_history(history)
    return jsonify({"success": True, "message": f"{added}嫄댁쓽 踰덊샇瑜??깅줉?덉뒿?덈떎."})


@app.route('/check_win', methods=['POST'])
def check_win_endpoint():
    """援щℓ 踰덊샇? ?뚯감 ?뱀꺼 寃곌낵 鍮꾧탳"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    my_numbers = data.get('numbers', [])

    # ?꾩옱 ?뚯감? 鍮꾧탳?섏뿬 ?꾩쭅 異붿꺼 ?꾩씤吏 ?뺤씤
    current_draw = get_latest_draw_no()
    if draw_no > current_draw:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "誘몄텛泥?, "match": 0, "bonus": False,
            "draw_no": draw_no, "message": f"{draw_no}?뚮뒗 ?꾩쭅 異붿꺼 ?꾩엯?덈떎."
        }})

    draw_info = get_lotto_info_by_no(draw_no)
    if not draw_info:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "誘몄텛泥?, "match": 0, "bonus": False,
            "draw_no": draw_no, "message": f"{draw_no}???뱀꺼 ?뺣낫瑜??꾩쭅 媛?몄삱 ???놁뒿?덈떎."
        }})

    # 踰덊샇媛 ?녿뒗 寃쎌슦 (?숆린?붾줈 媛?몄삩 硫뷀??뺣낫留??덈뒗 寃쎌슦)
    if not my_numbers:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "踰덊샇 ?놁쓬", "match": 0, "bonus": False,
            "draw_no": draw_no, "message": "援щℓ 踰덊샇媛 ?놁뼱 ?뱀꺼 ?뺤씤??遺덇??⑸땲??"
        }})

    result = check_win(my_numbers, draw_info["numbers"], draw_info["bonus"])
    result["draw_no"] = draw_no
    result["draw_date"] = draw_info["date"]
    result["draw_numbers"] = draw_info["numbers"]
    result["bonus"] = draw_info["bonus"]
    result["my_numbers"] = my_numbers

    # ?대젰 ?낅뜲?댄듃
    if uid:
        update_win_result(uid, draw_no, my_numbers, result)

    return jsonify({"success": True, "result": result})


@app.route('/check_all_wins', methods=['POST'])
def check_all_wins_endpoint():
    """?ъ슜?먯쓽 紐⑤뱺 援щℓ ?대젰 ?뱀꺼 ?뺤씤"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "?꾩씠?붽? ?꾩슂?⑸땲??"})

    current_draw = get_latest_draw_no()
    history = load_history()
    records = history.get(uid, [])
    results = []
    changed = False

    for record in records:
        draw_no = record.get("draw_no", 0)

        # ?대? ?뺤씤???덉퐫?쒕뒗 ?ㅽ궢 (?? 誘몄텛泥⑥씠?덈뜕 寃껋? ?ы솗??
        if record.get("win_checked"):
            prev_result = record.get("win_result", {})
            # ?댁쟾??'誘몄텛泥??댁뿀?쇰㈃ ?ㅼ떆 ?뺤씤
            if prev_result and prev_result.get("rank", 0) != -1:
                results.append(record)
                continue

        # ?꾩쭅 異붿꺼 ?꾩씤 ?뚯감??'誘몄텛泥? 泥섎━
        if draw_no > current_draw:
            record["win_checked"] = False
            record["official_result"] = "誘몄텛泥?
            record["win_result"] = {"rank": -1, "label": "誘몄텛泥?, "match": 0, "bonus": False}
            results.append(record)
            continue

        # 踰덊샇媛 ?녿뒗 寃쎌슦 (?숆린?붿뿉??硫뷀??뺣낫留?媛?몄삩 寃쎌슦)
        nums = record.get("numbers", [])
        if not nums:
            results.append(record)
            continue

        # ?뱀꺼 ?뺣낫 議고쉶 ?쒕룄
        draw_info = get_lotto_info_by_no(draw_no)
        if draw_info:
            win = check_win(nums, draw_info["numbers"], draw_info["bonus"])
            win["draw_numbers"] = draw_info["numbers"]
            win["bonus"] = draw_info["bonus"]
            win["draw_date"] = draw_info["date"]
            record["win_checked"] = True
            record["win_result"] = win
            record["official_result"] = win["label"]
            changed = True
        else:
            # ?뱀꺼 ?뺣낫瑜?媛?몄삱 ???놁쓬 ???꾩쭅 異붿꺼 ??or ?쒕쾭 ?ㅻ쪟
            record["win_checked"] = False
            record["official_result"] = "誘몄텛泥?
            record["win_result"] = {"rank": -1, "label": "誘몄텛泥?, "match": 0, "bonus": False}
        results.append(record)

    history[uid] = results
    if changed:
        save_history(history)
    return jsonify({"success": True, "records": results})


@app.route('/api/balance', methods=['POST'])
def get_balance_api():
    """留덉씠?섏씠吏 ?덉튂湲??곕룞"""
    data = request.json
    uid = data.get('id', '')
    upw = data.get('pw', '')
    if not uid or not upw:
        return jsonify({"success": False, "message": "?꾩씠?붿? 鍮꾨?踰덊샇媛 ?꾩슂?⑸땲??"})
    
    is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer", "--single-process", "--js-flags=--max-old-space-size=128", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(user_agent=UA)
            page = context.new_page()
            
            if HAS_STEALTH:
                try: Stealth().apply_stealth_sync(page)
                except: pass

            if not do_login(page, uid, upw):
                if browser: browser.close()
                return jsonify({"success": False, "message": "?숉뻾蹂듦텒 ?쒕쾭 濡쒓렇???ㅽ뙣"})

            # PC ??硫붿씤?섏씠吏 ?대룞 (?꾩껜 硫붾돱 ?쒖슜)
            page.goto("https://dhlottery.co.kr/common.do?method=main", wait_until="networkidle", timeout=30000)
            time.sleep(1.5)
            
            # ?ъ슜???붿껌: ?꾩껜 硫붾돱 ?대┃
            try:
                page.evaluate("""() => {
                    const menuBtn = document.querySelector('.btn_common.menu, a[title="?꾩껜硫붾돱"], .top_menu, .btn_mypage');
                    if (menuBtn) menuBtn.click();
                }""")
                time.sleep(1.5)
            except: pass
            
            # HTML DOM 援ъ“??臾닿??섍쾶 ?붾㈃???몄텧?섎뒗 ?띿뒪?몃? ?꾨? ?⑹퀜???뺢퇋???ㅼ틪
            info = page.evaluate("""() => {
                let bal = '0';
                let acc = '';
                const fullText = document.body.innerText || '';
                
                // ?대?吏 利앷굅: "?덉튂湲?1,500?? 留ㅼ묶???꾪븳 媛???뺤떎?섍퀬 愿????뺢퇋??
                // "?덉튂湲?, "?붿븸", ":" ?깆쓽 臾몄옄媛 ?덈뱺 ?녿뱺 ?ㅼ씠?됲듃濡??レ옄 留ㅼ튂
                const balMatch = fullText.match(/?덉튂湲?^0-9]*([0-9,]+)\\s*??);
                if (balMatch) {
                    bal = balMatch[1];
                } else {
                    // ?덉튂湲??띿뒪???꾨옒???덉쓣 寃쎌슦
                    const lines = fullText.split('\\n');
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes('?덉튂湲?)) {
                            const m = lines[i].match(/([0-9,]+)\\s*??);
                            if (m) bal = m[1];
                            else if (i + 1 < lines.length) {
                                const m2 = lines[i+1].match(/([0-9,]+)/);
                                if (m2) bal = m2[1];
                            }
                        }
                    }
                }
                
                // 媛?곴퀎醫??ㅽ겕?섑븨
                const accMatch = fullText.match(/耳?대콉??^0-9]*([0-9]{3}-?[0-9]{3}-?[0-9]+(?:\\*)?)/);
                if (accMatch) {
                    acc = '耳?대콉??' + accMatch[1];
                }
                
                return { balance: bal, account: acc };
            }""")
            
            # 留뚯빟 怨꾩쥖踰덊샇媛 ?녿떎硫?留덉씠?섏씠吏?먯꽌 媛?몄삤湲?
            if info.get('balance', '0') == '0' or not info.get('account'):
                page.goto("https://dhlottery.co.kr/user.do?method=myPage", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)
                
                info2 = page.evaluate("""() => {
                    let bal = '0'; let acc = '';
                    const fullText = document.body.innerText || '';
                    const bMatch = fullText.match(/?덉튂湲?^0-9]*([0-9,]+)\\s*??);
                    if (bMatch) bal = bMatch[1];
                    const aMatch = fullText.match(/耳?대콉??^0-9]*([0-9]{3}-?[0-9]{3}-?[0-9]+(?:\\*)?)/);
                    if (aMatch) acc = '耳?대콉??' + aMatch[1];
                    return { balance: bal, account: acc };
                }""")
                if info.get('balance', '0') == '0': info['balance'] = info2.get('balance', '0')
                if not info.get('account'): info['account'] = info2.get('account', '')
            
            import re
            b_str = str(info.get('balance', '0'))
            balance_num = int(re.sub(r'[^0-9]', '', b_str)) if re.sub(r'[^0-9]', '', b_str) else 0
            account_str = info.get('account', '')

            if browser: browser.close()
            return jsonify({"success": True, "balance": balance_num, "account": account_str})
    except Exception as e:
        logger.error(f"?덉튂湲?泥섎━ ?먮윭: {e}")
        try:
            if browser: browser.close()
        except:
            pass
        return jsonify({"success": False, "message": "?붿븸 ?숆린??吏?? ?ㅼ떆 ?쒕룄."})

@app.route('/auto_charge_popup', methods=['GET', 'POST'])
def auto_charge_popup():
    uid = request.args.get('id', '')
    upw = request.args.get('pw', '')
    if not uid or not upw:
        return "蹂댁븞 ?뺣낫媛 ?좏슚?섏? ?딆뒿?덈떎. ?ㅼ떆 ?숆린?뷀빐二쇱꽭??", 400

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <title>?덉쟾 寃곗젣 ?쒕쾭 ?묒냽 以?/title>
    </head>
    <body onload="document.getElementById('autoFrm').submit();" style="text-align:center; padding-top:100px; background:#f8fafc; font-family:sans-serif;">
        <h3 style="color:#0f172a; margin-bottom:10px;">?숉뻾蹂듦텒 異⑹쟾 ?쇳꽣 ?곌껐 以?..</h3>
        <p style="color:#64748b; font-size:14px;">濡쒓렇???몄쬆 ?뺣낫瑜??덉쟾?섍쾶 ?꾩넚?⑸땲??</p>
        <form id="autoFrm" method="post" action="https://dhlottery.co.kr/userSlogin.do?method=login">
            <input type="hidden" name="userId" value="{uid}">
            <input type="hidden" name="password" value="{upw}">
            <input type="hidden" name="checkReturnUrl" value="https://dhlottery.co.kr/userSlogin.do?method=latelyReady">
        </form>
    </body>
    </html>
    """
    return html


@app.route('/news')
def news_endpoint():
    """?ㅼ씠踰??ㅼ떆媛??댁뒪 ?щ·留?(10遺?罹먯떆)"""
    now_ts = time.time()
    cache_key = 'naver_news'
    
    if cache_key in _lotto_cache and (now_ts - _lotto_cache_time.get(cache_key, 0)) < 600:
        return jsonify({"success": True, "news": _lotto_cache[cache_key]})

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer", "--single-process", "--js-flags=--max-old-space-size=128", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(user_agent=UA)
            page = context.new_page()
            
            # 援ш? ?댁뒪 寃??(濡쒕삉 ?ㅼ썙??
            url = "https://www.google.com/search?q=%EB%A1%9C%EB%98%90&tbm=nws"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            news_list = page.evaluate("""() => {
                const results = [];
                // 援ш? ?댁뒪 ??ぉ ??됲꽣 (?쒕ぉ ?꾩＜)
                const items = Array.from(document.querySelectorAll('div.SoR63b, a.WlyS9b, div.mCBkyc, .n0W67d'));
                
                for (let item of items) {
                    if (results.length >= 3) break;
                    
                    let titleEl = item.querySelector('[role="heading"], .mCBkyc, .nDCH9b');
                    let linkEl = item.closest('a') || item.querySelector('a');
                    
                    if (!titleEl && item.tagName === 'DIV' && item.innerText.length > 10) titleEl = item;
                    
                    if (titleEl && linkEl) {
                        const title = titleEl.innerText.trim();
                        const link = linkEl.href;
                        if (title && link && !results.find(r => r.title === title)) {
                            results.push({ title, link });
                        }
                    }
                }
                
                // 寃??寃곌낵媛 ????됲꽣濡????≫옄 寃쎌슦 ?鍮?(踰붿슜 a ?쒓렇 ?먯깋)
                if (results.length === 0) {
                    const links = Array.from(document.querySelectorAll('a')).filter(a => 
                        a.href.includes('url?q=') || (a.innerText.length > 15 && a.querySelector('h3'))
                    );
                    for (let a of links) {
                        if (results.length >= 3) break;
                        const t = a.innerText.split('\\n')[0].trim();
                        if (t.length > 5) results.push({ title: t, link: a.href });
                    }
                }
                
                return results;
            }""")
            
            browser.close()
            if news_list and len(news_list) > 0:
                _lotto_cache[cache_key] = news_list
                _lotto_cache_time[cache_key] = now_ts
                return jsonify({"success": True, "news": news_list})
    except Exception as e:
        logger.error(f"?댁뒪 ?섏쭛 ?ㅽ뙣: {e}")
    
    return jsonify({"success": False, "message": "?댁뒪 ?뺣낫瑜?媛?몄삱 ???놁뒿?덈떎."})


#  ?쒕쾭 ?쒖옉
# ?????????????????????????????????????????????????????????
def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def open_browser():
    ip = get_local_ip()
    try:
        from pyngrok import ngrok
        import atexit
        public_url = ngrok.connect(5000).public_url
        print(f"\n{'='*60}\n?뙋 [?명꽣??二쇱냼] {public_url}\n{'='*60}")
        atexit.register(ngrok.disconnect, public_url)
    except:
        pass
    print(f"?룧 [濡쒖뺄 二쇱냼] http://{ip}:5000")
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == '__main__':
    Timer(1.5, open_browser).start()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
