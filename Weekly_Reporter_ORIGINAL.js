const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));
  const NL = String.fromCharCode(10);
  const to0 = (n) => Math.round(Number(n)||0).toLocaleString('ko-KR');
  const pct = (r) => ((r*100).toFixed(1) + '%');
  const HOLIDAYS = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-03-01','2025-03-03','2025-05-05','2025-05-06','2025-06-06','2025-08-15','2025-10-03','2025-10-06','2025-10-07','2025-10-08','2025-10-09','2025-12-25','2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-05-05','2026-05-24','2026-05-25','2026-06-03','2026-06-06','2026-08-15','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-10-09','2026-12-25'];
  const now = new Date();
  const kst = new Date(now.getTime() + 9*60*60*1000);
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;
  if (HOLIDAYS.includes(today)) return [{ json: { skipped: true, reason: 'Holiday (KRX closed)', today } }];
  const getWeekDates = (ref) => { const dates = []; const d = new Date(ref); const dow = d.getUTCDay(); const daysToFri = (dow === 6) ? 1 : (dow + 2); const friday = new Date(d.getTime() - daysToFri*24*60*60*1000); for (let i=4;i>=0;i--){ const cur = new Date(friday.getTime() - i*24*60*60*1000); const ds = `${cur.getUTCFullYear()}-${String(cur.getUTCMonth()+1).padStart(2,'0')}-${String(cur.getUTCDate()).padStart(2,'0')}`; const wd = cur.getUTCDay(); if (wd>=1 && wd<=5 && !HOLIDAYS.includes(ds)) dates.push(ds); } return dates; };
  const input = items && items[0] && items[0].json || {};
  const forceTest = !!input.forceTest;
  if (forceTest) {
    const msg = '[주간 리포트 테스트] 시스템 정상 작동 - ' + kst.toISOString().slice(0,16).replace('T',' ') + ' KST';
    try { await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); } catch(e) {}
    return [{ json: { testSent: true } }];
  }

  const store = this.getWorkflowStaticData('global');
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  const weekDates = getWeekDates(kst);
  if (weekDates.length === 0) return [{ json: { skipped: true } }];
  
  const recs = [];
  for (const ds of weekDates){ const arr = store.weeklyRecommendations[ds] || []; for (const r of arr){ if (r.type==='scalping' || r.type==='swing') recs.push({ ...r, date: ds }); }}
  if (recs.length === 0) { const msg = '📊 주간 성과 리포트'+NL+NL+'📅 대상: ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length-1] + NL + NL + '추천 없음'; try{ await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); }catch(e){} return [{ json: { sent: true, count: 0 } }]; }

  // Calculate Returns
  let wins = 0;
  let totalReturn = 0;
  const details = [];
  
  const httpDaily = async (t)=> await http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/' + t + '?range=1mo&interval=1d', json: true });
  
  for (const r of recs) {
      try {
          const cDaily = await httpDaily(r.ticker);
          const res = cDaily && cDaily.chart && cDaily.chart.result && cDaily.chart.result[0];
          if (!res) { details.push({ ...r, maxReturn: 0, finalReturn: 0 }); continue; }
          const quotes = res.indicators.quote[0];
          const timestamps = res.timestamp;
          const highs = quotes.high;
          const closes = quotes.close;
          
          let maxR = 0;
          let finalR = 0;
          
          // Find index of recommendation date
          const recDateStr = r.date;
          let startIdx = -1;
          for(let i=0; i<timestamps.length; i++) {
              const d = new Date(timestamps[i]*1000 + 9*60*60*1000);
              const ds = `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`;
              if (ds === recDateStr) { startIdx = i; break; }
          }
          
          if (startIdx >= 0) {
              // Check max high from startIdx to end
              let maxPrice = 0;
              for(let i=startIdx; i<highs.length; i++) {
                  if (highs[i] > maxPrice) maxPrice = highs[i];
              }
              const finalPrice = closes[closes.length-1];
              
              maxR = (maxPrice - r.entry) / r.entry;
              finalR = (finalPrice - r.entry) / r.entry;
          }
          
          if (maxR > 0) wins++;
          totalReturn += maxR;
          details.push({ ...r, maxReturn: maxR, finalReturn: finalR });
          await new Promise(resolve => setTimeout(resolve, 200)); // Rate limit
      } catch(e) {
          details.push({ ...r, maxReturn: 0, finalReturn: 0 });
      }
  }
  
  const avgReturn = recs.length > 0 ? (totalReturn / recs.length) : 0;
  const winRate = recs.length > 0 ? (wins / recs.length) : 0;
  
  // Sort by Max Return
  details.sort((a,b) => b.maxReturn - a.maxReturn);
  const top3 = details.slice(0, 3);

  let msg = '📊 주간 성과 리포트'+NL+NL+'📅 기간: ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length-1] + NL
    + '총 ' + recs.length + '건 추천' + NL
    + '🏆 최고 수익률 평균: ' + pct(avgReturn) + NL
    + '🎯 익절 성공률: ' + pct(winRate) + NL + NL
    + '[BEST 3 종목]' + NL;
    
  for (const t of top3) {
      msg += '🥇 ' + t.name + ' (' + t.type + '): 최고 +' + pct(t.maxReturn) + NL;
  }
  
  msg += NL + '면책: 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.';

  try{ await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); }catch(e){}
  return [{ json: { sent:true, count: recs.length, avgReturn, winRate } }];
};
return run();