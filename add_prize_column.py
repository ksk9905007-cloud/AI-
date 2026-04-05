#!/usr/bin/env python3
"""Add prize column to history table"""

with open('lotto_ai.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Table header (add 당첨금)
old_thead = """                            <tr>
                                <th>회차</th>
                                <th>구매 번호</th>
                                <th>구매일시</th>
                                <th>당첨</th>
                                <th>확인</th>
                            </tr>"""

new_thead = """                            <tr>
                                <th>회차</th>
                                <th>구매 번호</th>
                                <th>구매일시</th>
                                <th>당첨금</th>
                                <th>당첨</th>
                                <th>확인</th>
                            </tr>"""

if old_thead in content:
    content = content.replace(old_thead, new_thead)
    print("OK: Table header updated")

# Fix 2: Table body row (colspan)
old_tbody = """<tbody id="historyBody">
                            <tr><td colspan="5" style="text-align:center;color:var(--muted);padding:1.5rem;">구매 이력이 없습니다</td></tr>
                        </tbody>"""

new_tbody = """<tbody id="historyBody">
                            <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:1.5rem;">구매 이력이 없습니다</td></tr>
                        </tbody>"""
if old_tbody in content:
    content = content.replace(old_tbody, new_tbody)
    print("OK: Empty state colspan updated")

# Fix 3: renderHistory function (add prize column)
idx = content.find("            const checkBtn = (!hasNums || isUndrawn)")
end_idx = content.find("        }).join('');", idx)
old_render_block = content[idx:end_idx]

new_render_block = """            const checkBtn = (!hasNums || isUndrawn)
                ? `<button class="check-btn" disabled style="opacity:0.4;">${isUndrawn ? '대기' : '확인'}</button>`
                : `<button class="check-btn" onclick="checkSingleWin(${r.draw_no},'${JSON.stringify(r.numbers).replace(/"/g,"'")}')">확인</button>`;
            
            // 당첨금 처리
            let prizeDisplay = '-';
            if (r.prize && r.prize.trim() !== '') {
                prizeDisplay = `<b>${r.prize}</b>`;
            } else if (rank > 0 && winResult.prize) {
                // 향후 기능 확장을 위해 (로또 당첨금 자동 계산 기능)
                prizeDisplay = winResult.prize;
            }

            return `
                <tr class="history-item">
                    <td><b>${r.draw_no}회</b></td>
                    <td><div style="display:flex;gap:3px;flex-wrap:wrap;">${balls}</div></td>
                    <td style="font-size:.75rem;color:var(--muted);">${(r.purchased_at||'').substring(0,10)}</td>
                    <td style="font-size:.85rem;color:var(--primary);">${prizeDisplay}</td>
                    <td>${winBadge}</td>
                    <td>${checkBtn}</td>
                </tr>
            `;
"""

if old_render_block:
    content = content[:idx] + new_render_block + content[end_idx:]
    print("OK: renderHistory template updated")

with open('lotto_ai.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("File saved.")
