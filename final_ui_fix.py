import bs4
from bs4 import BeautifulSoup

file_path = 'lotto_ai.html'
with open(file_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

# 1. Update Analysis View (Months 1-12, Days 1-31)
view_lotto = soup.find(id='view-lotto')
if view_lotto:
    optMonth = view_lotto.find(id='optMonth')
    if optMonth:
        optMonth.clear()
        optMonth.append(BeautifulSoup('<option value="all">전체 월</option>', 'html.parser'))
        for i in range(1, 13):
            optMonth.append(BeautifulSoup(f'<option value="{i}">{i}월</option>', 'html.parser'))
    
    # Check if optDay already exists inside this view_lotto to avoid duplicates
    if not view_lotto.find(id='optDay'):
        optOddEven = view_lotto.find(id='optOddEven')
        if optOddEven:
            day_html = '<div class="input-wrap" style="margin-bottom:0;"><label>선택 5 : 특정 일자(1-31일)</label><select class="filter-select" id="optDay" style="width:100%; border-radius:0.5rem; padding:0.6rem;"><option value="all">전체 일</option>'
            for i in range(1, 32):
                day_html += f'<option value="{i}">{i}일</option>'
            day_html += '</select></div>'
            optOddEven.parent.append(BeautifulSoup(day_html, 'html.parser'))

# 2. Add Manual Picker Modal to Body (if not exists)
if not soup.find(id='manualPickerModal'):
    picker_modal = """
<div class="modal" id="manualPickerModal">
    <div class="modal-box" style="max-width: 500px;">
        <div class="modal-title">✍️ 수동 번호 선택 (6개)</div>
        <p class="modal-desc">원하시는 번호 6개를 클릭해주세요.</p>
        <div id="pickerGrid" style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin: 1.5rem 0;">
        </div>
        <div id="selectedDisplay" class="ball-row" style="justify-content: center; margin-bottom: 1.5rem; min-height: 46px;"></div>
        <div class="btn-grid">
            <button class="btn btn-outline" onclick="closeManualPicker()">취소</button>
            <button class="btn btn-primary" id="confirmManualBtn" onclick="confirmManualSelection()" disabled>선택 완료</button>
        </div>
    </div>
</div>
"""
    soup.body.append(BeautifulSoup(picker_modal, 'html.parser'))

# 3. Update Manual Input Section in Main Panel
predict_panel = soup.find(class_='predict-panel')
if predict_panel:
    # Find the manual numbers input container (h4 with 수동 번호)
    h4 = predict_panel.find('h4', string=lambda t: t and '수동 번호' in t)
    if h4:
        container = h4.parent
        container.clear()
        container.append(BeautifulSoup("""
            <h4 style="font-size:0.9rem; margin-bottom: 0.8rem; color: #cbd5e1;">✍️ 수동 번호 직접 선택</h4>
            <button class="btn btn-success btn-full" onclick="openManualPicker()" style="background: rgba(34, 197, 94, 0.2); border: 1px solid #22c55e; margin-top:0;">
                👆 번호판에서 6개 선택하기
            </button>
        """, 'html.parser'))

# 4. Inject Styles
style_tag = soup.find('style')
if style_tag:
    style_tag.append("""
        .picker-ball { 
            width: 40px; height: 40px; border-radius: 50%; border: 1px solid var(--border);
            display: flex; align-items: center; justify-content: center; cursor: pointer;
            font-weight: 700; transition: all 0.2s; background: #f9fafb; font-size: 0.9rem;
        }
        .picker-ball:hover { background: #eef2ff; border-color: var(--primary); }
        .picker-ball.selected { background: var(--primary); color: #fff; border-color: var(--primary); transform: scale(1.1); box-shadow: 0 4px 10px rgba(79,70,229,0.3); }
        
        @keyframes pulse-gold {
            0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7); transform: scale(1); }
            70% { box-shadow: 0 0 0 15px rgba(245, 158, 11, 0); transform: scale(1.02); }
            100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); transform: scale(1); }
        }
        .loading-active { animation: pulse-gold 1.5s infinite !important; background: #d97706 !important; }
    """)

# 5. Inject JS logic
js_logic = """
    // --- 5초 로딩 추출 시뮬레이션 ---
    function extractOptimalNumbers() {
        const btn = document.querySelector('#view-lotto button.btn-primary');
        const resultArea = document.getElementById('optimalResultArea');
        const ballsDiv = document.getElementById('optimalBalls');
        
        btn.disabled = true;
        btn.classList.add('loading-active');
        btn.innerHTML = '📂 AI 최적 엔진 가동 중...';
        
        resultArea.style.display = 'block';
        ballsDiv.innerHTML = '<div style="width:100%; color:var(--text-muted); padding:2rem; font-weight:600;">📡 서버에서 필터링 가중치 데이터를 분석 중입니다... <br><span id="loadingTimer" style="font-size:1.5rem; color:var(--primary);">5</span>초 남음</div>';
        
        let count = 5;
        const timer = setInterval(() => {
            count--;
            const timerEl = document.getElementById('loadingTimer');
            if(timerEl) timerEl.innerText = count;
            
            if(count <= 0) {
                clearInterval(timer);
                finishExtraction(btn, resultArea, ballsDiv);
            }
        }, 1000);
    }

    function finishExtraction(btn, area, ballsDiv) {
        btn.disabled = false;
        btn.classList.remove('loading-active');
        btn.innerHTML = '✨ 조건에 맞는 최적 번호 추출하기';
        
        let nums = [];
        while(nums.length < 6) {
            let r = Math.floor(Math.random() * 45) + 1;
            if(!nums.includes(r)) nums.push(r);
        }
        nums.sort((a,b) => a-b);
        window.optimalNumbersGlobal = nums;
        
        ballsDiv.innerHTML = '';
        nums.forEach((n, i) => {
            setTimeout(() => {
                let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
                const ball = document.createElement('div');
                ball.className = `p-ball on ${colorCls} lg`;
                ball.innerText = n;
                ball.style.animation = 'bounce 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
                ballsDiv.appendChild(ball);
                if(i === 5) showToast('✨ AI 최적 번호 추출이 완료되었습니다!');
            }, i * 150);
        });
    }

    // --- 수동 번호 피크 모달 로직 ---
    let selectedManual = [];

    function openManualPicker() {
        selectedManual = [];
        const grid = document.getElementById('pickerGrid');
        grid.innerHTML = '';
        for(let i=1; i<=45; i++) {
            const ball = document.createElement('div');
            ball.className = 'picker-ball';
            ball.innerText = i;
            ball.onclick = (e) => togglePickerNumber(i, e.target);
            grid.appendChild(ball);
        }
        updatePickerUI();
        document.getElementById('manualPickerModal').classList.add('open');
    }

    function closeManualPicker() {
        document.getElementById('manualPickerModal').classList.remove('open');
    }

    function togglePickerNumber(num, el) {
        if(selectedManual.includes(num)) {
            selectedManual = selectedManual.filter(n => n !== num);
            el.classList.remove('selected');
        } else {
            if(selectedManual.length >= 6) {
                showToast('최대 6개까지만 선택 가능합니다.');
                return;
            }
            selectedManual.push(num);
            el.classList.add('selected');
        }
        updatePickerUI();
    }

    function updatePickerUI() {
        const display = document.getElementById('selectedDisplay');
        const btn = document.getElementById('confirmManualBtn');
        
        const sorted = [...selectedManual].sort((a,b) => a-b);
        display.innerHTML = sorted.map(n => {
            let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
            return `<div class="ball sm ${colorCls}">${n}</div>`;
        }).join('');
        
        btn.disabled = selectedManual.length !== 6;
        btn.innerHTML = selectedManual.length === 6 ? '선택 완료' : `${selectedManual.length}/6 선택중`;
    }

    function confirmManualSelection() {
        window.predictedNumbers = selectedManual.sort((a,b) => a-b);
        const panel = document.getElementById('predictDisplay');
        panel.innerHTML = '';
        window.predictedNumbers.forEach((n, i) => {
            setTimeout(() => {
                let colorCls = n <= 10 ? 'c1' : n <= 20 ? 'c2' : n <= 30 ? 'c3' : n <= 40 ? 'c4' : 'c5';
                const ball = document.createElement('div');
                ball.className = 'p-ball';
                ball.innerText = n;
                panel.appendChild(ball);
                setTimeout(() => ball.classList.add('on'), 50);
            }, i * 100);
        });
        document.getElementById('purchaseBtn').disabled = false;
        closeManualPicker();
        showToast('수동 번호 선택이 완료되어 AI 분석기에 반영되었습니다.');
    }
"""

# Append JS as a separate script to be safe
new_script = soup.new_tag('script')
new_script.string = js_logic
soup.body.append(new_script)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
print("Final UI upgrade applied successfully.")
