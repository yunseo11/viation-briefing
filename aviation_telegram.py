import os
import re
import feedparser, anthropic, requests, datetime

CLAUDE_API_KEY   = os.environ.get("CLAUDE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEEDS = [
    {"name": "eVTOL News",    "url": "https://evtol.news/__rss"},
    {"name": "Simple Flying", "url": "https://simpleflying.com/feed"},
    {"name": "Vertical Mag",  "url": "https://verticalmag.com/feed"},
    {"name": "Aviation Week", "url": "https://aviationweek.com/rss.xml"},
    {"name": "FAA News",      "url": "https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bagencies%5D%5B%5D=federal-aviation-administration"},
    {"name": "EASA News",     "url": "https://www.easa.europa.eu/en/newsroom-and-events/news/feed.xml"},
    {"name": "AVweb",        "url": "https://avweb.com/feed/"},
]

def collect_news():
    articles = []
    for f in RSS_FEEDS:
        try:
            feed = feedparser.parse(f["url"])
            for e in feed.entries[:3]:
                articles.append({"source": f["name"], "title": e.get("title",""), "summary": e.get("summary", e.get("description",""))[:400], "link": e.get("link","")})
            print(f"✅ {f['name']}: {min(3,len(feed.entries))}개")
        except Exception as ex:
            print(f"⚠️ {f['name']} 실패: {ex}")
    return articles

def _filter_stale_urls(urls, max_age_days=21):
    now = datetime.datetime.utcnow()
    pattern = re.compile(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})")
    kept = []
    for u in urls:
        m = pattern.search(u)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime.datetime(y, mo, d)
                if (now - dt).days > max_age_days:
                    continue
            except ValueError:
                pass
        kept.append(u)
    return kept

def web_search(client, query, max_uses=3):
    def _call(q):
        msg = client.messages.create(model="claude-haiku-4-5", max_tokens=1000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
            messages=[{"role":"user","content":q}])
        text_parts = []
        urls = []
        for b in msg.content:
            if hasattr(b, "text"):
                text_parts.append(b.text)
            for c in (getattr(b, "citations", None) or []):
                u = getattr(c, "url", None)
                t = getattr(c, "title", None)
                if u:
                    urls.append(f"{t or ''} - {u}".strip(" -"))
        out = "".join(text_parts)
        uniq = list(dict.fromkeys(urls))
        uniq = _filter_stale_urls(uniq)
        if uniq:
            out += "\n\n[실제 출처 링크]\n" + "\n".join(uniq[:10])
        return out
    result = _call(query)
    refusal_markers = ["구체적인 질문", "명확화", "질문이 필요", "무엇을 원하시", "어떤 정보를 찾으", "다시 말씀", "clarif", "more specific"]
    if any(m in result for m in refusal_markers) or len(result.strip()) < 20:
        print("   ⚠️ 검색 결과가 거절/빈 응답처럼 보여 1회 재시도")
        result = _call(query + "\n\n다시 한번 강조: 절대 질문하거나 명확화를 요구하지 말고, 위에 나열된 키워드들로 지금 바로 web_search 도구를 호출해서 실제 검색 결과를 요약해. 텍스트로만 답하지 말고 반드시 도구를 사용해.")
    return result

def send(text):
    max_len = 4000
    parts = []
    while len(text) > max_len:
        idx = text[:max_len].rfind("\n")
        if idx == -1: idx = max_len
        parts.append(text[:idx])
        text = text[idx:].strip()
    parts.append(text)
    for i, part in enumerate(parts):
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"})
        if r.status_code != 200:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": part})
        print(f"✅ {i+1}/{len(parts)} 발송 완료!" if r.status_code==200 else f"❌ 실패: {r.text}")
