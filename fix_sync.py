#!/usr/bin/env python3
"""Fix do_sync_history - 주말 간소화 모드에서 테이블 없이 텍스트 기반 파싱"""
import re

with open('lotto_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func_pattern = r'(def do_sync_history\(page, user_id\):.*?(?=\n# ─────|def automate_purchase))'

new_func = r'''def do_sync_history(page, user_id):
    """마이페이지 구매 내역 동기화 (평일/주말 간소화 대응)"""
    try:
        logger.info("  [SYNC] 구매 내역 페이지 이동 중...")

        # 로그인 후 현재 페이지에서 마이페이지 메뉴 찾기
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
            logger.info(f"  [SYNC] MY 링크: {my_link}")

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
                    logger.warning(f"  [SYNC] GNB 메뉴 클릭 실패: {e2}")
            elif my_link and my_link.startswith('http'):
                page.goto(my_link, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2.0)
                found_mypage = True
        except Exception as e:
            logger.warning(f"  [SYNC] 네비게이션 실패: {e}")

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
        logger.info(f"  [SYNC] 최종 URL: {cur_url}")
        logger.info(f"  [SYNC] tables={debug.get('tables')}, trs={debug.get('trs')}, divItems={debug.get('divItems')}")
        logger.info(f"  [SYNC] 미리보기: {str(debug.get('preview',''))[:500]}")

        if "login" in cur_url.lower() and "logout" not in str(debug.get('preview','')).lower():
            return False, "주말/공휴일 간소화 모드에서는 구매 내역 조회가 불가합니다.\n평일(월~금)에 다시 시도해 주세요."

        # ── 파싱: 3가지 방법 ──
        records = page.evaluate(r"""() => {
            const results = [];

            // === 방법 1: 테이블 구조 (평일) ===
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
                        else if (/로또|lotto/i.test(txt)) lottoName = txt;
                        else if (/^\d{3,4}$/.test(txt) && !drawNo) drawNo = parseInt(txt);
                        else if (/미추첨|당첨|낙첨/.test(txt)) resultStr = txt;
                    }
                    numsText = tds[3] ? tds[3].innerText.trim() : '';
                }

                if (!lottoName.includes('로또') && !lottoName.includes('6/45')) return;
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

            // === 방법 2: div/li 기반 구조 (주말 간소화) ===
            const items = document.querySelectorAll('.item, .list-item, .ledger-item, .buy-item, li, [class*=ledger], [class*=buy], [class*=game]');
            items.forEach(item => {
                const txt = item.innerText || '';
                if (!txt.includes('로또') && !txt.includes('6/45')) return;
                const drawMatch = txt.match(/(\d{3,4})\s*회/);
                if (!drawMatch) return;
                const drawNo = parseInt(drawMatch[1]);
                const dateMatch = txt.match(/\d{4}[-./]\d{2}[-./]\d{2}/);
                const dateStr = dateMatch ? dateMatch[0].replace(/[./]/g, '-') : '';
                let resultStr = '';
                if (txt.includes('미추첨')) resultStr = '미추첨';
                else if (txt.includes('낙첨')) resultStr = '낙첨';
                else if (txt.includes('당첨')) resultStr = '당첨';
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

            // === 방법 3: 전체 페이지 텍스트에서 정규식 ===
            const fullText = document.body.innerText;
            // 로또6/45 항목 찾기: "2026-04-04\n로또6/45\n1218" 패턴
            const blocks = fullText.split(/\n/);
            for (let i = 0; i < blocks.length; i++) {
                if (blocks[i].includes('로또6/45') || blocks[i].includes('로또 6/45')) {
                    // 앞뒤 줄에서 날짜와 회차 찾기
                    let dateStr = '', drawNo = 0, resultStr = '';
                    for (let j = Math.max(0, i-3); j < Math.min(blocks.length, i+5); j++) {
                        const line = blocks[j].trim();
                        const dm = line.match(/^(\d{4}[-./]\d{2}[-./]\d{2})$/);
                        if (dm && !dateStr) dateStr = dm[1].replace(/[./]/g, '-');
                        const dn = line.match(/^(\d{3,4})$/);
                        if (dn && !drawNo) drawNo = parseInt(dn[1]);
                        if (/미추첨/.test(line)) resultStr = '미추첨';
                        else if (/낙첨/.test(line)) resultStr = '낙첨';
                        else if (/당첨/.test(line)) resultStr = '당첨';
                    }
                    if (drawNo > 0) {
                        // 이미 같은 회차가 등록되어있는지 체크
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
            logger.warning("  [SYNC] 모든 파싱 방법 실패")
            return False, "구매 내역을 찾을 수 없습니다."

        logger.info(f"  [SYNC] {len(records)}건 추출 성공!")
        for r in records:
            logger.info(f"  [SYNC] -> {r.get('draw_no')}회 | {r.get('numbers')} | {r.get('official_result')} | {r.get('purchased_at')}")

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
                    "win_checked": r.get('official_result', '') in ['당첨', '낙첨'],
                    "win_result": None,
                    "official_result": r.get('official_result', ''),
                    "prize": r.get('prize', ''),
                }
                if r.get('official_result') == '당첨':
                    new_record["win_result"] = {"rank": -1, "label": "당첨", "match": 0, "bonus": False}
                elif r.get('official_result') == '낙첨':
                    new_record["win_result"] = {"rank": 0, "label": "낙첨", "match": 0, "bonus": False}
                history[uid_key].insert(0, new_record)
                added_count += 1

        if added_count > 0:
            history[uid_key].sort(key=lambda x: x.get('purchased_at',''), reverse=True)
            save_history(history)

        return True, f"{added_count}건의 새로운 내역을 가져왔습니다."
    except Exception as e:
        logger.error(f"동기화 중 오류: {e}")
        return False, str(e)

'''

match = re.search(old_func_pattern, content, flags=re.DOTALL)
if match:
    content = content[:match.start()] + new_func + content[match.end():]
    print(f"OK: replaced ({match.end()-match.start()} -> {len(new_func)} bytes)")
else:
    print("ERROR: pattern not found")

with open('lotto_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Saved.")
