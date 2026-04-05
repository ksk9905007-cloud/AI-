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


# ─────────────────────────────────────────────────────────
#  구매 이력 관리 (JSON 파일 기반, 아이디별 분리)
# ─────────────────────────────────────────────────────────
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
        logger.error(f"이력 저장 오류: {e}")


def add_purchase_record(user_id, draw_no, numbers):
    """구매 이력에 새 항목 추가"""
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
        "win_result": None
    }
    history[uid_key].insert(0, record)  # 최신 순 정렬
    # 최대 100건 유지
    history[uid_key] = history[uid_key][:100]
    save_history(history)
    return record


def update_win_result(user_id, draw_no, numbers, win_info):
    """당첨 결과 업데이트"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        return
    for record in history[uid_key]:
        if record["draw_no"] == draw_no and record["numbers"] == numbers:
            record["win_checked"] = True
            record["win_result"] = win_info
    save_history(history)


# ─────────────────────────────────────────────────────────
#  최신 회차 정보 조회 (Playwright 페이지 파싱)
# ─────────────────────────────────────────────────────────

import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 메모리 캐시 (60분간 유지)
_lotto_cache = {}
_lotto_cache_time = {}
CACHE_TTL = 3600  # 1시간

def get_lotto_info_by_no(draw_no):
    """동행복권 HTML 결과를 직접 파싱하여 가장 빠르고 안정적으로 데이터 획득 (Playwright 브라우저 우회)"""
    now_ts = time.time()
    if draw_no in _lotto_cache and (now_ts - _lotto_cache_time.get(draw_no, 0)) < CACHE_TTL:
        return _lotto_cache[draw_no]

    try:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(user_agent=UA)
            page = context.new_page()

            url = f"https://www.dhlottery.co.kr/lt645/result?drwNo={draw_no}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # 새 페이지의 DOM 구조 파싱 (Swiper 기반 최신 사이트 대응)
            result = page.evaluate("""(draw_no) => {
                // 1. 회차번호 확인
                const drawTitle = document.querySelector('.d-trigger span, .lt645-draw-result h3 strong');
                const titleTxt = drawTitle ? drawTitle.innerText : '';
                const noMatch = titleTxt.match(/(\\d+)\\s*회/);
                const actualNo = noMatch ? parseInt(noMatch[1]) : draw_no;

                // 2. 당첨 번호 추출 (Swiper 활성 슬라이드 내부 우선)
                let ballEls = Array.from(document.querySelectorAll('.swiper-slide-active .ball, .lt645-draw-result .ball, .result-ball'));
                if (ballEls.length < 7) {
                    ballEls = Array.from(document.querySelectorAll('.ball, .result-ball'));
                }

                let balls = [];
                let bonus = 0;
                if (ballEls.length >= 7) {
                    // 번호가 중복 수집될 수 있으므로 상위 7개만 사용
                    const nums = ballEls.slice(0, 7).map(e => parseInt(e.innerText || e.textContent)).filter(n => !isNaN(n));
                    if (nums.length >= 7) {
                        balls = nums.slice(0, 6);
                        bonus = nums[6];
                    }
                }

                // 3. 날짜 추출
                const dateTxt = document.querySelector('.swiper-slide-active .result-infoWrap p, .lt645-draw-date, .lt645-date');
                let date = '';
                if (dateTxt) {
                    const dateMatch = dateTxt.innerText.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/);
                    if (dateMatch) date = dateMatch[0].replace(/\\./g, '-');
                }

                // 4. 당첨금 및 인원 (1등 기준)
                let amount = 0;
                let count = 0;
                const tbl = document.querySelector('.drawResult-tbl, .table-layout');
                if (tbl) {
                    const row = tbl.querySelector('tbody tr:first-child');
                    if (row) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 3) {
                            amount = parseInt(cells[1].innerText.replace(/[^0-9]/g, '')) || 0;
                            count = parseInt(cells[2].innerText.replace(/[^0-9]/g, '')) || 0;
                        }
                    }
                }

                return { actualNo, date, balls, bonus, amount, count };
            }""", draw_no)

            browser.close()

            if result and len(result.get('balls', [])) == 6 and any(b > 0 for b in result['balls']):
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
                logger.info(f"파싱 성공: {draw_no}회 {info}")
                return info
            else:
                logger.warning(f"파싱 실패: {result}")

    except Exception as e:
        logger.error(f"get_lotto_info_by_no 오류: {e}")
    return None

def get_latest_draw_no():
    """이번 주 회차 계산 (토요일 추첨 기준)"""
    try:
        base_date = datetime(2002, 12, 7)
        now = datetime.now()
        draw_no = (now - base_date).days // 7 + 1
        # 당일이 토요일 오후 9시 이전이면 아직 추첨 전
        if now.weekday() == 5 and now.hour < 21:
            draw_no -= 1
        return draw_no
    except:
        return 1215


def get_latest_lotto_info():
    return get_lotto_info_by_no(get_latest_draw_no())




# ─────────────────────────────────────────────────────────
#  당첨 확인 로직
# ─────────────────────────────────────────────────────────
def check_win(my_numbers, draw_numbers, bonus_number):
    """당첨 등수 계산 (1~5등, 미당첨)"""
    my_set = set(my_numbers)
    draw_set = set(draw_numbers)
    match_count = len(my_set & draw_set)
    has_bonus = bonus_number in my_set

    if match_count == 6:
        return {"rank": 1, "label": "🏆 1등!", "match": match_count, "bonus": False}
    elif match_count == 5 and has_bonus:
        return {"rank": 2, "label": "🥈 2등!", "match": match_count, "bonus": True}
    elif match_count == 5:
        return {"rank": 3, "label": "🥉 3등!", "match": match_count, "bonus": False}
    elif match_count == 4:
        return {"rank": 4, "label": "✨ 4등!", "match": match_count, "bonus": False}
    elif match_count == 3:
        return {"rank": 5, "label": "🎯 5등!", "match": match_count, "bonus": False}
    else:
        return {"rank": 0, "label": "미당첨", "match": match_count, "bonus": False}


# ─────────────────────────────────────────────────────────
#  로그인 (평일/주말 간소화 페이지 모두 대응)
# ─────────────────────────────────────────────────────────
def is_logged_in(page):
    try:
        content = page.content()
        indicators = [".btn_logout", "로그아웃", "btn-logout", "logout", "gnb-my", "마이페이지"]
        return any(ind in content for ind in indicators)
    except:
        return False


LOGIN_URLS = [
    "https://www.dhlottery.co.kr/login",
    "https://www.dhlottery.co.kr/user.do?method=login",
]


def do_login(page, user_id, user_pw):
    """동행복권 로그인 (간소화/일반 모드 자동 대응)"""
    for login_url in LOGIN_URLS:
        try:
            logger.info(f"  [LOGIN] 시도: {login_url}")
            page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1.0)

            # 현재 URL이 에러 페이지로 리다이렉트 되었는지 확인
            cur_url = page.url
            if "errorPage" in cur_url or "error" in cur_url.lower():
                logger.warning(f"  [LOGIN] 에러 페이지로 리다이렉트됨: {cur_url}")
                continue

            # 로그인 폼 존재 여부 확인 (다양한 셀렉터 시도)
            id_field = None
            pw_field = None
            login_btn = None

            # 셀렉터 조합들
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
                logger.warning(f"  [LOGIN] 로그인 폼 요소 찾기 실패 (id={id_field}, pw={pw_field}, btn={login_btn})")
                continue

            logger.info(f"  [LOGIN] 폼 요소 발견: id={id_field}, pw={pw_field}, btn={login_btn}")

            # 아이디 입력
            page.fill(id_field, "")
            page.type(id_field, user_id, delay=50)
            time.sleep(0.3)

            # 비밀번호 입력 (type으로 한 글자씩 입력하여 사이트 JS 이벤트 트리거)
            page.fill(pw_field, "")
            page.type(pw_field, user_pw, delay=50)
            time.sleep(0.5)

            # 사이트의 JS가 hidden 필드에 암호화된 비밀번호를 세팅할 시간 확보
            # 일부 사이트에서 hidden 필드(userId, userPswdEncn)에 값을 복사하는 로직이 있음
            page.evaluate("""(args) => {
                const [uid, upw] = args;
                // hidden userId 필드에 값 세팅
                const hiddenId = document.getElementById('userId');
                if (hiddenId && hiddenId.type === 'hidden') {
                    hiddenId.value = uid;
                }
            }""", [user_id, user_pw])
            time.sleep(0.3)

            # 로그인 버튼 클릭
            logger.info("  [LOGIN] 로그인 버튼 클릭...")
            page.click(login_btn)

            # 페이지 로딩 대기
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            time.sleep(1.0)

            # 로그인 성공 확인 (여러 방법으로 판단)
            for attempt in range(20):
                # 방법 1: 페이지 내용에서 로그아웃 버튼/텍스트 존재 확인
                if is_logged_in(page):
                    logger.info("  [LOGIN] ✅ 로그인 성공!")
                    return True

                # 방법 2: URL 변화 확인 (로그인 후 메인/마이페이지로 이동)
                cur = page.url
                if "login" not in cur.lower() and "error" not in cur.lower():
                    # 로그인 페이지를 벗어났으면 성공 가능성 높음
                    content = page.content()
                    if user_id.lower() in content.lower() or "마이" in content or "my" in content.lower():
                        logger.info(f"  [LOGIN] ✅ 로그인 성공 (URL 변화 감지: {cur})")
                        return True

                # 방법 3: 쿠키 확인 (JSESSIONID 등)
                cookies = page.context.cookies()
                session_cookies = [c for c in cookies if 'session' in c['name'].lower() or 'JSESSIONID' in c['name']]
                if session_cookies and attempt > 3:
                    # 세션 쿠키가 존재하고 로그인 페이지를 벗어났다면
                    if "login" not in page.url.lower():
                        logger.info(f"  [LOGIN] ✅ 로그인 성공 (세션 쿠키 감지)")
                        return True

                time.sleep(0.5)

            # 로그인 실패 원인 파악
            fail_content = page.evaluate("() => document.body.innerText.substring(0, 300)")
            logger.error(f"  [LOGIN] ❌ 로그인 실패. 페이지 내용: {fail_content}")

            # 에러 메시지 확인 (비밀번호 틀림 등)
            error_msg = page.evaluate("""() => {
                const alerts = document.querySelectorAll('.alert, .error, .err-msg, .login-error');
                return Array.from(alerts).map(a => a.innerText).join(' ');
            }""")
            if error_msg:
                logger.error(f"  [LOGIN] 에러 메시지: {error_msg}")

        except Exception as e:
            logger.error(f"  [LOGIN] {login_url} 시도 중 오류: {e}")
            continue

    logger.error("  [LOGIN] 모든 로그인 시도 실패")
    return False


# ─────────────────────────────────────────────────────────
#  iframe 탐색
# ─────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────
#  번호 선택
# ─────────────────────────────────────────────────────────
def select_number(frame, num):
    padded = str(num)

    # 방법 1: label JS click (hidden input 대응)
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

    # 방법 2: input checkbox JS 강제 클릭
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

    # 방법 3: Playwright force click
    try:
        lbl = frame.locator(f"label[for='check645num{padded}']")
        if lbl.count() > 0:
            lbl.click(force=True, timeout=1000)
            return True
    except:
        pass

    return False


# ─────────────────────────────────────────────────────────
#  구매 메인 함수
# ─────────────────────────────────────────────────────────
def do_purchase(page, numbers):
    logger.info("[PURCHASE] === 구매 엔진 시작 ===")

    dialog_msgs = []

    def handle_dialog(dialog):
        logger.warning(f"  [DIALOG] {dialog.message}")
        dialog_msgs.append(dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)

    try:
        # STEP 1: 구매 페이지 접속
        logger.info("  [1/7] 구매 페이지 접속 중...")
        page.goto(
            "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40",
            wait_until="networkidle", timeout=30000
        )
        time.sleep(1.0)

        try:
            page.evaluate("""() => {
                document.querySelectorAll('input[value="닫기"],.close,.popup-close')
                    .forEach(el => { try { el.click(); } catch(e){} });
            }""")
        except:
            pass

        # STEP 2: iframe 탐색
        logger.info("  [2/7] game645 iframe 탐색...")
        frame = find_game_frame(page)
        if not frame:
            return False, "game645 iframe을 찾지 못했습니다."
        logger.info(f"    iframe: {frame.url}")

        try:
            frame.wait_for_load_state("domcontentloaded", timeout=8000)
        except:
            pass
        time.sleep(0.5)

        # STEP 3: 게임 UI 확인 (label 존재 여부)
        logger.info("  [3/7] 번호 선택 UI 확인...")
        ui_loaded = False
        for attempt in range(20):
            try:
                label_count = frame.evaluate("""() =>
                    document.querySelectorAll('label[for^="check645num"]').length
                """)
                if label_count > 0:
                    ui_loaded = True
                    logger.info(f"    UI 확인 완료 (label 수: {label_count})")
                    break
            except:
                pass
            time.sleep(0.5)

        if not ui_loaded:
            try:
                txt = frame.evaluate("() => document.body.innerText.substring(0, 200)")
                logger.error(f"  iframe 내용: {txt!r}")
            except:
                pass
            return False, "번호 선택 UI 로드 실패 (구매 시간: 월~토 06:00 ~ 토 20:00)"

        # STEP 4: 혼합선택 탭 활성화
        logger.info("  [4/7] 번호 입력 탭 활성화...")
        try:
            frame.evaluate("""() => {
                for (let el of document.querySelectorAll('a,button,li,label,span,div')) {
                    const t = (el.innerText||el.textContent||'').replace(/\\s/g,'');
                    if (t === '혼합선택' || t === '번호직접선택') { el.click(); return t; }
                }
            }""")
        except:
            pass
        time.sleep(0.3)

        # STEP 5: 번호 6개 선택
        logger.info(f"  [5/7] 번호 선택: {numbers}")
        fail_count = 0
        for num in numbers:
            ok = select_number(frame, num)
            logger.info(f"    {num:02d} {'✅' if ok else '❌'}")
            if not ok:
                fail_count += 1
            time.sleep(0.08)

        # 실제 체크된 수 검증
        try:
            checked = frame.evaluate("""() =>
                document.querySelectorAll('input[id^="check645num"]:checked').length
            """)
            logger.info(f"    체크된 번호 수: {checked}/6")
        except:
            checked = 6 - fail_count

        if fail_count >= 3:
            return False, f"번호 선택 다수 실패 ({fail_count}/6 실패)"

        time.sleep(0.3)

        # STEP 6: 선택완료(확인) 클릭
        logger.info("  [6/7] '선택완료' 클릭...")
        def do_sync_history(page, user_id):
            """마이페이지 구매 내역 동기화 (평일/주말 간소화 대응)"""
            try:
                logger.info("  [SYNC] 구매 내역 페이지 이동 중...")

                mypage_urls = [
                    "https://www.dhlottery.co.kr/myPage.do?method=lottoBuyList",
                    "https://www.dhlottery.co.kr/mypage/mylotteryledger",
                    "https://www.dhlottery.co.kr/myPage.do?method=lottoBuyListView",
                ]

                records = []

                for url in mypage_urls:
                    try:
                        logger.info(f"  [SYNC] URL 시도: {url}")
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(2.0)

                        cur_url = page.url
                        logger.info(f"  [SYNC] 현재 URL: {cur_url}")

                        if "errorPage" in cur_url or "error" in cur_url.lower():
                            logger.warning("  [SYNC] 에러 페이지 -> 다음 URL")
                            continue

                        debug = page.evaluate("""() => ({
                            url: location.href,
                            bodyLen: document.body.innerText.length,
                            preview: document.body.innerText.substring(0, 500),
                            tables: document.querySelectorAll('table').length,
                            trs: document.querySelectorAll('tr').length,
                            tblDataCol: document.querySelectorAll('.tbl_data_col').length,
                        })""")
                        logger.info(f"  [SYNC] tables={debug.get('tables')}, trs={debug.get('trs')}, tblDataCol={debug.get('tblDataCol')}")
                        logger.info(f"  [SYNC] 미리보기: {str(debug.get('preview',''))[:300]}")

                        found = page.evaluate(r"""() => {
                            const results = [];
                            // 방법1: .tbl_data_col (평일)
                            document.querySelectorAll('.tbl_data_col tbody tr').forEach(row => {
                                const tds = row.querySelectorAll('td');
                                if (tds.length < 5) return;
                                const dn = parseInt(tds[1].innerText.replace(/[^0-9]/g,''));
                                const nums = tds[2].innerText.trim().split(/\s+/).map(Number).filter(n=>n>=1&&n<=45);
                                const dt = tds[3].innerText.trim();
                                const rs = tds[4].innerText.trim();
                                if (dn && nums.length===6) results.push({draw_no:dn, numbers:nums.sort((a,b)=>a-b), purchased_at:dt+' 00:00:00', official_result:rs});
                            });
                            if (results.length) return results;
                            // 방법2: 모든 tr에서 추출
                            document.querySelectorAll('table tr, tbody tr').forEach(row => {
                                const txt = row.innerText||'';
                                const nm = txt.match(/(\d+)\s*회/);
                                if (!nm) return;
                                const dn = parseInt(nm[1]);
                                const an = txt.match(/\b([1-9]|[1-3]\d|4[0-5])\b/g);
                                if (!an || an.length<6) return;
                                const nums = an.slice(0,6).map(Number).sort((a,b)=>a-b);
                                const dm = txt.match(/\d{4}[.\-\/]\d{2}[.\-\/]\d{2}/);
                                const dt = dm ? dm[0].replace(/\./g,'-') : '';
                                let rs='';
                                if (txt.includes('낙첨')) rs='낙첨';
                                else if (txt.includes('당첨')) rs='당첨';
                                if (dn>0) results.push({draw_no:dn, numbers:nums, purchased_at:dt+' 00:00:00', official_result:rs});
                            });
                            if (results.length) return results;
                            // 방법3: 전체 텍스트에서 정규식
                            const full = document.body.innerText;
                            const rx = /(\d+)\s*회[\s\S]*?(\d{1,2})[\s,]+(\d{1,2})[\s,]+(\d{1,2})[\s,]+(\d{1,2})[\s,]+(\d{1,2})[\s,]+(\d{1,2})/g;
                            let m;
                            while ((m=rx.exec(full))!==null) {
                                const dn=parseInt(m[1]);
                                const nums=[parseInt(m[2]),parseInt(m[3]),parseInt(m[4]),parseInt(m[5]),parseInt(m[6]),parseInt(m[7])];
                                if (nums.every(n=>n>=1&&n<=45)) results.push({draw_no:dn, numbers:nums.sort((a,b)=>a-b), purchased_at:' 00:00:00', official_result:''});
                            }
                            return results;
                        }""")

                        if found and len(found) > 0:
                            records = found
                            logger.info(f"  [SYNC] {len(records)}건 추출 성공!")
                            break
                        else:
                            logger.warning(f"  [SYNC] {url}에서 내역 없음")

                    except Exception as e:
                        logger.error(f"  [SYNC] {url} 오류: {e}")
                        continue

                if not records:
                    logger.warning("  [SYNC] 모든 URL에서 추출 실패")
                    return False, "구매 내역을 찾을 수 없습니다. (주말에는 일부 내역이 제공되지 않을 수 있습니다)"

                history = load_history()
                uid_key = user_id.lower().strip()
                if uid_key not in history:
                    history[uid_key] = []

                added_count = 0
                for r in records:
                    exists = any(h['draw_no'] == r['draw_no'] and h['numbers'] == r['numbers'] for h in history[uid_key])
                    if not exists:
                        new_record = {
                            "id": len(history[uid_key]) + 1,
                            "draw_no": r['draw_no'],
                            "numbers": r['numbers'],
                            "purchased_at": r['purchased_at'],
                            "win_checked": False,
                            "win_result": None,
                            "official_result": r.get('official_result', '')
                        }
                        history[uid_key].insert(0, new_record)
                        added_count += 1

                if added_count > 0:
                    history[uid_key].sort(key=lambda x: x['purchased_at'], reverse=True)
                    save_history(history)

                return True, f"{added_count}건의 새로운 내역을 가져왔습니다."
            except Exception as e:
                logger.error(f"동기화 중 오류: {e}")
                return False, str(e)
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
            return False, "[6/7] '선택완료' 버튼 클릭 실패"
        logger.info("    선택완료 완료")
        time.sleep(0.8)

        # 잔액/한도 에러 감지
        if dialog_msgs:
            last = dialog_msgs[-1]
            if any(x in last for x in ["부족", "한도", "오류", "실패", "초과", "로그인"]):
                return False, f"구매 불가: {last}"

        # STEP 7: 구매하기 클릭 (frame 내 #btnBuy만)
        logger.info("  [7/7] '구매하기' 클릭...")
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
            return False, "[7/7] '구매하기' 버튼 클릭 실패"
        logger.info("    구매하기 완료")
        time.sleep(1.5)

        # 구매 확인 팝업 처리
        for ctx in [page, frame]:
            try:
                ctx.evaluate("""() => {
                    const sels = ['#popupLayerConfirm .button_ok',
                        '#popupLayerConfirm input[value="확인"]',
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

        # 최종 결과 판정
        logger.info("  === 결과 판정 ===")
        for msg in reversed(dialog_msgs):
            if any(k in msg for k in ["완료", "성공", "발행", "구매하셨"]):
                return True, f"구매 완료: {msg}"
            if any(k in msg for k in ["부족", "한도", "실패", "오류", "초과", "불가", "로그인"]):
                return False, f"구매 실패: {msg}"

        try:
            verdict = page.evaluate("""() => {
                const t = document.body.innerText || '';
                if (t.includes('구매가 완료') || t.includes('발행번호') || t.includes('정상적으로 처리')) return 'ok';
                if (t.includes('잔액이 부족') || t.includes('한도를 초과')) return 'fail';
                return 'unknown';
            }""")
            if verdict == 'ok':
                return True, "구매 완료"
        except:
            pass

        return False, "구매 결과 확인 불가 - 동행복권 '구매내역'을 직접 확인하세요."
    except Exception as e:
        logger.error(f"구매 중 예외: {e}")
        return False, f"구매 오류: {str(e)[:100]}"


def do_sync_history(page, user_id):
    """마이페이지 구매 내역 동기화 (평일/주말 간소화 대응)"""
    try:
        logger.info("  [SYNC] 구매 내역 페이지 이동 중...")
            // 평일용 셀렉터: .tbl_data_col
            // 주말용 셀렉터: .lt-ledger-list, .ledger-table, .tbl-data
            const rows = Array.from(document.querySelectorAll('.tbl_data_col tbody tr, .lt-ledger-list li, .ledger-table tbody tr, .tbl-data tbody tr'));
            
            return rows.map(row => {
                let draw_no = 0;
                let nums = [];
                let date = "";
                let result = "";

                // 평일 테이블 구조 (td 위주)
                const tds = row.querySelectorAll('td');
                if (tds.length >= 5) {
                    draw_no = parseInt(tds[1].innerText.replace(/[^0-9]/g, ''));
                    const nums_text = tds[2].innerText.trim();
                    nums = nums_text.split(/\\s+/).map(n => parseInt(n)).filter(n => !isNaN(n));
                    date = tds[3].innerText.trim();
                    result = tds[4].innerText.trim();
                } 
                // 주말 간소화 페이지 (li 또는 특정 클래스 구조 예상)
                else {
                    const txt = row.innerText || "";
                    const noMatch = txt.match(/(\\d+)회/);
                    if (noMatch) draw_no = parseInt(noMatch[1]);
                    
                    const numsMatch = txt.match(/(\\d{1,2}\\s+){5}\\d{1,2}/);
                    if (numsMatch) {
                        nums = numsMatch[0].split(/\\s+/).map(n => parseInt(n)).filter(n => !isNaN(n));
                    }
                    
                    const dateMatch = txt.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/);
                    if (dateMatch) date = dateMatch[0].replace(/\\./g, '-');
                    
                    if (txt.includes('낙첨')) result = '낙첨';
                    else if (txt.includes('당첨')) result = '당첨';
                }

                if (!draw_no || nums.length !== 6) return null;
                return { draw_no, numbers: nums.sort((a,b)=>a-b), purchased_at: date + " 00:00:00", official_result: result };
            }).filter(r => r !== null);
        }""")

        if not records:
            # 주말 페이지에서 API/JSON 응답을 직접 시도 (일부 주말 환경 대응)
            logger.warning("  [SYNC] HTML에서 내역 추출 실패, 백업 로직 시도...")
            # 필요 시 추가적인 API 스크래핑 로직 삽입 가능
            return False, "구매 내역을 찾을 수 없습니다. (사이트 점검 중이거나 로그인이 풀렸을 수 있습니다)"

        history = load_history()
        uid_key = user_id.lower().strip()
        if uid_key not in history:
            history[uid_key] = []

        added_count = 0
        for r in records:
            # 중복 체크
            exists = any(h['draw_no'] == r['draw_no'] and h['numbers'] == r['numbers'] for h in history[uid_key])
            if not exists:
                new_record = {
                    "id": len(history[uid_key]) + 1,
                    "draw_no": r['draw_no'],
                    "numbers": r['numbers'],
                    "purchased_at": r['purchased_at'],
                    "win_checked": False,
                    "win_result": None,
                    "official_result": r['official_result']
                }
                history[uid_key].insert(0, new_record)
                added_count += 1

        if added_count > 0:
            # 재정렬 및 저장
            history[uid_key].sort(key=lambda x: x['purchased_at'], reverse=True)
            save_history(history)

        return True, f"{added_count}건의 새로운 내역을 가져왔습니다."
    except Exception as e:
        logger.error(f"동기화 중 오류: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────
#  구매 자동화 진입점
# ─────────────────────────────────────────────────────────
def automate_purchase(user_id, user_pw, numbers):
    with sync_playwright() as p:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        browser = p.chromium.launch(
            headless=bool(is_cloud),
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(viewport={"width": 1366, "height": 768}, user_agent=UA)
        page = context.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        try:
            logger.info("=== 로그인 시도 중 ===")
            if do_login(page, user_id, user_pw):
                logger.info("=== 로그인 성공 → 구매 진행 ===")
                return do_purchase(page, numbers)
            return False, "로그인 실패"
        except Exception as e:
            return False, str(e)
        finally:
            browser.close()


# ─────────────────────────────────────────────────────────
#  Flask 라우트
# ─────────────────────────────────────────────────────────
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
        draw_no = get_latest_draw_no()
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
    return jsonify({"success": False, "message": "정보를 가져오지 못했습니다."})


@app.route('/draw')
def draw_endpoint():
    """특정 회차 당첨 정보: /draw?no=1215"""
    no = request.args.get('no', type=int)
    if not no:
        return jsonify({"success": False, "message": "회차 번호가 필요합니다."})
    info = get_lotto_info_by_no(no)
    if info:
        return jsonify({"success": True, "info": info})
    return jsonify({"success": False, "message": f"{no}회 정보를 가져오지 못했습니다."})


@app.route('/history')
def history_endpoint():
    uid = request.args.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "아이디가 필요합니다."})
    history = load_history()
    records = history.get(uid, [])
    return jsonify({"success": True, "records": records, "count": len(records)})


@app.route('/sync_history', methods=['POST'])
def sync_history_endpoint():
    data = request.json
    uid = data.get('id', '')
    pw = data.get('pw', '')

    if not uid or not pw:
        return jsonify({"success": False, "message": "아이디와 비밀번호가 필요합니다."})

    try:
        with sync_playwright() as p:
            is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=UA
            )
            page = context.new_page()
            if HAS_STEALTH:
                Stealth().apply_stealth_sync(page)

            try:
                logger.info(f"=== 동기화 시작: {uid} ===")
                if do_login(page, uid, pw):
                    logger.info("=== 로그인 성공 → 내역 동기화 ===")
                    success, msg = do_sync_history(page, uid)
                    return jsonify({"success": success, "message": msg})
                else:
                    # 로그인 실패 시 상세 원인 파악
                    cur_url = page.url
                    page_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
                    logger.error(f"로그인 실패 - URL: {cur_url}, 내용: {page_text}")
                    
                    detail = "로그인 실패"
                    if "errorPage" in cur_url:
                        detail = "사이트 점검/간소화 모드로 접속 불가"
                    elif "비밀번호" in page_text or "password" in page_text.lower():
                        detail = "아이디 또는 비밀번호가 올바르지 않습니다"
                    elif "점검" in page_text:
                        detail = "사이트 시스템 점검 중입니다"
                    
                    return jsonify({"success": False, "message": detail})
            except Exception as e:
                logger.error(f"동기화 처리 중 오류: {e}")
                return jsonify({"success": False, "message": f"처리 오류: {str(e)[:100]}"})
            finally:
                browser.close()
    except Exception as e:
        logger.error(f"브라우저 시작 오류: {e}")
        return jsonify({"success": False, "message": f"브라우저 실행 오류: {str(e)[:100]}"})


@app.route('/add_qr_record', methods=['POST'])
def add_qr_record_endpoint():
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    numbers_list = data.get('numbers_list', []) # [[], [], ...]

    if not uid or not draw_no or not numbers_list:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."})

    history = load_history()
    if uid not in history: history[uid] = []

    added = 0
    for nums in numbers_list:
        nums.sort()
        # 중복 체크
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
    return jsonify({"success": True, "message": f"{added}건의 번호를 등록했습니다."})


@app.route('/check_win', methods=['POST'])
def check_win_endpoint():
    """구매 번호와 회차 당첨 결과 비교"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    my_numbers = data.get('numbers', [])

    draw_info = get_lotto_info_by_no(draw_no)
    if not draw_info:
        return jsonify({"success": False, "message": f"{draw_no}회 당첨 정보를 가져올 수 없습니다."})

    result = check_win(my_numbers, draw_info["numbers"], draw_info["bonus"])
    result["draw_no"] = draw_no
    result["draw_date"] = draw_info["date"]
    result["draw_numbers"] = draw_info["numbers"]
    result["bonus"] = draw_info["bonus"]
    result["my_numbers"] = my_numbers

    # 이력 업데이트
    if uid:
        update_win_result(uid, draw_no, my_numbers, result)

    return jsonify({"success": True, "result": result})


@app.route('/check_all_wins', methods=['POST'])
def check_all_wins_endpoint():
    """사용자의 모든 구매 이력 당첨 확인"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "아이디가 필요합니다."})

    history = load_history()
    records = history.get(uid, [])
    results = []

    for record in records:
        if record.get("win_checked"):
            results.append(record)
            continue
        draw_info = get_lotto_info_by_no(record["draw_no"])
        if draw_info:
            win = check_win(record["numbers"], draw_info["numbers"], draw_info["bonus"])
            win["draw_numbers"] = draw_info["numbers"]
            win["bonus"] = draw_info["bonus"]
            win["draw_date"] = draw_info["date"]
            record["win_checked"] = True
            record["win_result"] = win
        results.append(record)

    history[uid] = results
    save_history(history)
    return jsonify({"success": True, "records": results})


# ─────────────────────────────────────────────────────────
#  서버 시작
# ─────────────────────────────────────────────────────────
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
        print(f"\n{'='*60}\n🌐 [인터넷 주소] {public_url}\n{'='*60}")
        atexit.register(ngrok.disconnect, public_url)
    except:
        pass
    print(f"🏠 [로컬 주소] http://{ip}:5000")
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == '__main__':
    Timer(1.5, open_browser).start()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