def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now_kst = datetime.datetime.now(KST)
    print("="*50)
    print(f"AW항공 데일리 브리핑 | {now_kst.strftime('%Y-%m-%d %H:%M')} KST")
    print("="*50)
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    today = now_kst.strftime("%Y년 %m월 %d일")
    articles = collect_news()
    news_text = "\n".join([f"[{a['source']}] {a['title']}\n{a['summary']}\n{a['link']}" for a in articles])
    print(f"\n총 {len(articles)}개 기사 수집")
    print("🔍 해외 항공 정보 검색 중...")
    global_search = web_search(client, "You must actually call the web_search tool right now and perform a real search. Do not ask for clarification no matter how the query is phrased - just search using these keywords and summarize the results. Search for latest FAA EASA aviation certification rule changes Advisory Circulars UAM eVTOL regulatory updates this week 2026. Also search for recent aviation accidents, crashes, incidents, and safety investigations worldwide in the past 3 days")
    print("🔍 국내 항공 정보 검색 중...")
    korea_search = web_search(client, "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 검색어가 길고 여러 키워드로 보여도 절대 명확화나 재질문을 하지 말고, 아래 키워드들과 관련된 실제 최신 뉴스를 검색해서 결과를 요약해줘. 2026년 대한민국 UAM eVTOL 항공부품 인증 정부과제 공고 국토부 방사청 산업부 중기부 경남 부산 대구 인천 서울 경기 지자체 항공 UAM 사업공고 K-UAM 그랜드챌린지 NTIS IRIS 항공인증 과제공고 K-Startup(k-startup.go.kr) 항공 UAM 드론 관련 사업공고 IRIS(iris.go.kr) 항공 과제공고 TIPS 팁스 창업기업 마감일 신규 등록 최근 공고 당일자 최근 3일 이내 국내 항공 드론 헬기 사고 추락 결함 조사 안전 이슈 뉴스 산림청 소방청 국토부 항공철도사고조사위원회", max_uses=8)
    print(f"   해외검색 미리보기: {global_search[:100]!r}")
    print(f"   국내검색 미리보기: {korea_search[:100]!r}")
    print("✍️ 해외 브리핑 작성 중...")
    m1 = client.messages.create(model="claude-haiku-4-5", max_tokens=3200,
                messages=[{"role":"user","content":f"항공 인증 전문가. 아래 [RSS]/[웹검색]은 실제 웹검색으로 수집한 오늘자 자료야. 너의 실시간 인터넷 접속 여부는 언급하지 말고 이 자료만 근거로 자신있게 작성해. 자료에 없는 내용은 추측하지 말고 해당 섹션은 생략해. [RSS]/[웹검색] 내용이 실제 뉴스가 아니라 오류 메시지, 검색어 재질문, 안내문처럼 보이면 그 내용을 절대 언급하거나 설명하지 말고, 대신 짧게 '오늘은 확인된 주요 해외 소식이 없습니다'라고만 답해. 오늘({today}) 해외 항공 뉴스 텔레그램 메시지 작성.  오늘 날짜 기준으로 이미 지난 날짜의 행사나 마감된 공고는 언급하지 말고, 아직 유효한 최신 정보만 포함해줘. [웹검색] 안의 [실제 출처 링크] 목록은 이미 최근 자료만 걸러져 있어. 이 목록에 없는 오래된 사건(예: 지난 박람회, 예전 실증사업 완료 소식)은 핵심 요약이나 정책 동향에 넣지 말고, 꼭 필요하면 배경 설명으로만 짧게 언급해. 구체적 사실 기반. 각 섹션은 먼저 핵심 사실을 불릿(•)으로 2~3개 정리하고, 그 아래에 짧은 줄글로 1~2문장 부연 설명을 붙여줘. 전문용어가 처음 나올 때는 괄호로 짧게 풀어써줘. 가능하면 출처 링크를 표시해줘.\n\n[RSS]\n{news_text}\n\n[웹검색]\n{global_search}\n\n형식:\n✈️ *AW항공브리핑 해외편 | {today}*\n[오늘 가장 중요한 소식을 임팩트 있게 한 줄로 요약한 후킹 헤드라인]\n\n📌 *핵심 요약*\n• 불릿1\n• 불릿2\n• 불릿3\n\n💡 *쉽게 이해하기*\n전문용어 없이 왜 중요한지 2~3문장으로 풀어서 설명\n\n🚨 *최근 항공 이슈*\n최근 3일 내 해외에서 발생한 항공기·드론·헬기 관련 사고·결함·조사 등 실제 이슈가 자료에 있으면 날짜·장소·현재 상황 포함해 구체적으로 1~2건 정리, 자료에 없으면 이 섹션 생략\n• 이슈1\n• 이슈2\n줄글로 인증·안전 관점의 시사점 1문장\n\n🚁 *UAM eVTOL 글로벌 동향*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n📋 *FAA EASA 인증 변화*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n💼 *글로벌 비즈니스 투자*\n• 불릿1\n• 불릿2\n줄글 1문장\n\n📓 *용어 정리*\n▷ 용어1: 짧은 설명\n▷ 용어2: 짧은 설명\n\n📈 *앞으로 지켜볼 것*\n① 포인트1\n② 포인트2\n③ 포인트3\n\n💬 *결론적으로*\n1~2문장으로 종합 정리\n\n🔗 *원문 링크*\n있으면 링크 나열, 없으면 이 섹션 생략"}])
    print("✍️ 국내 브리핑 작성 중...")
    m2 = client.messages.create(model="claude-haiku-4-5", max_tokens=3200,
                        messages=[{"role":"user","content":f"항공 인증 전문가. 오아래 [웹검색]은 실제 웹검색으로 수집한 오늘자 자료야. 너의 실시간 인터넷 접속 여부는 언급하지 말고 이 자료만 근거로 자신있게 작성해. 자료에 없는 내용은 추측하지 말고 해당 섹션은 생략해. [웹검색] 내용이 실제 뉴스가 아니라 오류 메시지, 검색어 재질문, 안내문처럼 보이면 그 내용을 절대 언급하거나 설명하지 말고, 대신 짧게 '오늘은 확인된 주요 국내 소식이 없습니다'라고만 답해. 늘({today}) 국내 항공 동향 텔레그램 메시지 작성. 오늘 날짜 기준으로 이미 지난 날짜의 행사나 마감된 공고는 언급하지 말고, 아직 유효한 최신 정보만 포함해줘. [웹검색] 안의 [실제 출처 링크] 목록은 이미 최근 자료만 걸러져 있어. 이 목록에 없는 오래된 사건(예: 지난 박람회, 예전 실증사업 완료 소식)은 핵심 요약이나 정책 동향에 넣지 말고, 꼭 필요하면 배경 설명으로만 짧게 언급해.  구체적 사실 기반. 각 섹션은 먼저 핵심 사실을 불릿(•)으로 2~3개 정리하고, 그 아래에 짧은 줄글로 1~2문장 부연 설명을 붙여줘. 전문용어가 처음 나올 때는 괄호로 짧게 풀어써줘. 가능하면 출처 링크를 표시해줘.\n\n[웹검색]\n{korea_search}\n\n형식:\n🇰🇷 *AW항공브리핑 국내편 | {today}*\n[오늘 가장 중요한 소식을 임팩트 있게 한 줄로 요약한 후킹 헤드라인]\n\n📌 *핵심 요약*\n• 불릿1\n• 불릿2\n• 불릿3\n\n💡 *쉽게 이해하기*\n전문용어 없이 왜 중요한지 2~3문장으로 풀어서 설명\n\n🚨 *최근 항공 이슈*\n최근 1주일 내 국내에서 발생한 항공기·헬기·드론·공항 운영 관련 사고·결함·조사·안전 이슈를 UAM에 국한하지 말고 폭넓게 찾아서, 실제 이슈가 자료에 있으면 날짜·장소·현재 상황 포함해 구체적으로 1~2건 정리, 자료에 없으면 이 섹션 생략\n• 이슈1\n• 이슈2\n줄글로 인증·안전 관점의 시사점 1문장\n\n🏛️ *국토부 방사청 정책 동향*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n📢 *정부 지자체 과제 공고* (K-Startup·IRIS·TIPS 등에서 항공·UAM·드론 관련 현재 접수중인 사업만 선별, 마감일과 출처 포함), 신규  공고 위주로, 이미 예전부터 계속 진행 중이던 사업은 중복이므로 제외\n• 과제명 및 내용\n• 과제명 및 내용\n\n🗺️ *지자체 항공 UAM 사업*\n• 지자체1 내용\n• 지자체2 내용\n\n📓 *용어 정리*\n▷ 용어1: 짧은 설명\n▷ 용어2: 짧은 설명\n\n📈 *앞으로 지켜볼 것*\n① 포인트1\n② 포인트2\n③ 포인트3\n\n💬 *결론적으로*\n1~2문장으로 종합 정리, 국내 기업에게 시사점 포함\n\n🔗 *원문 링크*\n있으면 링크 나열, 없으면 이 섹션 생략\n\n_AW인증솔루션 | 항공 규제 트렌드 선제 분석_"}])
    print("🎬 숏폼 소재 후보 작성 중...")
    m3 = client.messages.create(model="claude-haiku-4-5", max_tokens=2000,
        messages=[{"role":"user","content":f"항공 인증 콘텐츠 크리에이터. 오늘 날짜는 {today}야. 아래 [뉴스]/[해외검색]/[국내검색] 자료를 검토해서 숏폼 영상이나 카드뉴스로 만들기 좋은 소재를 골라줘. 자료에 없는 내용은 추측하지 마. 특히 규격 번호·문서 버전·정확한 날짜처럼 구체적인 숫자나 명칭은 자료에 그대로 나와있지 않으면 절대 만들어내지 말고 뭉뚱그려 표현해. 소재로 고를 뉴스는 반드시 최근 2주 이내에 실제로 발생하거나 발표된 것만 선택하고, 그보다 오래된 기사나 날짜가 불분명한 자료는 절대 소재로 쓰지 마. 각 소재의 소재 설명에는 구체적인 날짜(예: 2026년 9월 X일 또는 최소 '이번 주')를 반드시 명시해. 아래 5개 콘텐츠 유형 중 가장 잘 맞는 것 하나로 소재를 분류해줘(억지로 끼워맞추지 말 것):\n1) 항공사업 진입 숏폼 - 타깃:연구소장·임원, 예:자동차 부품회사가 항공사업을 시작할 때 놓치는 것, CTA:인증 준비도 진단\n2) 개발·인증 문제 숏폼 - 타깃:개발팀장·PM, 예:시험은 했는데 인증자료가 부족한 이유, CTA:컨설팅 상담\n3) 실무 문제해결 숏폼 - 타깃:개발 엔지니어, 예:DO-160 시험 전 확인해야 할 것, CTA:전자책 다운로드\n4) 항공인증 용어사전 - 타깃:주니어 연구원, 예:CCL, FHA, MoC, DAL, CTA:전자책·클래스101\n5) 5분 교육 미드폼 - 타깃:개발팀장·실무자, 예:항공기 인증계획서 작성 흐름, CTA:기업교육·컨설팅\n\n선정 기준: 1) 후킹력 있는 소재(반전, 놀라운 사실, 논란, 사고), 2) 시각 자료(영상·사진)가 있을 법한 소재, 3) 위 5개 유형 중 하나에 명확히 들어맞는 소재. 최대 3개까지만 선정하고, 마땅한 소재가 전혀 없으면 다른 말 없이 '오늘은 특별한 소재가 없습니다'라고만 답해.\n\n[뉴스]\n{news_text}\n\n[해외검색]\n{global_search}\n\n[국내검색]\n{korea_search}\n\n형식:\n🎬 *숏폼/카드뉴스 소재 후보 | {today}*\n\n1️⃣ *[후킹 한 줄 제목]*\n📍 소재: 무슨 일이 있었는지 2~3문장\n🎯 콘텐츠 유형: [5개 유형 중 하나] | 타깃: [해당 타깃]\n💡 왜 소재로 좋은지: 반전·놀라움·논란 포인트 1문장\n🎥 형식 제안: 숏폼 영상 또는 카드뉴스 중 추천 + 이유 1문장\n📣 다음 행동: [해당 CTA]\n🔗 출처: 자료의 [실제 출처 링크] 목록에 있는 URL을 그대로 복사, 없으면 '링크 확인 필요'라고 표시\n\n(소재가 더 있으면 2️⃣ 3️⃣로 이어서, 최대 3개)"}])
    send(m1.content[0].text)
    send(m2.content[0].text)
    send(m3.content[0].text)
    print("\n🎉 완료!")

if __name__ == "__main__":
    main()
