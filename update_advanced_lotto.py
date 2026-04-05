import bs4
from bs4 import BeautifulSoup

with open("lotto_ai.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f, "html.parser")

# 1. Update Top 3 to Top 6 in Analysis panel
view_lotto = soup.find(id="view-lotto")
if view_lotto:
    freqStats = view_lotto.find(id="freqStats")
    if freqStats:
        freqStats.clear()
        stats_html = """
        <div class="stat-card"><div class="stat-title">1위 번호 (출현 82회)</div><div class="ball c4" style="margin: 0 auto; box-shadow: 0 0 15px rgba(156,163,175, 0.5);">34</div></div>
        <div class="stat-card"><div class="stat-title">2위 번호 (출현 75회)</div><div class="ball c2" style="margin: 0 auto;">18</div></div>
        <div class="stat-card"><div class="stat-title">3위 번호 (출현 71회)</div><div class="ball c3" style="margin: 0 auto;">27</div></div>
        <div class="stat-card"><div class="stat-title">4위 번호 (출현 68회)</div><div class="ball c1" style="margin: 0 auto;">5</div></div>
        <div class="stat-card"><div class="stat-title">5위 번호 (출현 65회)</div><div class="ball c5" style="margin: 0 auto;">42</div></div>
        <div class="stat-card"><div class="stat-title">6위 번호 (출현 61회)</div><div class="ball c2" style="margin: 0 auto;">11</div></div>
        """
        freqStats.append(BeautifulSoup(stats_html, "html.parser"))

    # Replace the chart placeholder with the Custom Analysis Options
    h3_chart = view_lotto.find("h3", text=lambda t: t and "주차별 분석" in t)
    if h3_chart:
        h3_chart.string = "⚙️ 최적 로또 번호 조합 및 추출"
        
        custom_analysis_html = """
        <div style="background:#F9FAFB; border-radius:1rem; padding:1.8rem; border:1px solid var(--border);">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem;">
                <div class="input-wrap" style="margin-bottom:0;">
                    <label>선택 1 : 분석 기간</label>
                    <select class="filter-select" id="optPeriod" style="width:100%; border-radius:0.5rem; padding:0.6rem;">
                        <option value="1">최근 1년</option>
                        <option value="3">최근 3년</option>
                        <option value="5">최근 5년</option>
                        <option value="10">최근 10년</option>
                    </select>
                </div>
                <div class="input-wrap" style="margin-bottom:0;">
                    <label>선택 2 : 주요 발생 월별</label>
                    <select class="filter-select" id="optMonth" style="width:100%; border-radius:0.5rem; padding:0.6rem;">
                        <option value="all">전체 월 종합</option>
                        <option value="1">1월 강세장</option>
                        <option value="4">4월 강세장</option>
                        <option value="12">12월 연말 강세</option>
                    </select>
                </div>
                <div class="input-wrap" style="margin-bottom:0;">
                    <label>선택 3 : 연도 홀짝 분포</label>
                    <select class="filter-select" id="optOddEven" style="width:100%; border-radius:0.5rem; padding:0.6rem;">
                        <option value="all">전체</option>
                        <option value="even">짝수년도 강세 번호</option>
                        <option value="odd">홀수년도 강세 번호</option>
                    </select>
                </div>
                <div class="input-wrap" style="margin-bottom:0;">
                    <label>선택 4 : 구매방식 보정</label>
                    <select class="filter-select" id="optMethod" style="width:100%; border-radius:0.5rem; padding:0.6rem;">
                        <option value="auto">자동 중심 패턴</option>
                        <option value="manual">수동 중심 패턴</option>
                        <option value="mix">반자동 최적화</option>
                    </select>
                </div>
            </div>
            
            <button class="btn btn-primary btn-full" onclick="extractOptimalNumbers()" style="margin-top:0;">✨ 조건에 맞는 최적 번호 추출하기</button>
            
            <!-- Result Display -->
            <div id="optimalResultArea" style="display:none; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px dashed var(--border); text-align:center;">
                <h4 style="color:var(--text-main); margin-bottom: 1rem;">🎯 추출된 AI 최적 번호 조합</h4>
                <div class="ball-row" id="optimalBalls" style="justify-content:center; margin-bottom: 1.5rem;"></div>
                <button class="btn btn-gold btn-full" onclick="sendToMainAI()">👉 메인 단말(AI 분석기)로 번호 연계 및 구매하기</button>
            </div>
        </div>
        """
        chart_div = h3_chart.find_next_sibling("div")
        if chart_div:
            chart_div.replace_with(BeautifulSoup(custom_analysis_html, "html.parser"))


# 2. Main Tab: Add Manual Selection to Predict Panel
predict_panel = soup.find(class_="predict-panel")
if predict_panel:
    btn_grid = predict_panel.find(class_="btn-grid")
    
    manual_wrap_html = """
    <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px dashed rgba(255,255,255,0.2);">
        <h4 style="font-size:0.9rem; margin-bottom: 0.6rem; color: #cbd5e1;">✍️ 수동 번호 직접 입력</h4>
        <div style="display:flex; gap: 0.5rem; align-items:center;">
            <input type="text" id="manualNumbers" placeholder="번호 6개 쉼표(,)로 구분" style="flex:1; padding: 0.7rem; border-radius: 0.5rem; border:1px solid rgba(255,255,255,0.3); background: rgba(0,0,0,0.3); color: #fff; font-size:0.95rem; outline: none;">
            <button class="btn btn-success btn-sm" onclick="applyManualNumbers()" style="padding: 0.8rem 1rem;">적용</button>
        </div>
        <div id="manualError" style="color:#fca5a5; font-size:0.8rem; margin-top:0.4rem; display:none;">숫자 6개를 정확히 입력하세요. (1~45)</div>
    </div>
    """
    # Insert before the purchase/QR btn grid (the second btn-grid)
    second_btn_grid = predict_panel.find_all(class_="btn-grid")[1]
    second_btn_grid.insert_before(BeautifulSoup(manual_wrap_html, "html.parser"))


# 3. Inject JS Logic
js_addition = """
    // ==== 추가된 로또 분석 로직 ====
    // 1~6위 빈도 재렌더링
    const originalExecuteAnalysis = executeAnalysis;
    executeAnalysis = function() {
        const btn = document.getElementById('analysisBtn');
        const period = document.getElementById('analysisPeriod').value;
        const type = document.getElementById('analysisType').value;
        
        btn.disabled = true;
        btn.innerHTML = '진행 중...';
        
        let freqHtml = '';
        setTimeout(() => {
            if (period === '1year' || period === 'all') {
                freqHtml = `
                    <div class="stat-card"><div class="stat-title">1위 번호 (출현 82회)</div><div class="ball c4" style="margin: 0 auto;">34</div></div>
                    <div class="stat-card"><div class="stat-title">2위 번호 (출현 75회)</div><div class="ball c2" style="margin: 0 auto;">18</div></div>
                    <div class="stat-card"><div class="stat-title">3위 번호 (출현 71회)</div><div class="ball c3" style="margin: 0 auto;">27</div></div>
                    <div class="stat-card"><div class="stat-title">4위 번호 (출현 68회)</div><div class="ball c1" style="margin: 0 auto;">5</div></div>
                    <div class="stat-card"><div class="stat-title">5위 번호 (출현 65회)</div><div class="ball c5" style="margin: 0 auto;">42</div></div>
                    <div class="stat-card"><div class="stat-title">6위 번호 (출현 61회)</div><div class="ball c2" style="margin: 0 auto;">11</div></div>
                `;
            } else {
                freqHtml = `
                    <div class="stat-card"><div class="stat-title">1위 (출현 14회)</div><div class="ball c1" style="margin: 0 auto;">3</div></div>
                    <div class="stat-card"><div class="stat-title">2위 (출현 11회)</div><div class="ball c5" style="margin: 0 auto;">45</div></div>
                    <div class="stat-card"><div class="stat-title">3위 (출현 10회)</div><div class="ball c2" style="margin: 0 auto;">12</div></div>
                    <div class="stat-card"><div class="stat-title">4위 (출현 9회)</div><div class="ball c3" style="margin: 0 auto;">26</div></div>
                    <div class="stat-card"><div class="stat-title">5위 (출현 8회)</div><div class="ball c4" style="margin: 0 auto;">31</div></div>
                    <div class="stat-card"><div class="stat-title">6위 (출현 7회)</div><div class="ball c1" style="margin: 0 auto;">7</div></div>
                `;
            }
            document.getElementById('freqStats').innerHTML = freqHtml;
            btn.innerHTML = '🔍 분석 완료';
            setTimeout(() => { btn.disabled = false; btn.innerHTML = '🔍 분석 실행'; }, 2000);
            showToast('Top 6 번호 데이터 분석이 완료되었습니다.');
        }, 1000);
    };

    let optimalNumbersGlobal = [];

    function extractOptimalNumbers() {
        const p = document.getElementById('optPeriod').value;
        const m = document.getElementById('optMonth').value;
        const o = document.getElementById('optOddEven').value;
        const mt = document.getElementById('optMethod').value;
        
        // Mock generation based on options
        let nums = [];
        while(nums.length < 6) {
            let r = Math.floor(Math.random() * 45) + 1;
            if(!nums.includes(r)) nums.push(r);
        }
        nums.sort((a,b) => a-b);
        optimalNumbersGlobal = nums;
        
        const area = document.getElementById('optimalResultArea');
        const ballsDiv = document.getElementById('optimalBalls');
        
        let ballsHtml = '';
        nums.forEach(n => {
            let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
            ballsHtml += `<div class="p-ball on ${colorCls} lg">${n}</div>`;
        });
        
        ballsDiv.innerHTML = ballsHtml;
        area.style.display = 'block';
        showToast('조건에 맞는 최적 번호가 추출되었습니다!');
    }

    function sendToMainAI() {
        if(optimalNumbersGlobal.length !== 6) return;
        
        // 메인 탭으로 이동
        switchNavTab('main');
        
        // 글로벌 predictedNumbers 업데이트
        window.predictedNumbers = optimalNumbersGlobal;
        
        // 화면 랜더링
        const panel = document.getElementById('predictDisplay');
        let html = '';
        optimalNumbersGlobal.forEach((n, i) => {
            setTimeout(() => {
                let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
                const ball = document.createElement('div');
                ball.className = `p-ball ${colorCls}`;
                ball.innerText = n;
                panel.appendChild(ball);
                setTimeout(() => ball.classList.add('on'), 50);
            }, i * 150);
        });
        panel.innerHTML = '';
        
        document.getElementById('purchaseBtn').disabled = false;
        showToast('최적 번호가 구매 리스트로 연계되었습니다.');
    }

    function applyManualNumbers() {
        const input = document.getElementById('manualNumbers').value;
        const err = document.getElementById('manualError');
        err.style.display = 'none';
        
        let parts = input.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n >= 1 && n <= 45);
        // Deduplicate
        parts = [...new Set(parts)];
        
        if (parts.length !== 6) {
            err.style.display = 'block';
            return;
        }
        
        parts.sort((a,b) => a-b);
        window.predictedNumbers = parts;
        
        const panel = document.getElementById('predictDisplay');
        panel.innerHTML = '';
        parts.forEach((n, i) => {
            setTimeout(() => {
                let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
                const ball = document.createElement('div');
                ball.className = `p-ball ${colorCls}`;
                ball.innerText = n;
                panel.appendChild(ball);
                setTimeout(() => ball.classList.add('on'), 50);
            }, i * 150);
        });
        
        document.getElementById('purchaseBtn').disabled = false;
        showToast('수동 번호가 입력되었습니다.');
    }
"""

scripts = soup.find_all("script")
if scripts:
    scripts[-1].append(bs4.NavigableString(js_addition))

with open("lotto_ai.html", "w", encoding="utf-8") as f:
    f.write(str(soup))

print("All advanced features applied.")
