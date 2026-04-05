import bs4
from bs4 import BeautifulSoup

with open("lotto_ai.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f, "html.parser")

# 1. Update Main View with Lotto News
view_main = soup.find(id="view-main")
if view_main:
    right_col = view_main.find("div", class_="main-view-grid").find_all("div", recursive=False)[1]
    news_html = """
    <div class="card" style="margin-top: 1.5rem;">
        <div class="card-title">📰 로또 최신 뉴스</div>
        <div style="display:flex; flex-direction:column; gap:0.8rem;">
            <a href="https://search.naver.com/search.naver?query=로또당첨" target="_blank" class="btn-link" style="justify-content: flex-start; border-radius: 0.8rem; background: #fff; border: 1px solid var(--border);">
                <span style="font-size: 1.2rem;">💸</span> 이번 주 로또 1등 당첨금은 얼마? 당첨 명당은 어디?
            </a>
            <a href="https://search.naver.com/search.naver?query=동행복권+이벤트" target="_blank" class="btn-link" style="justify-content: flex-start; border-radius: 0.8rem; background: #fff; border: 1px solid var(--border);">
                <span style="font-size: 1.2rem;">🎉</span> 동행복권 공식 이벤트 및 공지사항 확인하기
            </a>
            <a href="https://search.naver.com/search.naver?query=로또+세금" target="_blank" class="btn-link" style="justify-content: flex-start; border-radius: 0.8rem; background: #fff; border: 1px solid var(--border);">
                <span style="font-size: 1.2rem;">🧾</span> 로또 당첨금 수령 방법 및 세금 계산법 총정리
            </a>
        </div>
    </div>
    """
    news_soup = BeautifulSoup(news_html, "html.parser")
    right_col.append(news_soup)

# 2. Update Lotto Analysis View to execute JS
view_lotto = soup.find(id="view-lotto")
if view_lotto:
    btn = view_lotto.find("button", text=lambda t: t and "분석 실행" in t)
    if btn:
        btn['onclick'] = "executeAnalysis()"
        btn['id'] = "analysisBtn"

# 3. Completely replace Youtube View
view_youtube = soup.find(id="view-youtube")
if view_youtube:
    view_youtube.clear()
    yt_html = """
    <div class="card">
        <div class="card-title">▶️ 유튜브 통합 미디어 포털</div>
        
        <div class="search-wrap" style="margin-bottom: 1.5rem; max-width: 600px;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <input type="text" id="ytSearch" placeholder="유튜브 검색어를 입력하세요..." onkeypress="searchYoutube(event)">
        </div>
        
        <div style="display:flex; gap: 0.8rem; margin-bottom: 1.5rem;">
            <button class="btn btn-primary btn-sm" onclick="filterYoutube('재미')">🤣 재미있는</button>
            <button class="btn btn-success btn-sm" onclick="filterYoutube('음악')">🎵 트렌딩 음악</button>
            <button class="btn btn-outline btn-sm" onclick="filterYoutube('뉴스')">📰 실시간 뉴스</button>
        </div>
        
        <div id="ytVideoGrid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:1.5rem;">
            <!-- Videos will be injected here via JS -->
            <div style="color:var(--text-muted); text-align:center; grid-column: 1 / -1; padding: 2rem;">카테고리를 선택하거나 검색해주세요.</div>
        </div>
    </div>
    """
    view_youtube.append(BeautifulSoup(yt_html, "html.parser"))

# 4. Completely replace Invest View
view_invest = soup.find(id="view-invest")
if view_invest:
    view_invest.clear()
    invest_html = """
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem; margin-bottom: 1.5rem;">
        <div class="card" style="margin-bottom: 0;">
            <h4 style="color:var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">KOSPI</h4>
            <div style="font-size: 1.8rem; font-weight: 800; color: var(--danger);">2,754.21 <span style="font-size: 1rem;">▲ 1.2%</span></div>
        </div>
        <div class="card" style="margin-bottom: 0;">
            <h4 style="color:var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">NASDAQ</h4>
            <div style="font-size: 1.8rem; font-weight: 800; color: var(--danger);">16,424.31 <span style="font-size: 1rem;">▲ 0.8%</span></div>
        </div>
        <div class="card" style="margin-bottom: 0;">
            <h4 style="color:var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">BTC/KRW</h4>
            <div style="font-size: 1.8rem; font-weight: 800; color: var(--primary);">98,421,000 <span style="font-size: 1rem; color: var(--secondary);">▼ -0.5%</span></div>
        </div>
    </div>
    
    <div class="card">
        <div class="card-title">📰 실시간 투자 시황 뉴스</div>
        <div style="display: flex; flex-direction: column;">
            <div style="padding: 1.2rem 0; border-bottom: 1px solid var(--border); display:flex; justify-content: space-between;">
                <div>
                    <h4 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 0.4rem; color: var(--text-main);">"AI 반도체 훈풍" 삼성전자, SK하이닉스 52주 신고가 경신</h4>
                    <p style="font-size: 0.85rem; color: var(--text-muted);">글로벌 반도체 랠리에 힘입어 국내 증시를 주도하고 있습니다.</p>
                </div>
                <span style="font-size: 0.8rem; color: var(--primary); font-weight: 700;">10분 전</span>
            </div>
            <div style="padding: 1.2rem 0; border-bottom: 1px solid var(--border); display:flex; justify-content: space-between;">
                <div>
                    <h4 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 0.4rem; color: var(--text-main);">비트코인 반감기 도래, 향후 코인 시장 전망은?</h4>
                    <p style="font-size: 0.85rem; color: var(--text-muted);">반감기를 앞두고 변동성이 커지는 가운데 1억 돌파 여부에 주목</p>
                </div>
                <span style="font-size: 0.8rem; color: var(--primary); font-weight: 700;">1시간 전</span>
            </div>
            <div style="padding: 1.2rem 0; display:flex; justify-content: space-between;">
                <div>
                    <h4 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 0.4rem; color: var(--text-main);">미 연준 금리 동결 유력, 하반기 인하 기대감 솔솔</h4>
                    <p style="font-size: 0.85rem; color: var(--text-muted);">인플레이션 지표 둔화로 연내 금리 인하 가능성이 대두됩니다.</p>
                </div>
                <span style="font-size: 0.8rem; color: var(--primary); font-weight: 700;">2시간 전</span>
            </div>
        </div>
        <button class="btn btn-outline btn-full" style="margin-top: 1rem;">더 많은 시황 보기</button>
    </div>
    """
    view_invest.append(BeautifulSoup(invest_html, "html.parser"))

# 5. Inject JavaScript functions for Youtube & Analysis
script_addition = """
    // ==== 로또 분석 실행 ====
    function executeAnalysis() {
        const btn = document.getElementById('analysisBtn');
        const period = document.getElementById('analysisPeriod').value;
        const type = document.getElementById('analysisType').value;
        
        btn.disabled = true;
        btn.innerHTML = '진행 중...';
        
        let freqHtml = '';
        setTimeout(() => {
            if (period === '1year' || period === 'all') {
                freqHtml = `
                    <div class="stat-card"><div class="stat-title">1위 번호 (출현 82회)</div><div class="ball c4" style="margin: 0 auto; box-shadow: 0 0 15px rgba(156,163,175, 0.5);">34</div></div>
                    <div class="stat-card"><div class="stat-title">2위 번호 (출현 75회)</div><div class="ball c2" style="margin: 0 auto;">18</div></div>
                    <div class="stat-card"><div class="stat-title">3위 번호 (출현 71회)</div><div class="ball c3" style="margin: 0 auto;">27</div></div>
                `;
            } else {
                freqHtml = `
                    <div class="stat-card"><div class="stat-title">1위 번호 (출현 14회)</div><div class="ball c1" style="margin: 0 auto; box-shadow: 0 0 15px rgba(251,191,36, 0.5);">3</div></div>
                    <div class="stat-card"><div class="stat-title">2위 번호 (출현 11회)</div><div class="ball c5" style="margin: 0 auto;">45</div></div>
                    <div class="stat-card"><div class="stat-title">3위 번호 (출현 10회)</div><div class="ball c2" style="margin: 0 auto;">12</div></div>
                `;
            }
            document.getElementById('freqStats').innerHTML = freqHtml;
            btn.innerHTML = '🔍 분석 완료';
            setTimeout(() => { btn.disabled = false; btn.innerHTML = '🔍 분석 실행'; }, 2000);
            showToast('데이터 분석이 완료되었습니다.');
        }, 1000);
    }

    // ==== 유튜브 검색 및 필터 ====
    const ytMockData = {
        '재미': [
            { id: '1', title: '역대급 꿀잼 숏츠 모음집', channel: '재밍유튜브', type: 'shorts' },
            { id: '2', title: '강아지 웃긴 영상 레전드', channel: '애견일기' },
            { id: '3', title: '예능 레전드 모음 다시보기', channel: '예능저장소' }
        ],
        '음악': [
            { id: '4', title: '2026 빌보드 탑 100 플레이리스트', channel: 'Music Box' },
            { id: '5', title: '카페에서 듣기 좋은 재즈 & 팝', channel: 'Cafe Vibes' },
            { id: '6', title: '노동요 신나는 K-POP 믹스', channel: '아이돌라디오' }
        ],
        '뉴스': [
            { id: '7', title: '[속보] 글로벌 경제 위기 극복되나', channel: '경제뉴스TV' },
            { id: '8', title: '오늘의 주요 사건/사고 종합', channel: '하루뉴스' },
            { id: '9', title: '부동산 정책 전면 개편 요약', channel: '리얼스토리' }
        ]
    };

    function renderYoutube(videos) {
        const grid = document.getElementById('ytVideoGrid');
        if (!videos || videos.length === 0) {
            grid.innerHTML = '<div style="color:var(--text-muted); text-align:center; grid-column: 1 / -1; padding: 2rem;">검색 결과가 없습니다.</div>';
            return;
        }
        
        let html = '';
        videos.forEach(v => {
            const ratio = v.type === 'shorts' ? '9/16' : '16/9';
            html += `
                <div style="display:flex; flex-direction:column; gap:0.5rem; cursor:pointer;" onclick="window.open('https://youtube.com/results?search_query=${encodeURIComponent(v.title)}', '_blank')">
                    <div style="background:#E2E8F0; border-radius:1rem; aspect-ratio:${ratio}; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; border: 1px solid var(--border);">
                        <span style="font-size:3rem; color: #DC2626;">▶</span>
                        <div style="position:absolute; bottom:0.5rem; right:0.5rem; background:rgba(0,0,0,0.8); color:#fff; padding:0.2rem 0.6rem; border-radius:0.4rem; font-size:0.75rem; font-weight:700;">10:24</div>
                    </div>
                    <h4 style="font-size:1rem; font-weight:700; color:var(--text-main); margin-top:0.3rem;">${v.title}</h4>
                    <p style="font-size:0.85rem; color:var(--text-muted);">${v.channel} • 조회수 10만회</p>
                </div>
            `;
        });
        grid.innerHTML = html;
    }

    function filterYoutube(category) {
        renderYoutube(ytMockData[category] || []);
    }
    
    function searchYoutube(e) {
        if (e.key === 'Enter') {
            const q = document.getElementById('ytSearch').value;
            if(!q) return;
            // Mock search query
            renderYoutube([
                { id: 'search1', title: `'${q}' 최신 리뷰 영상`, channel: '테크튜브' },
                { id: 'search2', title: `'${q}' 완벽 정리 분석`, channel: '인사이트' }
            ]);
        }
    }
    
    // Default load Main Tab
    // document.addEventListener("DOMContentLoaded", () => { switchNavTab('main'); });
"""

scripts = soup.find_all("script")
if scripts:
    scripts[-1].append(bs4.NavigableString(script_addition))

with open("lotto_ai.html", "w", encoding="utf-8") as f:
    f.write(str(soup))
print("All views updated successfully.")
